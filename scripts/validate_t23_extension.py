"""Read-only recomputation and gate validation of the T23 temporal extension."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.graph_config import project_path
from src.stage4_common import save_json, sha256


def main():
    config_path = ROOT / "config/t23.yaml"
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    folder = project_path(cfg["output_dir"])
    summary = json.loads((folder / "t23_summary.json").read_text(encoding="utf-8"))
    features = pd.read_parquet(folder / "t23_temporal_features.parquet")
    scores = pd.read_parquet(folder / "t23_anomaly_scores.parquet")
    events = pd.read_parquet(folder / "t23_events.parquet")
    checks = []

    def check(condition, name):
        checks.append({"check": name, "status": "PASS" if bool(condition) else "FAIL"})
        if not condition:
            raise ValueError(f"T23 independent review failed: {name}")

    check(summary["mandatory_gate_passed"] and summary["validation_pass"], "gate and pipeline true")
    check(summary["config_sha256"] == sha256(config_path), "config hash")
    for key in ("weekly_split", "graph_metrics", "community_metrics", "snapshot_embeddings", "external_stress"):
        check(summary["input_sha256"][key] == sha256(project_path(cfg[key])), f"{key} source hash")
    check(summary["input_sha256"]["external_stress"] == cfg["external_stress_sha256"], "T13 accepted stress SHA")
    for name, digest in summary["outputs"].items():
        check(sha256(folder / name) == digest, f"output SHA {name}")
    review = json.loads((ROOT / "data/processed/t22/t22_independent_review.json").read_text(encoding="utf-8"))
    check(review["all_pass"] and len(review["checks"]) == 112 and all(x["status"] == "PASS" for x in review["checks"]),
          "T20–T22 independently accepted before T23")
    check(len(features) == len(scores) == 188 and not scores.duplicated(["model", "time_window"]).any(), "188 unique model-weeks")
    check(set(scores.model) == set(cfg["models"]), "two frozen embedding models")
    raw = pd.read_parquet(project_path(cfg["graph_metrics"]))
    community = pd.read_parquet(project_path(cfg["community_metrics"]))
    raw = raw.merge(community[["time_window", "hhi_community_volume", "community_concentration_index", "modularity"]],
                    on="time_window", validate="one_to_one").set_index("time_window")
    embedding = pd.read_parquet(project_path(cfg["snapshot_embeddings"]))
    means = sorted(x for x in embedding if x.startswith("mean_"))
    stds = sorted(x for x in embedding if x.startswith("std_"))
    for model in cfg["models"]:
        part = scores[scores.model.eq(model)].sort_values("window_start").reset_index(drop=True)
        f = features[features.model.eq(model)].sort_values("window_start").reset_index(drop=True)
        check(len(part) == 94 and len(f) == 94, f"{model}: complete 94-week ledger")
        check(part[["time_window", "status", "split"]].equals(f[["time_window", "status", "split"]]),
              f"{model}: scores/features calendar same")
        for _, row in f.iterrows():
            source = raw.loc[row.time_window]
            check(np.isclose(row.log_nodes, np.log1p(source.num_nodes)) and
                  np.isclose(row.log_edges, np.log1p(source.num_edges)) and
                  np.isclose(row.hhi_community_volume, source.hhi_community_volume),
                  f"{model}/{row.time_window}: independent raw metric lookup")
        emb = embedding[embedding.model.eq(model)].set_index("time_window")
        selected = f[f.status.eq("scoreable")]
        for _, row in selected.iterrows():
            i = f.index[f.time_window.eq(row.time_window)][0]
            prior = f.iloc[i - 1]
            check((row.window_start - prior.window_start) == pd.Timedelta(days=7) and
                  row.time_window in emb.index and prior.time_window in emb.index,
                  f"{model}/{row.time_window}: strictly previous calendar week")
            now_v = emb.loc[row.time_window, means].to_numpy(dtype=float)
            prev_v = emb.loc[prior.time_window, means].to_numpy(dtype=float)
            now_s = emb.loc[row.time_window, stds].to_numpy(dtype=float)
            prev_s = emb.loc[prior.time_window, stds].to_numpy(dtype=float)
            check(np.isclose(row.embedding_mean_drift, np.linalg.norm(now_v - prev_v)) and
                  np.isclose(row.embedding_std_drift, np.linalg.norm(now_s - prev_s)) and
                  np.isclose(row.delta_log_volume, row.log_volume - prior.log_volume),
                  f"{model}/{row.time_window}: independent temporal-delta lookup")
        train = part.split.eq("train") & part.status.eq("scoreable")
        eligible = part.status.eq("scoreable")
        check(int(train.sum()) == 53 and int((part.split.eq("validation") & eligible).sum()) == 17 and
              int((part.split.eq("test") & eligible).sum()) == 17, f"{model}: train/validation/test timeline")
        check(not part.loc[~eligible, "is_anomaly"].any() and part.loc[~eligible, "anomaly_score"].isna().all(),
              f"{model}: no anomaly across split gap/partial week")
        x_train = part.loc[train, cfg["features"]].to_numpy(dtype=float)
        x_all = part.loc[eligible, cfg["features"]].to_numpy(dtype=float)
        detector = IsolationForest(n_estimators=int(cfg["isolation_forest"]["n_estimators"]),
                                   random_state=int(cfg["seed"]), contamination="auto", n_jobs=1)
        detector.fit(x_train)
        independently_scored = -detector.score_samples(x_all)
        threshold = np.quantile(-detector.score_samples(x_train), float(cfg["isolation_forest"]["train_anomaly_quantile"]))
        check(np.allclose(part.loc[eligible, "anomaly_score"], independently_scored, atol=1e-12) and
              np.allclose(part.threshold_train_only, threshold, atol=1e-12), f"{model}: independent Isolation Forest refit")
        check(part.is_anomaly.equals(part.anomaly_score.gt(threshold).fillna(False)), f"{model}: threshold predicate")
    flagged = scores[scores.is_anomaly][["model", "time_window"]].sort_values(["model", "time_window"]).reset_index(drop=True)
    events_keys = events[["model", "time_window"]].sort_values(["model", "time_window"]).reset_index(drop=True)
    check(flagged.equals(events_keys), "events equal flagged score rows")
    external = pd.read_parquet(project_path(cfg["external_stress"]))
    iso = pd.to_datetime(external.date, utc=True).dt.isocalendar()
    external["week"] = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    stress_count = external.groupby("week").regime.apply(lambda x: x.eq("Stress").sum()).to_dict()
    check(all(row.stress_days_same_week == stress_count.get(row.time_window, 0) for row in scores.itertuples()),
          "external T13 stress labels joined only after anomaly scoring")
    check("stress_days_same_week" not in cfg["features"], "stress absent from detector feature set")
    result = {"protocol_id": cfg["protocol_id"], "all_pass": True, "n_checks": len(checks), "checks": checks,
              "summary_sha256": sha256(folder / "t23_summary.json")}
    save_json(folder / "t23_independent_review.json", result)
    print(json.dumps({"all_pass": True, "n_checks": len(checks)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
