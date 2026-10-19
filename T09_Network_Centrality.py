
"""
T09 - Dynamic Network Centrality
On-chain Whale Contagion Analysis

Input:
    data/processed/graphs/dynamic_edges_daily.parquet
    data/processed/graphs/dynamic_edges_weekly.parquet

Metrics:
    Degree (in/out/total)
    Weighted Degree - USDT and transaction count
    Weighted PageRank

Output:
    data/processed/t09/node_metrics_daily.parquet
    data/processed/t09/node_metrics_weekly.parquet
    data/processed/t09/t09_summary.json
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent

INPUT_DIR = ROOT / "data/processed/graphs"
OUTPUT_DIR = ROOT / "data/processed/t09"

REQUIRED_COLUMNS = {
    "time_window",
    "from_address",
    "to_address",
    "total_value",
    "transaction_count",
}


def load_edges(window_type):

    path = INPUT_DIR / f"dynamic_edges_{window_type}.parquet"

    if not path.exists():
        raise FileNotFoundError(
            f"Missing T08 data: {path}"
        )

    df = pd.read_parquet(
        path,
        columns=list(REQUIRED_COLUMNS),
    )

    missing = REQUIRED_COLUMNS - set(df.columns)

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df["time_window"] = df["time_window"].astype(str)

    for col in ["from_address", "to_address"]:
        df[col] = (
            df[col].astype("string").str.lower().str.strip()
        )

    df["total_value"] = pd.to_numeric(
        df["total_value"], errors="raise"
    )

    df["transaction_count"] = pd.to_numeric(
        df["transaction_count"], errors="raise"
    )

    if df[
        ["time_window", "from_address", "to_address",
         "total_value", "transaction_count"]
    ].isna().any().any():
        raise ValueError("Missing values in T08 edges")

    if (
        (df["total_value"] < 0).any()
        or (df["transaction_count"] < 0).any()
    ):
        raise ValueError("Negative edge weights detected")

    # Preserve one directed edge per sender-receiver pair.
    df = df.groupby(
        ["time_window", "from_address", "to_address"],
        as_index=False,
        sort=False
    ).agg(
        total_value=("total_value", "sum"),
        transaction_count=("transaction_count", "sum"),
    )

    return df


def calculate_snapshot(sub, window_type, time_window):

    graph = nx.DiGraph()

    for row in sub.itertuples(index=False):

        graph.add_edge(
            row.from_address,
            row.to_address,
            total_value=float(row.total_value),
            transaction_count=float(row.transaction_count),
        )

    n_nodes = graph.number_of_nodes()
    n_edges = graph.number_of_edges()

    if n_nodes == 0:
        return pd.DataFrame(), {}

    # 1. Unweighted Degree
    in_degree = dict(graph.in_degree())
    out_degree = dict(graph.out_degree())

    # 2. USDT Weighted Degree
    in_strength = dict(
        graph.in_degree(weight="total_value")
    )

    out_strength = dict(
        graph.out_degree(weight="total_value")
    )

    # 3. Transaction Frequency Weighted Degree
    in_tx = dict(
        graph.in_degree(weight="transaction_count")
    )

    out_tx = dict(
        graph.out_degree(weight="transaction_count")
    )

    # 4. Weighted PageRank
    # If a snapshot has no positive value, use unweighted
    # PageRank to avoid a zero-weight transition matrix.
    has_positive_value = (
        sub["total_value"] > 0
    ).any()

    weight_name = (
        "total_value" if has_positive_value else None
    )

    try:
        pagerank = nx.pagerank(
            graph,
            alpha=0.85,
            weight=weight_name,
            max_iter=200,
            tol=1e-8,
        )

        pr_status = "converged"

    except nx.PowerIterationFailedConvergence:

        pagerank = nx.pagerank(
            graph,
            alpha=0.85,
            weight=weight_name,
            max_iter=1000,
            tol=1e-6,
        )

        pr_status = "converged_retry"

    records = []

    for address in graph.nodes():

        incoming = float(in_strength[address])
        outgoing = float(out_strength[address])

        incoming_tx = float(in_tx[address])
        outgoing_tx = float(out_tx[address])

        records.append({
            "window_type": window_type,
            "time_window": str(time_window),
            "address": address,

            "in_degree": int(in_degree[address]),
            "out_degree": int(out_degree[address]),
            "degree": int(
                in_degree[address] + out_degree[address]
            ),

            "in_strength_usdt": incoming,
            "out_strength_usdt": outgoing,
            "weighted_degree_usdt": incoming + outgoing,

            "in_tx_count": incoming_tx,
            "out_tx_count": outgoing_tx,
            "weighted_degree_tx": incoming_tx + outgoing_tx,

            "net_inflow_usdt": incoming - outgoing,

            "pagerank": float(pagerank[address]),
        })

    result = pd.DataFrame(records)

    stats = {
        "window_type": window_type,
        "time_window": str(time_window),
        "num_nodes": n_nodes,
        "num_edges": n_edges,
        "total_volume_usdt": float(
            sub["total_value"].sum()
        ),
        "pagerank_sum": float(
            sum(pagerank.values())
        ),
        "pagerank_status": pr_status,
        "pagerank_weight": (
            "total_value" if has_positive_value
            else "unweighted_fallback"
        ),
    }

    return result, stats


def process_window(window_type, max_windows, output_dir):

    print(f"\n===== T09 {window_type.upper()} =====")

    edges = load_edges(window_type)

    print("Edges:", f"{len(edges):,}")

    grouped = edges.groupby(
        "time_window", sort=True
    )

    windows = sorted(edges["time_window"].unique())

    if max_windows > 0:
        windows = windows[:max_windows]

    print("Snapshots to process:", len(windows))

    results = []
    snapshot_stats = []

    for i, window in enumerate(windows, 1):

        sub = grouped.get_group(window)

        metrics, stats = calculate_snapshot(
            sub, window_type, window
        )

        if not metrics.empty:
            results.append(metrics)

        snapshot_stats.append(stats)

        if (
            i == 1
            or i % 10 == 0
            or i == len(windows)
        ):
            print(
                f"[{i}/{len(windows)}] "
                f"{window} | "
                f"nodes={stats['num_nodes']:,} | "
                f"edges={stats['num_edges']:,} | "
                f"PageRank={stats['pagerank_status']}",
                flush=True,
            )

    if not results:
        raise RuntimeError("No node metrics generated")

    final = pd.concat(results, ignore_index=True)

    output_dir.mkdir(
        parents=True, exist_ok=True
    )

    output_path = (
        output_dir /
        f"node_metrics_{window_type}.parquet"
    )

    final.to_parquet(
        output_path,
        index=False,
    )

    # Keep detailed snapshot-level statistics.
    snapshot_path = (
        output_dir /
        f"snapshot_metrics_{window_type}.csv"
    )

    pd.DataFrame(snapshot_stats).to_csv(
        snapshot_path,
        index=False,
        encoding="utf-8-sig",
    )

    # Validation
    assert not final.duplicated(
        ["window_type", "time_window", "address"]
    ).any()

    assert np.isfinite(
        final["pagerank"]
    ).all()

    assert np.allclose(
        final["weighted_degree_usdt"],
        final["in_strength_usdt"]
        + final["out_strength_usdt"],
    )

    print("Node metric rows:", f"{len(final):,}")
    print("Saved:", output_path)

    return {
        "snapshots": len(windows),
        "node_metric_rows": len(final),
        "output_file": str(output_path),
        "snapshot_metrics_file": str(snapshot_path),
        "pagerank_retry_snapshots": sum(
            s["pagerank_status"] == "converged_retry"
            for s in snapshot_stats
        ),
    }


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--window",
        choices=["daily", "weekly", "both"],
        default="both",
    )

    parser.add_argument(
        "--max-windows",
        type=int,
        default=0,
        help="0 = process all snapshots",
    )

    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
    )

    args = parser.parse_args()

    if args.max_windows < 0:
        parser.error("--max-windows must be >= 0")

    output_dir = Path(args.output_dir)

    print("=" * 60)
    print("TASK T09 - DYNAMIC NETWORK CENTRALITY")
    print("=" * 60)

    modes = (
        ["daily", "weekly"]
        if args.window == "both"
        else [args.window]
    )

    summary = {
        "task": "T09",
        "metrics": [
            "degree",
            "weighted_degree_usdt",
            "weighted_degree_tx",
            "pagerank",
        ],
        "pagerank_alpha": 0.85,
        "pagerank_weight": "total_value",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "results": {},
    }

    for mode in modes:

        summary["results"][mode] = process_window(
            mode,
            args.max_windows,
            output_dir,
        )

    summary_path = (
        output_dir / "t09_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\n===== T09 COMPLETED =====")
    print("Summary:", summary_path)


if __name__ == "__main__":
    main()
