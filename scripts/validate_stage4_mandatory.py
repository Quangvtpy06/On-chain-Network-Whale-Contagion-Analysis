"""Independent data-level acceptance checks for T20, T21 and T22."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.graph_config import ROOT, project_path
from src.stage4_common import load_t19, read_config, save_json, sha256


def require(ok, message, results):
    results.append({"check": message, "status": "PASS" if ok else "FAIL"})
    if not ok:
        raise ValueError(message)


def validate_task(task: str, source: dict, checks: list) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    folder = ROOT / f"data/processed/{task}"
    summary = json.loads((folder / f"{task}_summary.json").read_text(encoding="utf-8"))
    require(summary["source"] == source, f"{task}: source/config hashes current", checks)
    require(summary["validation_pass"] is True, f"{task}: pipeline validation", checks)
    for name, digest in summary["outputs"].items():
        require(sha256(folder / name) == digest, f"{task}: SHA {name}", checks)
    prediction = pd.read_parquet(folder / f"{task}_predictions.parquet")
    metrics = pd.read_parquet(folder / f"{task}_metrics.parquet")
    require(not prediction.duplicated(["model", "split", "time_window", "address"]).any(), f"{task}: unique prediction keys", checks)
    require(prediction.split.isin(["validation", "test"]).all(), f"{task}: no train predictions released", checks)
    require(np.isfinite(prediction[["probability_cex", "probability_dex"]].to_numpy()).all(), f"{task}: finite probability", checks)
    require(np.allclose(prediction.probability_cex + prediction.probability_dex, 1, atol=1e-6), f"{task}: probability sum", checks)
    require(prediction.predicted_class.eq(np.where(prediction.probability_cex >= prediction.probability_dex, "CEX", "DEX")).all(),
            f"{task}: argmax classes", checks)
    return prediction, metrics, summary


def main():
    cfg = read_config()
    frame, columns, source = load_t19(cfg)
    checks: list[dict] = []
    t19_validation = pd.read_parquet(project_path(cfg["source_t19"]) / "t19_validation.parquet")
    require(t19_validation.status.eq("PASS").all() and len(t19_validation) == 70, "T19: 70 validation checks pass", checks)
    require(len(columns) == 41 and not any(x.startswith("label_") for x in columns), "T19: predictor dictionary excludes labels", checks)
    predictions, metrics, summaries = {}, {}, {}
    for task in ("t20", "t21", "t22"):
        predictions[task], metrics[task], summaries[task] = validate_task(task, source, checks)
    expected = frame[frame.split.isin(["validation", "test"]) & frame.label_class.isin(cfg["classes"])][
        ["split", "time_window", "address", "label_class", "address_seen_in_train"]].sort_values(["split", "time_window", "address"]).reset_index(drop=True)
    for task, prediction in predictions.items():
        for model, group in prediction.groupby("model"):
            sample = group[expected.columns].sort_values(["split", "time_window", "address"]).reset_index(drop=True)
            require(sample.equals(expected), f"{task}/{model}: same frozen validation/test rows and labels", checks)
            for split in ("validation", "test"):
                subset = group[group.split.eq(split)]
                for scope, chosen in (("all", subset), ("new_address", subset[~subset.address_seen_in_train])):
                    if chosen.empty:
                        continue
                    actual, predicted = chosen.label_class.to_numpy(), chosen.predicted_class.to_numpy()
                    macro = f1_score(actual, predicted, labels=cfg["classes"], average="macro", zero_division=0)
                    precision, recall, per_class_f1, support = precision_recall_fscore_support(
                        actual, predicted, labels=cfg["classes"], zero_division=0)
                    reported = metrics[task][(metrics[task].model == model) & (metrics[task].split == split) & (metrics[task].scope == scope)]
                    require(len(reported) == len(cfg["classes"]) and np.allclose(reported.macro_f1, macro, atol=1e-10),
                            f"{task}/{model}/{split}/{scope}: macro F1 independently recomputed", checks)
                    for j, label in enumerate(cfg["classes"]):
                        row = reported[reported["class"] == label]
                        require(len(row) == 1 and np.isclose(row.precision.iloc[0], precision[j]) and
                                np.isclose(row.recall.iloc[0], recall[j]) and np.isclose(row.f1.iloc[0], per_class_f1[j]) and
                                row.support.iloc[0] == support[j], f"{task}/{model}/{split}/{scope}/{label}: class metrics", checks)
    anchors = pd.read_parquet(ROOT / "data/processed/t20/t20_train_node2vec_anchors.parquet")
    require(anchors.address.is_unique and len(anchors) == summaries["t20"]["node2vec"]["train_graph_nodes"],
            "T20: unique train-graph embedding anchors", checks)
    require(summaries["t20"]["node2vec"]["coverage"]["test"]["direct"] >= 0,
            "T20: test embedding availability reported", checks)
    for task, model_count in (("t21", 2), ("t22", 1)):
        embedding = pd.read_parquet(ROOT / f"data/processed/{task}/{task}_snapshot_embeddings.parquet")
        require(len(embedding) == 90 * model_count and embedding.duplicated(["model", "split", "time_window"]).sum() == 0,
                f"{task}: 54 train + 18 validation + 18 test graph embeddings per model", checks)
        require(np.isfinite(embedding.select_dtypes(include="number").to_numpy()).all(), f"{task}: finite graph embeddings", checks)
    finding = summaries["t22"]["rq5"]
    all_predictions = pd.concat(predictions.values(), ignore_index=True)
    val = all_predictions[all_predictions.split.eq("validation")]
    validation_macro = {name: f1_score(sub.label_class, sub.predicted_class, labels=cfg["classes"], average="macro", zero_division=0)
                        for name, sub in val.groupby("model")}
    best = sorted((m for m in ("gcn", "graphsage", "gat")), key=lambda m: (-validation_macro[m], m))[0]
    require(best == finding["selected_gnn"], "T22: GNN selected from validation only", checks)
    compare = pd.read_parquet(ROOT / "data/processed/t22/t22_model_comparison.parquet")
    require(set(compare.model) == set(all_predictions.model) and set(compare.scope) == {"all", "new_address"},
            "T22: all five models/all + new-address comparison", checks)
    test = all_predictions[all_predictions.split.eq("test")]
    a, b = test[test.model.eq(best)], test[test.model.eq("tabular_mlp")]
    delta = f1_score(a.label_class, a.predicted_class, labels=cfg["classes"], average="macro", zero_division=0) - f1_score(
        b.label_class, b.predicted_class, labels=cfg["classes"], average="macro", zero_division=0)
    require(np.isclose(delta, finding["test_delta_macro_f1_vs_tabular_mlp"]), "T22: independent test delta", checks)
    boot = pd.read_parquet(ROOT / "data/processed/t22/t22_bootstrap.parquet")
    ci = np.quantile(boot.delta_macro_f1, [0.025, 0.975])
    require(np.allclose(ci, finding["address_cluster_bootstrap_95pct_ci"]), "T22: bootstrap CI recomputed", checks)
    weekly_boot = pd.read_parquet(ROOT / "data/processed/t22/t22_week_block_sensitivity.parquet")
    week_ci = np.quantile(weekly_boot.delta_macro_f1, [0.025, 0.975])
    require(np.allclose(week_ci, finding["sensitivity_week_block_95pct_ci"]), "T22: week-block sensitivity CI recomputed", checks)
    status = {"protocol_id": cfg["protocol_id"], "all_pass": True, "checks": checks,
              "source": source, "models": sorted(all_predictions.model.unique()),
              "test_new_dex_addresses": int(expected[(expected.split.eq("test")) & (~expected.address_seen_in_train) &
                                                      expected.label_class.eq("DEX")].address.nunique())}
    save_json(ROOT / "data/processed/t22/t22_independent_review.json", status)
    print(json.dumps({"all_pass": True, "n_checks": len(checks), "models": status["models"],
                      "test_new_dex_addresses": status["test_new_dex_addresses"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
