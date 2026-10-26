"""T20: fixed weekly tabular MLP and train-graph-only Node2Vec comparison."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from gensim.models import Word2Vec
from torch import nn

from src.graph_config import ROOT, project_path
from src.stage4_common import SETTINGS, labels_and_masks, load_t19, read_config, save_json, score, seed_all, sha256, transform_features


def training_graph(edges: pd.DataFrame, train_windows: set[str]) -> dict[str, tuple[str, ...]]:
    subset = edges.loc[edges.time_window.isin(train_windows), ["from_address", "to_address"]].drop_duplicates()
    links: dict[str, set[str]] = defaultdict(set)
    for a, b in subset.itertuples(index=False, name=None):
        if a != b:
            links[a].add(b)
            links[b].add(a)
    return {node: tuple(sorted(neighbors)) for node, neighbors in sorted(links.items())}


def walks(graph: dict[str, tuple[str, ...]], cfg: dict, rng: np.random.Generator):
    """Second-order Node2Vec walks; p=q=1 is its unbiased default."""
    p, q = float(cfg["p"]), float(cfg["q"])
    if p <= 0 or q <= 0:
        raise ValueError("Node2Vec p/q must be positive")
    nodes = list(graph)
    for _ in range(int(cfg["walks_per_node"])):
        rng.shuffle(nodes)
        for start in nodes:
            walk = [start]
            for step in range(1, int(cfg["walk_length"])):
                options = graph.get(walk[-1], ())
                if not options:
                    break
                if step == 1 or (p == 1.0 and q == 1.0):
                    chosen = options[int(rng.integers(len(options)))]
                else:
                    prior = walk[-2]
                    prior_neighbors = set(graph.get(prior, ()))
                    weights = np.array([1 / p if n == prior else 1.0 if n in prior_neighbors else 1 / q for n in options])
                    weights /= weights.sum()
                    chosen = options[int(rng.choice(len(options), p=weights))]
                walk.append(chosen)
            yield walk


def node2vec_features(frame: pd.DataFrame, edges: pd.DataFrame, cfg: dict, seed: int) -> tuple[np.ndarray, pd.DataFrame, dict]:
    train_windows = set(frame.loc[frame.split.eq("train"), "time_window"])
    graph = training_graph(edges, train_windows)
    model = Word2Vec(sentences=list(walks(graph, cfg, np.random.default_rng(seed))),
                     vector_size=int(cfg["dimensions"]), window=int(cfg["window"]), min_count=int(cfg["min_count"]),
                     sg=1, workers=1, epochs=int(cfg["epochs"]), seed=seed, sorted_vocab=1,
                     hashfxn=lambda word: int.from_bytes(hashlib.sha256(word.encode("utf-8")).digest()[:8], "little"))
    vectors = {node: model.wv[node].astype(np.float32) for node in graph}
    dim = int(cfg["dimensions"])
    # New addresses use only same-window neighbors with an anchor in the training graph.
    # The train-graph vector space is fixed before validation/test; no future walk is fitted.
    needed = frame[["time_window", "address"]].copy()
    direct = needed.address.map(vectors)
    embedded = np.zeros((len(frame), dim), dtype=np.float32)
    mode = np.zeros(len(frame), dtype=np.int8)
    for i, vector in enumerate(direct):
        if isinstance(vector, np.ndarray):
            embedded[i] = vector
            mode[i] = 1
    missing_keys = set(zip(needed.loc[mode == 0, "time_window"], needed.loc[mode == 0, "address"]))
    if missing_keys:
        neighbor_sum: dict[tuple[str, str], np.ndarray] = {}
        neighbor_n: dict[tuple[str, str], int] = defaultdict(int)
        for window, a, b in edges[["time_window", "from_address", "to_address"]].itertuples(index=False, name=None):
            for target, source in ((a, b), (b, a)):
                key = (window, target)
                if key in missing_keys and source in vectors:
                    if key not in neighbor_sum:
                        neighbor_sum[key] = np.zeros(dim, dtype=np.float64)
                    neighbor_sum[key] += vectors[source]
                    neighbor_n[key] += 1
        for i in np.flatnonzero(mode == 0):
            key = (frame.time_window.iat[i], frame.address.iat[i])
            if key in neighbor_sum:
                embedded[i] = (neighbor_sum[key] / neighbor_n[key]).astype(np.float32)
                mode[i] = 2
    embedding_table = pd.DataFrame({"address": list(vectors), **{f"n2v_{j:02d}": [v[j] for v in vectors.values()] for j in range(dim)}})
    meta = {"train_graph_nodes": len(graph), "train_graph_edges_undirected": sum(map(len, graph.values())) // 2,
            "coverage": {split: {"direct": int((mode[frame.split.eq(split).to_numpy()] == 1).sum()),
                                 "neighbor_mean": int((mode[frame.split.eq(split).to_numpy()] == 2).sum()),
                                 "unavailable": int((mode[frame.split.eq(split).to_numpy()] == 0).sum())}
                         for split in ("train", "validation", "test")}}
    return np.column_stack([embedded, (mode == 0).astype(np.float32)]), embedding_table, meta


class MLP(nn.Module):
    def __init__(self, width: int, hidden: int, n_classes: int):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(width, hidden), nn.ReLU(), nn.Linear(hidden, n_classes))

    def forward(self, x):
        return self.net(x)


def fit_mlp(x: np.ndarray, y: np.ndarray, masks: dict, cfg: dict, seed: int) -> tuple[np.ndarray, dict]:
    seed_all(seed)
    opt = cfg["tabular"]
    model = MLP(x.shape[1], int(opt["hidden"]), len(cfg["classes"]))
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(opt["learning_rate"]), weight_decay=float(opt["weight_decay"]))
    tensor = torch.from_numpy(x)
    labels = torch.from_numpy(y)
    train_idx = np.flatnonzero(masks["train"])
    validation_idx = np.flatnonzero(masks["validation"])
    counts = np.bincount(y[train_idx], minlength=len(cfg["classes"]))
    weights = torch.tensor(len(train_idx) / (len(counts) * counts), dtype=torch.float32)
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    best, best_epoch, wait = -1.0, 0, 0
    best_state = None
    rng = np.random.default_rng(seed)
    for epoch in range(1, int(opt["max_epochs"]) + 1):
        model.train()
        for ids in np.array_split(rng.permutation(train_idx), max(1, int(np.ceil(len(train_idx) / int(opt["batch_size"]))))):
            optimizer.zero_grad()
            loss = loss_fn(model(tensor[ids]), labels[ids])
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val_pred = model(tensor[validation_idx]).argmax(1).numpy()
        value = score(y[validation_idx], val_pred, cfg["classes"])["macro_f1"]
        if value > best + 1e-8:
            best, best_epoch, wait = value, epoch, 0
            best_state = copy.deepcopy(model.state_dict())
        else:
            wait += 1
            if wait >= int(opt["patience"]):
                break
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        probabilities = torch.softmax(model(tensor), dim=1).numpy()
    return probabilities, {"best_epoch": best_epoch, "validation_macro_f1": best, "trained_epochs": epoch,
                           "class_weight": weights.tolist()}


def main():
    cfg = read_config()
    seed = int(cfg["seed"])
    frame, columns, provenance = load_t19(cfg)
    fit_mask = frame.split.eq("train").to_numpy()
    x, preprocessing = transform_features(frame, columns, cfg, fit_mask)
    y, masks = labels_and_masks(frame, cfg["classes"])
    edges = pd.read_parquet(project_path(cfg["source_edges"]), columns=["time_window", "from_address", "to_address"])
    windows = set(frame.time_window)
    edges = edges[edges.time_window.isin(windows)].copy()
    n2v, anchor_table, embedding_meta = node2vec_features(frame, edges, cfg["node2vec"], seed)
    output = ROOT / "data/processed/t20"
    output.mkdir(parents=True, exist_ok=True)
    anchor_table.to_parquet(output / "t20_train_node2vec_anchors.parquet", index=False)
    records, prediction_frames, training = [], [], {}
    for model_name, design in (("tabular_mlp", x), ("tabular_plus_node2vec_mlp", np.column_stack([x, n2v]))):
        probabilities, info = fit_mlp(design, y, masks, cfg, seed)
        training[model_name] = info
        predicted = probabilities.argmax(1)
        for split in ("validation", "test"):
            mask = masks[split]
            subset = frame.loc[mask, ["time_window", "address", "label_class", "address_seen_in_train"]].copy()
            subset["model"] = model_name
            subset["split"] = split
            subset["predicted_class"] = np.asarray(cfg["classes"])[predicted[mask]]
            subset["probability_cex"] = probabilities[mask, 0]
            subset["probability_dex"] = probabilities[mask, 1]
            prediction_frames.append(subset)
            for scope, select in (("all", np.ones(mask.sum(), dtype=bool)),
                                  ("new_address", ~subset.address_seen_in_train.to_numpy())):
                result = score(y[mask][select], predicted[mask][select], cfg["classes"])
                for class_name, class_stats in result["by_class"].items():
                    records.append({"model": model_name, "split": split, "scope": scope, "class": class_name,
                                    "n": result["n"], "macro_f1": result["macro_f1"], "accuracy": result["accuracy"], **class_stats})
    predictions = pd.concat(prediction_frames, ignore_index=True)
    metrics = pd.DataFrame(records)
    predictions.to_parquet(output / "t20_predictions.parquet", index=False)
    metrics.to_parquet(output / "t20_metrics.parquet", index=False)
    save_json(output / "t20_preprocessing.json", preprocessing)
    summary = {"protocol_id": cfg["protocol_id"], "scope": "retrospective CEX/DEX node classification; weekly only",
               "source": provenance, "training": training, "node2vec": embedding_meta,
               "n_predictions": len(predictions), "validation_pass": bool(metrics.n.notna().all() and predictions.duplicated(["model", "split", "time_window", "address"]).sum() == 0),
               "outputs": {name: sha256(output / name) for name in
                           ("t20_train_node2vec_anchors.parquet", "t20_predictions.parquet", "t20_metrics.parquet", "t20_preprocessing.json")}}
    save_json(output / "t20_summary.json", summary)
    if not summary["validation_pass"]:
        raise ValueError("T20 validation failed")
    print(json.dumps({"validation_pass": True, "metrics": metrics.loc[(metrics.split == "test") & (metrics.scope == "all"), ["model", "class", "macro_f1", "f1"]].to_dict("records")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
