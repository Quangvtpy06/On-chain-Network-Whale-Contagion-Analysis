"""T22: GAT and frozen T20/T21/T22 comparison for RQ5."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from src.graph_config import ROOT
from src.stage4_common import read_config, save_json, sha256
from src.stage4_gnn import fit, prepare


def verified_release(folder, task, source):
    summary_path = folder / f"{task}_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not summary["validation_pass"] or summary["source"] != source:
        raise ValueError(f"{task} source/readiness differs from current T19")
    for file_name, digest in summary["outputs"].items():
        if sha256(folder / file_name) != digest:
            raise ValueError(f"{task} artifact changed: {file_name}")
    return summary


def compare_predictions(predictions: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    classes = cfg["classes"]
    test = predictions[predictions.split.eq("test")].copy()
    keys = ["time_window", "address"]
    if test.duplicated(["model"] + keys).any():
        raise ValueError("duplicate model/test/window/address")
    models = sorted(test.model.unique())
    baseline = test[test.model.eq("tabular_mlp")].set_index(keys).sort_index()
    aligned = {}
    for model in models:
        row = test[test.model.eq(model)].set_index(keys).sort_index()
        if not row.index.equals(baseline.index) or not row.label_class.equals(baseline.label_class):
            raise ValueError(f"model {model} is evaluated on a different test sample")
        aligned[model] = row
    entries = []
    for model, row in aligned.items():
        for scope, mask in (("all", np.ones(len(row), dtype=bool)),
                            ("new_address", ~row.address_seen_in_train.to_numpy())):
            actual = row.label_class.to_numpy()[mask]
            predicted = row.predicted_class.to_numpy()[mask]
            entries.append({"model": model, "scope": scope, "n_rows": len(actual),
                            "n_addresses": row.index.get_level_values("address")[mask].nunique(),
                            "n_cex": int((actual == "CEX").sum()), "n_dex": int((actual == "DEX").sum()),
                            "macro_f1": float(f1_score(actual, predicted, labels=classes, average="macro", zero_division=0)) if len(actual) else np.nan})
    comparison = pd.DataFrame(entries)
    val = predictions[predictions.split.eq("validation")]
    validation_score = {}
    for model, part in val.groupby("model"):
        validation_score[model] = float(f1_score(part.label_class, part.predicted_class, labels=classes, average="macro", zero_division=0))
    gnn = sorted((m for m in models if m in {"gcn", "graphsage", "gat"}), key=lambda m: (-validation_score[m], m))
    selected = gnn[0]
    # Primary comparison is frozen by validation, then tested once; resample address clusters.
    a = aligned[selected]
    b = aligned["tabular_mlp"]
    actual = a.label_class.to_numpy()
    pred_a = a.predicted_class.to_numpy()
    pred_b = b.predicted_class.to_numpy()
    addresses = a.index.get_level_values("address").to_numpy()
    unique, inverse = np.unique(addresses, return_inverse=True)
    groups = [np.flatnonzero(inverse == i) for i in range(len(unique))]
    rng = np.random.default_rng(int(cfg["seed"]) + 22)
    boot = []
    for run in range(int(cfg["comparison"]["bootstrap_replicates"])):
        sample = rng.integers(len(unique), size=len(unique))
        ids = np.concatenate([groups[i] for i in sample])
        fa = f1_score(actual[ids], pred_a[ids], labels=classes, average="macro", zero_division=0)
        fb = f1_score(actual[ids], pred_b[ids], labels=classes, average="macro", zero_division=0)
        boot.append({"replicate": run, "delta_macro_f1": float(fa - fb)})
    bootstrap = pd.DataFrame(boot)
    # Sensitivity to a shock shared by addresses in consecutive test weeks.
    week_names = sorted(a.index.get_level_values("time_window").unique())
    week_groups = [np.flatnonzero(a.index.get_level_values("time_window") == week) for week in week_names]
    length = int(cfg["comparison"]["sensitivity_week_block"])
    week_rng = np.random.default_rng(int(cfg["seed"]) + 122)
    weekly_boot = []
    for run in range(int(cfg["comparison"]["bootstrap_replicates"])):
        starts = week_rng.integers(len(week_names), size=int(np.ceil(len(week_names) / length)))
        positions = np.concatenate([(np.arange(start, start + length) % len(week_names)) for start in starts])[:len(week_names)]
        ids = np.concatenate([week_groups[i] for i in positions])
        fa = f1_score(actual[ids], pred_a[ids], labels=classes, average="macro", zero_division=0)
        fb = f1_score(actual[ids], pred_b[ids], labels=classes, average="macro", zero_division=0)
        weekly_boot.append({"replicate": run, "delta_macro_f1": float(fa - fb)})
    weekly_bootstrap = pd.DataFrame(weekly_boot)
    observed = float(f1_score(actual, pred_a, labels=classes, average="macro", zero_division=0) -
                     f1_score(actual, pred_b, labels=classes, average="macro", zero_division=0))
    alpha = float(cfg["comparison"]["alpha"])
    interval = np.quantile(bootstrap.delta_macro_f1, [alpha / 2, 1 - alpha / 2]).tolist()
    result = {"selected_gnn": selected, "selection_rule": "highest validation macro F1 among GCN, GraphSAGE, GAT; ties alphabetic",
              "validation_macro_f1": validation_score, "test_delta_macro_f1_vs_tabular_mlp": observed,
              "address_cluster_bootstrap_95pct_ci": interval,
              "sensitivity_week_block": length,
              "sensitivity_week_block_95pct_ci": np.quantile(weekly_bootstrap.delta_macro_f1, [alpha / 2, 1 - alpha / 2]).tolist(),
              "evidence_gnn_better_at_5pct": bool(interval[0] > 0)}
    return comparison, bootstrap, weekly_bootstrap, result


def main():
    cfg = read_config()
    inputs = prepare()
    t20_folder = ROOT / "data/processed/t20"
    t21_folder = ROOT / "data/processed/t21"
    verified_release(t20_folder, "t20", inputs.provenance)
    verified_release(t21_folder, "t21", inputs.provenance)
    gat_prediction, gat_metrics, gat_embeddings, gat_info = fit(inputs, "gat", cfg)
    t20 = pd.read_parquet(t20_folder / "t20_predictions.parquet")
    t21 = pd.read_parquet(t21_folder / "t21_predictions.parquet")
    all_predictions = pd.concat([t20, t21, gat_prediction], ignore_index=True)
    comparison, bootstrap, weekly_bootstrap, finding = compare_predictions(all_predictions, cfg)
    output = ROOT / "data/processed/t22"
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in (("predictions", gat_prediction), ("metrics", gat_metrics),
                        ("snapshot_embeddings", gat_embeddings), ("model_comparison", comparison),
                        ("bootstrap", bootstrap), ("week_block_sensitivity", weekly_bootstrap)):
        frame.to_parquet(output / f"t22_{name}.parquet", index=False)
    summary = {"protocol_id": cfg["protocol_id"], "scope": "retrospective weekly CEX/DEX node classification",
               "source": inputs.provenance, "t20_summary_sha256": sha256(t20_folder / "t20_summary.json"),
               "t21_summary_sha256": sha256(t21_folder / "t21_summary.json"),
               "gat_training": gat_info, "rq5": finding, "validation_pass": True,
               "outputs": {name: sha256(output / name) for name in
                           ("t22_predictions.parquet", "t22_metrics.parquet", "t22_snapshot_embeddings.parquet",
                            "t22_model_comparison.parquet", "t22_bootstrap.parquet", "t22_week_block_sensitivity.parquet")}}
    save_json(output / "t22_summary.json", summary)
    print(json.dumps({"validation_pass": True, "rq5": finding}, ensure_ascii=False))


if __name__ == "__main__":
    main()
