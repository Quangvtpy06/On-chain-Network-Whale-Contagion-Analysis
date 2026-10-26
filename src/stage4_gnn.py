"""Weekly snapshot GNN preparation/training shared by T21 GCN/SAGE and T22 GAT."""
from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.data import Data
from torch_geometric.nn import GATConv, GCNConv, SAGEConv

from src.graph_config import project_path
from src.stage4_common import labels_and_masks, load_t19, read_config, score, seed_all, transform_features


@dataclass
class GraphInputs:
    frame: pd.DataFrame
    graphs: dict[str, list[Data]]
    classes: list[str]
    preprocessing: dict
    provenance: dict


def prepare() -> GraphInputs:
    cfg = read_config()
    frame, columns, provenance = load_t19(cfg)
    x, preprocessing = transform_features(frame, columns, cfg, frame.split.eq("train").to_numpy())
    y, _ = labels_and_masks(frame, cfg["classes"])
    edges = pd.read_parquet(project_path(cfg["source_edges"]), columns=["time_window", "from_address", "to_address"])
    indexed_edges = {window: part for window, part in edges.groupby("time_window", sort=False)}
    result: dict[str, list[Data]] = {s: [] for s in ("train", "validation", "test")}
    for window, subset in frame.groupby("time_window", sort=False):
        split = subset.split.iloc[0]
        if split not in result:
            continue
        if not subset.split.eq(split).all():
            raise ValueError(f"mixed split within {window}")
        row_ids = subset.index.to_numpy()
        index = pd.Index(subset.address)
        group = indexed_edges.get(window)
        if group is None:
            raise ValueError(f"missing graph edges {window}")
        source = index.get_indexer(group.from_address)
        target = index.get_indexer(group.to_address)
        if (source < 0).any() or (target < 0).any():
            raise ValueError(f"edge endpoint absent from T19 nodes: {window}")
        pairs = np.vstack([np.r_[source, target], np.r_[target, source]]).astype(np.int64)
        if not len(np.unique(pairs, axis=1).T) == pairs.shape[1]:
            pairs = np.unique(pairs, axis=1)
        data = Data(x=torch.from_numpy(x[row_ids]), edge_index=torch.from_numpy(pairs),
                    y=torch.from_numpy(y[row_ids]), supervised=torch.from_numpy(np.flatnonzero(y[row_ids] >= 0)),
                    row_ids=torch.from_numpy(row_ids), window=window)
        result[split].append(data)
    if not all(result.values()):
        raise ValueError("empty graph split")
    return GraphInputs(frame, result, cfg["classes"], preprocessing, provenance)


class SnapshotGNN(nn.Module):
    def __init__(self, architecture: str, input_width: int, hidden: int, classes: int, heads: int = 2):
        super().__init__()
        self.architecture = architecture
        if architecture == "gcn":
            self.first = GCNConv(input_width, hidden)
            self.second = GCNConv(hidden, classes)
        elif architecture == "graphsage":
            self.first = SAGEConv(input_width, hidden)
            self.second = SAGEConv(hidden, classes)
        elif architecture == "gat":
            if hidden % heads:
                raise ValueError("GAT hidden width must divide attention heads")
            self.first = GATConv(input_width, hidden // heads, heads=heads, concat=True, dropout=0.0)
            self.second = GATConv(hidden, classes, heads=1, concat=False, dropout=0.0)
        else:
            raise ValueError(architecture)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor, *, return_hidden: bool = False):
        hidden = F.relu(self.first(x, edge_index))
        logits = self.second(hidden, edge_index)
        return (logits, hidden) if return_hidden else logits


def infer(model: SnapshotGNN, graphs: list[Data], classes: list[str]) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    model.eval()
    ids, probs, snapshots = [], [], []
    with torch.no_grad():
        for graph in graphs:
            logits, hidden = model(graph.x, graph.edge_index, return_hidden=True)
            label_nodes = graph.supervised.numpy()
            ids.extend(graph.row_ids.numpy()[label_nodes].tolist())
            probs.extend(torch.softmax(logits[label_nodes], dim=1).numpy())
            matrix = hidden.numpy()
            snapshots.append({"time_window": graph.window, "n_nodes": len(matrix), "n_edges_directed": graph.edge_index.shape[1],
                              **{f"mean_{j:02d}": float(matrix[:, j].mean()) for j in range(matrix.shape[1])},
                              **{f"std_{j:02d}": float(matrix[:, j].std()) for j in range(matrix.shape[1])}})
    return np.asarray(ids, dtype=np.int64), np.asarray(probs, dtype=np.float32), pd.DataFrame(snapshots)


def fit(inputs: GraphInputs, architecture: str, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    seed = int(cfg["seed"])
    seed_all(seed)
    option = cfg["gnn"]
    model = SnapshotGNN(architecture, 41, int(option["hidden"]), len(inputs.classes), int(option["attention_heads"]))
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(option["learning_rate"]), weight_decay=float(option["weight_decay"]))
    counts = np.bincount(np.concatenate([g.y[g.supervised].numpy() for g in inputs.graphs["train"]]), minlength=len(inputs.classes))
    n_train = counts.sum()
    weights = torch.tensor(n_train / (len(inputs.classes) * counts), dtype=torch.float32)
    criterion = nn.CrossEntropyLoss(weight=weights)
    best, best_epoch, waiting, best_state = -1.0, 0, 0, None
    rng = np.random.default_rng(seed)
    for epoch in range(1, int(option["max_epochs"]) + 1):
        model.train()
        for graph_i in rng.permutation(len(inputs.graphs["train"])):
            graph = inputs.graphs["train"][int(graph_i)]
            optimizer.zero_grad()
            logits = model(graph.x, graph.edge_index)
            loss = criterion(logits[graph.supervised], graph.y[graph.supervised])
            loss.backward()
            optimizer.step()
        val_ids, val_prob, _ = infer(model, inputs.graphs["validation"], inputs.classes)
        actual = inputs.frame.label_class.iloc[val_ids].map({x: i for i, x in enumerate(inputs.classes)}).to_numpy()
        value = score(actual, val_prob.argmax(1), inputs.classes)["macro_f1"]
        if value > best + 1e-8:
            best, best_epoch, waiting, best_state = value, epoch, 0, copy.deepcopy(model.state_dict())
        else:
            waiting += 1
            if waiting >= int(option["patience"]):
                break
    model.load_state_dict(best_state)
    predictions, metrics, embeddings = [], [], []
    _, _, train_snapshot = infer(model, inputs.graphs["train"], inputs.classes)
    train_snapshot["model"] = architecture
    train_snapshot["split"] = "train"
    embeddings.append(train_snapshot)
    for split in ("validation", "test"):
        ids, probability, snapshot = infer(model, inputs.graphs[split], inputs.classes)
        actual = inputs.frame.label_class.iloc[ids].map({x: i for i, x in enumerate(inputs.classes)}).to_numpy()
        estimated = probability.argmax(1)
        table = inputs.frame.iloc[ids][["time_window", "address", "label_class", "address_seen_in_train"]].copy()
        table["model"] = architecture
        table["split"] = split
        table["predicted_class"] = np.asarray(inputs.classes)[estimated]
        table["probability_cex"] = probability[:, 0]
        table["probability_dex"] = probability[:, 1]
        predictions.append(table)
        snapshot["model"] = architecture
        snapshot["split"] = split
        embeddings.append(snapshot)
        for scope, mask in (("all", np.ones(len(table), dtype=bool)), ("new_address", ~table.address_seen_in_train.to_numpy())):
            result = score(actual[mask], estimated[mask], inputs.classes)
            for class_name, stats in result["by_class"].items():
                metrics.append({"model": architecture, "split": split, "scope": scope, "class": class_name,
                                "n": result["n"], "macro_f1": result["macro_f1"], "accuracy": result["accuracy"], **stats})
    info = {"architecture": architecture, "best_epoch": best_epoch, "trained_epochs": epoch, "validation_macro_f1": best,
            "class_weight": weights.tolist(), "n_train_graphs": len(inputs.graphs["train"]),
            "n_validation_graphs": len(inputs.graphs["validation"]), "n_test_graphs": len(inputs.graphs["test"])}
    return pd.concat(predictions, ignore_index=True), pd.DataFrame(metrics), pd.concat(embeddings, ignore_index=True), info
