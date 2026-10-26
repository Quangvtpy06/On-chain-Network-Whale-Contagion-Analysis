"""Shared frozen input, preprocessing, scoring and provenance for T20–T22."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml
from sklearn.impute import SimpleImputer
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.preprocessing import StandardScaler

from src.graph_config import ROOT, project_path


SETTINGS = ROOT / "config/graph_ml_stage4.yaml"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def table_value_sha256(frame: pd.DataFrame) -> str:
    """Hash ordered column names and values, independent of Parquet writer metadata/dtype spelling."""
    h = hashlib.sha256()
    h.update(json.dumps(list(frame.columns), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    values = pd.util.hash_pandas_object(frame.reset_index(drop=True), index=False).to_numpy(dtype=np.uint64)
    h.update(values.astype("<u8", copy=False).tobytes())
    return h.hexdigest()


def read_config() -> dict:
    return yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(min(torch.get_num_threads(), 4))
    torch.use_deterministic_algorithms(True)


def load_t19(cfg: dict) -> tuple[pd.DataFrame, list[str], dict]:
    base = project_path(cfg["source_t19"])
    summary = json.loads((base / "t19_summary.json").read_text(encoding="utf-8"))
    window = cfg["primary_window"]
    state = summary["windows"][window]["readiness"]
    if not state["computation_validated"] or not state["node_classification_ready"] or state["pit_label_forecast"]:
        raise ValueError("T19 weekly readiness/scope invalid")
    paths = {name: base / f"t19_{name}_{window}.parquet" for name in ("node_features", "split_windows")}
    for path in paths.values():
        expected = summary["output_file_sha256"].get(path.name)
        if not expected or sha256(path) != expected:
            raise ValueError(f"T19 artifact SHA mismatch: {path.name}")
    feature_dictionary = base / "t19_feature_dictionary.parquet"
    if not feature_dictionary.is_file():
        raise FileNotFoundError(feature_dictionary)
    features = pd.read_parquet(paths["node_features"])
    split = pd.read_parquet(paths["split_windows"])
    dictionary = pd.read_parquet(feature_dictionary)
    columns = dictionary.feature.tolist()
    if len(columns) != 41 or len(set(columns)) != len(columns) or not set(columns).issubset(features.columns):
        raise ValueError("T19 feature dictionary invalid")
    if any(x.startswith("label_") or x in {"address", "split", "time_window", "community_id"} for x in columns):
        raise ValueError("ID/label/split leaked into predictors")
    if features.duplicated(["time_window", "address"]).any():
        raise ValueError("duplicate node-window key")
    if set(features.loc[features.split.isin(["train", "validation", "test"]), "label_class"].dropna()) != set(cfg["classes"]):
        raise ValueError("Unexpected supervised classes")
    if not set(features.time_window).issubset(set(split.time_window)):
        raise ValueError("feature windows absent from T19 split")
    metadata = {
        "t19_protocol_id": summary["protocol_id"],
        "t19_published_hf_revision": cfg["t19_published_hf_revision"],
        "t19_config_sha256": summary["config_sha256"],
        "t19_features_values_sha256": table_value_sha256(features),
        "t19_split_values_sha256": table_value_sha256(split),
        "t19_dictionary_values_sha256": table_value_sha256(dictionary),
        "source_edges_sha256": sha256(project_path(cfg["source_edges"])),
        "config_sha256": sha256(SETTINGS),
    }
    return features, columns, metadata


def transform_features(frame: pd.DataFrame, columns: list[str], cfg: dict,
                       fit_mask: np.ndarray) -> tuple[np.ndarray, dict]:
    raw = frame[columns].replace([np.inf, -np.inf], np.nan).to_numpy(dtype=np.float64)
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    train = imputer.fit_transform(raw[fit_mask])
    scaler = StandardScaler()
    scaler.fit(train)
    x = scaler.transform(imputer.transform(raw))
    x = np.clip(x, -float(cfg["preprocessing"]["clip_standardized"]), float(cfg["preprocessing"]["clip_standardized"]))
    if not np.isfinite(x).all():
        raise ValueError("non-finite transformed feature")
    return x.astype(np.float32), {"imputer_medians": imputer.statistics_.tolist(), "scaler_mean": scaler.mean_.tolist(),
                                   "scaler_scale": scaler.scale_.tolist(), "fit_rows": int(fit_mask.sum())}


def labels_and_masks(frame: pd.DataFrame, classes: list[str]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    y = np.array([classes.index(v) if v in classes else -1 for v in frame.label_class], dtype=np.int64)
    masks = {split: frame.split.eq(split).to_numpy() & (y >= 0) for split in ("train", "validation", "test")}
    if any(mask.sum() == 0 for mask in masks.values()):
        raise ValueError("missing labeled split")
    return y, masks


def score(y: np.ndarray, pred: np.ndarray, classes: list[str]) -> dict:
    if len(y) != len(pred):
        raise ValueError("prediction length differs from labels")
    if len(y) == 0:
        return {"n": 0, "macro_f1": None, "accuracy": None, "by_class": {}, "confusion": []}
    p, r, f, support = precision_recall_fscore_support(y, pred, labels=np.arange(len(classes)), zero_division=0)
    return {"n": len(y), "macro_f1": float(f1_score(y, pred, labels=np.arange(len(classes)), average="macro", zero_division=0)),
            "accuracy": float(np.mean(y == pred)),
            "by_class": {name: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(support[i])}
                         for i, name in enumerate(classes)},
            "confusion": confusion_matrix(y, pred, labels=np.arange(len(classes))).tolist()}


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
