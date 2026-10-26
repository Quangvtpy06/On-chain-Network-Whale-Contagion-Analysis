"""T23 optional extension: causal-order weekly graph anomaly detection."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import IsolationForest

from src.graph_config import ROOT, project_path
from src.stage4_common import load_t19, read_config as stage4_config, save_json, sha256


SETTINGS = ROOT / "config/t23.yaml"


def check_gate(cfg: dict) -> dict:
    review_path = ROOT / "data/processed/t22/t22_independent_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if not review.get("all_pass") or len(review.get("checks", [])) < 112 or any(x["status"] != "PASS" for x in review["checks"]):
        raise ValueError("T20–T22 independent acceptance gate is closed")
    stage_cfg = stage4_config()
    if stage_cfg["protocol_id"] != cfg["stage4_protocol"]:
        raise ValueError("stage4 protocol changed")
    _, _, source = load_t19(stage_cfg)
    if review["source"] != source:
        raise ValueError("T20–T22 review source differs from current T19/T08")
    for task in ("t20", "t21", "t22"):
        folder = ROOT / f"data/processed/{task}"
        summary = json.loads((folder / f"{task}_summary.json").read_text(encoding="utf-8"))
        if not summary.get("validation_pass") or summary["source"] != source:
            raise ValueError(f"{task} output is not accepted")
        if any(sha256(folder / name) != digest for name, digest in summary["outputs"].items()):
            raise ValueError(f"{task} artifact hash changed")
    t22 = json.loads((ROOT / "data/processed/t22/t22_summary.json").read_text(encoding="utf-8"))
    if t22["rq5"]["selected_gnn"] != cfg["primary_model"]:
        raise ValueError("T23 primary model must be validation-selected GNN")
    return source


def temporal_features(cfg: dict) -> pd.DataFrame:
    split = pd.read_parquet(project_path(cfg["weekly_split"]))[["time_window", "window_start", "split"]]
    graph = pd.read_parquet(project_path(cfg["graph_metrics"]))[["time_window", "num_nodes", "num_edges", "total_volume_usdt", "density", "reciprocity"]]
    community = pd.read_parquet(project_path(cfg["community_metrics"]))[["time_window", "hhi_community_volume", "community_concentration_index", "modularity"]]
    base = split.merge(graph, on="time_window", validate="one_to_one").merge(community, on="time_window", validate="one_to_one")
    if len(base) != 94 or base.time_window.duplicated().any():
        raise ValueError("incomplete weekly graph calendar")
    base = base.sort_values("window_start").reset_index(drop=True)
    base["log_nodes"] = np.log1p(base.num_nodes)
    base["log_edges"] = np.log1p(base.num_edges)
    base["log_volume"] = np.log1p(base.total_volume_usdt)
    for col in ("log_nodes", "log_edges", "log_volume", "hhi_community_volume", "community_concentration_index"):
        base[f"delta_{col}"] = base[col].diff()
    embedding = pd.read_parquet(project_path(cfg["snapshot_embeddings"]))
    if embedding.duplicated(["model", "time_window"]).any():
        raise ValueError("duplicate T21 graph embeddings")
    mean_cols = sorted(x for x in embedding if x.startswith("mean_"))
    std_cols = sorted(x for x in embedding if x.startswith("std_"))
    rows = []
    for model in cfg["models"]:
        current = base.merge(embedding[embedding.model.eq(model)][["time_window"] + mean_cols + std_cols], on="time_window", how="left", validate="one_to_one")
        means = current[mean_cols].to_numpy(dtype=float)
        stds = current[std_cols].to_numpy(dtype=float)
        current["embedding_mean_norm"] = np.linalg.norm(means, axis=1)
        current["embedding_std_norm"] = np.linalg.norm(stds, axis=1)
        current["embedding_mean_drift"] = np.linalg.norm(means - np.roll(means, 1, axis=0), axis=1)
        current["embedding_std_drift"] = np.linalg.norm(stds - np.roll(stds, 1, axis=0), axis=1)
        current.loc[0, ["embedding_mean_drift", "embedding_std_drift"]] = np.nan
        consecutive = current.window_start.diff().eq(pd.Timedelta(days=7))
        ready = current.split.isin(["train", "validation", "test"]) & consecutive & current[mean_cols].notna().all(axis=1) & current[mean_cols].shift(1).notna().all(axis=1)
        current["status"] = np.where(ready, "scoreable", np.where(current.split.isin(["train", "validation", "test"]), "missing_previous_embedding", "excluded_split_or_partial"))
        current["model"] = model
        current = current.drop(columns=mean_cols + std_cols)
        rows.append(current)
    result = pd.concat(rows, ignore_index=True)
    if result[result.status.eq("scoreable")][cfg["features"]].isna().any().any():
        raise ValueError("missing anomaly feature in scoreable week")
    return result


def stress_week_counts(path: Path) -> pd.DataFrame:
    stress = pd.read_parquet(path)
    if len(stress) != 655 or stress.date.duplicated().any() or int(stress.regime.eq("Stress").sum()) != 66:
        raise ValueError("T13 external stress series differs from accepted definition")
    dates = pd.to_datetime(stress.date, utc=True)
    iso = dates.dt.isocalendar()
    stress["time_window"] = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    return stress.groupby("time_window").regime.apply(lambda x: int(x.eq("Stress").sum())).rename("stress_days_same_week").reset_index()


def detect(features: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    all_scores, model_info = [], {}
    options = cfg["isolation_forest"]
    for model in cfg["models"]:
        current = features[features.model.eq(model)].copy()
        train = current.split.eq("train") & current.status.eq("scoreable")
        scoreable = current.status.eq("scoreable")
        if int(train.sum()) != 53 or int((current.split.eq("test") & scoreable).sum()) != 17:
            raise ValueError("unexpected train/test temporal windows")
        x_train = current.loc[train, cfg["features"]].to_numpy(dtype=float)
        x_all = current.loc[scoreable, cfg["features"]].to_numpy(dtype=float)
        detector = IsolationForest(n_estimators=int(options["n_estimators"]), random_state=int(cfg["seed"]),
                                   contamination="auto", n_jobs=int(options["n_jobs"]))
        detector.fit(x_train)
        train_score = -detector.score_samples(x_train)
        threshold = float(np.quantile(train_score, float(options["train_anomaly_quantile"])))
        current["anomaly_score"] = np.nan
        current.loc[scoreable, "anomaly_score"] = -detector.score_samples(x_all)
        current["threshold_train_only"] = threshold
        current["is_anomaly"] = current.anomaly_score.gt(threshold).fillna(False)
        model_info[model] = {"n_train_fit": int(train.sum()), "n_validation_scored": int((current.split.eq("validation") & scoreable).sum()),
                             "n_test_scored": int((current.split.eq("test") & scoreable).sum()), "threshold_train_only": threshold,
                             "n_train_anomalies": int(current.loc[train, "is_anomaly"].sum()),
                             "n_test_anomalies": int(current.loc[current.split.eq("test"), "is_anomaly"].sum())}
        all_scores.append(current)
    return pd.concat(all_scores, ignore_index=True), model_info


def chart(scores: pd.DataFrame, cfg: dict, path: Path):
    selected = scores[scores.model.eq(cfg["primary_model"])].sort_values("window_start")
    fig, ax = plt.subplots(figsize=(12, 4.5), constrained_layout=True)
    ax.plot(selected.window_start, selected.anomaly_score, lw=1.7, color="#26508c", label="GraphSAGE anomaly score")
    ax.axhline(selected.threshold_train_only.iloc[0], color="#cf6e2d", ls="--", lw=1.4, label="Train P95 threshold")
    flagged = selected[selected.is_anomaly]
    ax.scatter(flagged.window_start, flagged.anomaly_score, color="#cf3d36", s=30, zorder=3, label="Flagged week")
    for when in selected.loc[selected.stress_days_same_week.gt(0), "window_start"]:
        ax.axvspan(when, when + pd.Timedelta(days=7), color="#e2c1c1", alpha=.14)
    ax.set(title="Temporal graph anomalies, weekly USDT network", xlabel="UTC week", ylabel="Isolation Forest anomaly score")
    ax.grid(alpha=.2)
    ax.legend(loc="upper left", fontsize=8)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    cfg = yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))
    source = check_gate(cfg)
    if sha256(project_path(cfg["external_stress"])) != cfg["external_stress_sha256"]:
        raise ValueError("T13 published stress artifact SHA changed")
    features = temporal_features(cfg)
    scores, model_info = detect(features, cfg)
    stress = stress_week_counts(project_path(cfg["external_stress"]))
    scores = scores.merge(stress, on="time_window", validate="many_to_one", how="left")
    scores["stress_days_same_week"] = scores.stress_days_same_week.fillna(0).astype(int)
    events = scores[scores.is_anomaly][["model", "time_window", "window_start", "split", "anomaly_score", "threshold_train_only", "stress_days_same_week"]].copy()
    output = project_path(cfg["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output / "t23_temporal_features.parquet", index=False)
    scores.to_parquet(output / "t23_anomaly_scores.parquet", index=False)
    events.to_parquet(output / "t23_events.parquet", index=False)
    chart(scores, cfg, output / "t23_timeline.png")
    checks = [{"check": "mandatory_gate", "status": "PASS"},
              {"check": "complete_94_week_calendar", "status": "PASS" if features.groupby("model").size().eq(94).all() else "FAIL"},
              {"check": "train_only_fit", "status": "PASS" if all(v["n_train_fit"] == 53 for v in model_info.values()) else "FAIL"},
              {"check": "no_unscored_anomalies", "status": "PASS" if not scores.loc[~scores.status.eq("scoreable"), "is_anomaly"].any() else "FAIL"},
              {"check": "stress_not_predictor", "status": "PASS" if "stress_days_same_week" not in cfg["features"] else "FAIL"},
              {"check": "no_duplicate_key", "status": "PASS" if not scores.duplicated(["model", "time_window"]).any() else "FAIL"}]
    validation = pd.DataFrame(checks)
    validation.to_parquet(output / "t23_validation.parquet", index=False)
    if not validation.status.eq("PASS").all():
        raise ValueError("T23 pipeline validation failed")
    primary = scores[(scores.model.eq(cfg["primary_model"])) & (scores.split.eq("test")) & scores.status.eq("scoreable")]
    summary = {"protocol_id": cfg["protocol_id"], "scope": "unsupervised weekly temporal graph anomaly detection; retrospective stress overlap descriptive only",
               "mandatory_gate_passed": True, "validation_pass": True, "stage4_source": source,
               "input_sha256": {key: sha256(project_path(cfg[key])) for key in ("weekly_split", "graph_metrics", "community_metrics", "snapshot_embeddings", "external_stress")},
               "config_sha256": sha256(SETTINGS), "model_info": model_info,
               "test_primary_scored_weeks": len(primary), "test_primary_anomaly_weeks": int(primary.is_anomaly.sum()),
               "test_primary_anomalies_with_same_week_stress": int((primary.is_anomaly & primary.stress_days_same_week.gt(0)).sum()),
               "outputs": {name: sha256(output / name) for name in ("t23_temporal_features.parquet", "t23_anomaly_scores.parquet", "t23_events.parquet", "t23_validation.parquet", "t23_timeline.png")}}
    save_json(output / "t23_summary.json", summary)
    print(json.dumps({"validation_pass": True, "test_weeks": len(primary),
                      "test_anomalies": int(primary.is_anomaly.sum()), "overlap_stress": summary["test_primary_anomalies_with_same_week_stress"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
