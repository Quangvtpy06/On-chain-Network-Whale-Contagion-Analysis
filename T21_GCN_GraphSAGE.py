"""T21: GCN and GraphSAGE on disjoint weekly graph snapshots."""
import json

import pandas as pd

from src.graph_config import ROOT
from src.stage4_common import read_config, save_json, sha256
from src.stage4_gnn import fit, prepare


def main():
    cfg = read_config()
    inputs = prepare()
    output = ROOT / "data/processed/t21"
    output.mkdir(parents=True, exist_ok=True)
    predictions, metrics, embeddings, training = [], [], [], {}
    for architecture in ("gcn", "graphsage"):
        p, m, e, info = fit(inputs, architecture, cfg)
        predictions.append(p)
        metrics.append(m)
        embeddings.append(e)
        training[architecture] = info
    all_predictions = pd.concat(predictions, ignore_index=True)
    all_metrics = pd.concat(metrics, ignore_index=True)
    all_embeddings = pd.concat(embeddings, ignore_index=True)
    for name, frame in (("predictions", all_predictions), ("metrics", all_metrics), ("snapshot_embeddings", all_embeddings)):
        frame.to_parquet(output / f"t21_{name}.parquet", index=False)
    valid = not all_predictions.duplicated(["model", "split", "time_window", "address"]).any()
    if not valid:
        raise ValueError("duplicate T21 prediction key")
    summary = {"protocol_id": cfg["protocol_id"], "validation_pass": valid, "scope": "weekly retrospective CEX/DEX snapshot classification",
               "source": inputs.provenance, "training": training,
               "outputs": {name: sha256(output / name) for name in
                           ("t21_predictions.parquet", "t21_metrics.parquet", "t21_snapshot_embeddings.parquet")}}
    save_json(output / "t21_summary.json", summary)
    print(json.dumps({"validation_pass": valid, "training": training}, ensure_ascii=False))


if __name__ == "__main__":
    main()
