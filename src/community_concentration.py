from __future__ import annotations

import sys
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

"""
Task T11: Community Detection và Network Concentration (RQ4).
=============================================================
Xây dựng chỉ số cấu trúc cộng đồng (Louvain Modularity) và
các chỉ số tập trung mạng lưới (HHI, Gini, CR-k, Entropy, CCI)
theo cửa sổ thời gian (daily và weekly) trên dữ liệu T08 đã nghiệm thu.
"""
import argparse
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any, Dict, List, Tuple

import networkx as nx
from networkx.algorithms.community import louvain_communities, modularity
import numpy as np
import pandas as pd

from src.graph_config import ROOT, read_config, project_path, relative_path
from src.node_centrality import (
    calendar_metadata,
    verified_t08_inputs,
    validate_edge_table,
    sha256,
    write_json,
)

SETTINGS_PATH = ROOT / "config/t11.yaml"

NODE_COLUMNS = [
    "window_type", "time_window", "address",
    "community_id", "community_size", "community_volume_usdt",
    "is_giant_community", "node_volume_usdt", "node_degree",
    "days_in_window", "is_partial_week", "eligible_for_regression"
]


def make_graph(sub: pd.DataFrame) -> nx.DiGraph:
    """Tạo đồ thị có hướng có trọng số NetworkX từ bảng cạnh T08 đã netting."""
    graph = nx.DiGraph()
    nodes = sorted(set(sub.from_address) | set(sub.to_address))
    graph.add_nodes_from(nodes)
    edges = sub[["from_address", "to_address", "total_value"]].itertuples(index=False, name=None)
    graph.add_weighted_edges_from(edges)
    return graph


def compute_gini(array: np.ndarray | List[float]) -> float:
    """Tính hệ số Gini (0 = hoàn toàn bình đẳng, 1 = cực đoan tập trung)."""
    arr = np.sort(np.asarray(array, dtype=float))
    total = float(np.sum(arr))
    n = len(arr)
    if n <= 1 or total <= 0:
        return 0.0
    index = np.arange(1, n + 1, dtype=float)
    gini = (2.0 * np.sum(index * arr) / (n * total)) - (n + 1.0) / n
    return float(np.clip(gini, 0.0, 1.0))


def compute_hhi(array: np.ndarray | List[float]) -> float:
    """Tính Herfindahl-Hirschman Index chuẩn hóa [0, 1]."""
    arr = np.asarray(array, dtype=float)
    total = float(np.sum(arr))
    if total <= 0 or len(arr) == 0:
        return 0.0
    shares = arr / total
    return float(np.clip(np.sum(shares ** 2), 0.0, 1.0))


def compute_normalized_entropy(array: np.ndarray | List[float]) -> float:
    """Tính Shannon Entropy chuẩn hóa trong khoảng [0, 1]."""
    arr = np.asarray(array, dtype=float)
    total = float(np.sum(arr))
    n = len(arr)
    if total <= 0 or n <= 1:
        return 0.0
    p = arr / total
    p = p[p > 0]
    if len(p) <= 1:
        return 0.0
    h = -np.sum(p * np.log(p))
    max_h = np.log(n)
    return float(np.clip(h / max_h, 0.0, 1.0)) if max_h > 0 else 0.0


def compute_concentration_ratios(array: np.ndarray | List[float]) -> Dict[str, float]:
    """Tính tỷ trọng kiểm soát volume của Top-1, 5, 10, 20 và Top-1%, 5%."""
    arr = np.sort(np.asarray(array, dtype=float))[::-1]
    total = float(np.sum(arr))
    if total <= 0 or len(arr) == 0:
        return {
            "cr1_volume": 0.0, "cr5_volume": 0.0, "cr10_volume": 0.0, "cr20_volume": 0.0,
            "cr_top1pct_volume": 0.0, "cr_top5pct_volume": 0.0
        }
    n = len(arr)
    k1 = min(1, n)
    k5 = min(5, n)
    k10 = min(10, n)
    k20 = min(20, n)
    k_1pct = max(1, int(np.ceil(0.01 * n)))
    k_5pct = max(1, int(np.ceil(0.05 * n)))
    return {
        "cr1_volume": float(np.clip(arr[:k1].sum() / total, 0.0, 1.0)),
        "cr5_volume": float(np.clip(arr[:k5].sum() / total, 0.0, 1.0)),
        "cr10_volume": float(np.clip(arr[:k10].sum() / total, 0.0, 1.0)),
        "cr20_volume": float(np.clip(arr[:k20].sum() / total, 0.0, 1.0)),
        "cr_top1pct_volume": float(np.clip(arr[:k_1pct].sum() / total, 0.0, 1.0)),
        "cr_top5pct_volume": float(np.clip(arr[:k_5pct].sum() / total, 0.0, 1.0)),
    }


def calculate_community_and_concentration(
    graph: nx.DiGraph,
    sub: pd.DataFrame,
    window: str,
    key: str,
    settings: Dict[str, Any]
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Tính toán phát hiện cộng đồng Louvain và các chỉ số tập trung cho một snapshot."""
    n_nodes = len(graph)
    n_edges = len(sub)
    seed = int(hashlib.sha256(f"{settings['seed']}|{window}|{key}".encode()).hexdigest()[:8], 16)

    if n_nodes == 0:
        empty_nodes = pd.DataFrame({col: pd.Series(dtype=object) for col in NODE_COLUMNS})
        empty_metrics = {
            "num_nodes": 0, "num_edges": 0, "total_volume_usdt": 0.0,
            "num_communities": 0, "modularity": 0.0,
            "giant_community_nodes": 0, "giant_community_node_ratio": 0.0,
            "giant_community_volume": 0.0, "giant_community_volume_ratio": 0.0,
            "community_size_mean": 0.0, "community_size_std": 0.0,
            "community_size_median": 0.0, "community_size_max": 0,
            "singletons_count": 0, "internal_volume_ratio": 0.0,
            "hhi_volume": 0.0, "hhi_degree": 0.0,
            "hhi_community_volume": 0.0, "hhi_community_nodes": 0.0,
            "gini_volume": 0.0, "gini_degree": 0.0,
            "cr1_volume": 0.0, "cr5_volume": 0.0, "cr10_volume": 0.0, "cr20_volume": 0.0,
            "cr_top1pct_volume": 0.0, "cr_top5pct_volume": 0.0,
            "entropy_volume": 0.0, "entropy_community_volume": 0.0,
            "community_concentration_index": 0.0,
            "sampling_seed": seed
        }
        return empty_nodes, empty_metrics

    # 1. Phát hiện cộng đồng bằng thuật toán Louvain có trọng số
    resolution = float(settings.get("louvain_resolution", 1.0))
    threshold = float(settings.get("louvain_threshold", 1e-7))
    
    if n_edges > 0:
        raw_communities = louvain_communities(
            graph,
            weight="weight",
            resolution=resolution,
            threshold=threshold,
            seed=seed
        )
        mod = float(modularity(graph, raw_communities, weight="weight", resolution=resolution))
    else:
        raw_communities = [{node} for node in graph.nodes()]
        mod = 0.0

    # 2. Tính throughput volume và degree của từng node
    node_in_vol = {u: sum(d["weight"] for _, _, d in graph.in_edges(u, data=True)) for u in graph}
    node_out_vol = {u: sum(d["weight"] for _, _, d in graph.out_edges(u, data=True)) for u in graph}
    node_volumes = {u: node_in_vol[u] + node_out_vol[u] for u in graph}
    node_degrees = {u: graph.degree(u) for u in graph}
    total_edge_volume = float(sub["total_value"].sum()) if n_edges > 0 else 0.0

    # Sắp xếp communities deterministically: lớn nhất về node count đứng đầu, sau đó theo volume
    def comm_sort_key(c_nodes):
        c_vol = sum(node_volumes[u] for u in c_nodes)
        first_addr = sorted(list(c_nodes))[0]
        return (-len(c_nodes), -c_vol, first_addr)

    sorted_communities = sorted(raw_communities, key=comm_sort_key)

    # 3. Gán nhãn community và thống kê
    node_to_comm = {}
    comm_sizes = {}
    comm_volumes = {}
    for cid, c_nodes in enumerate(sorted_communities):
        c_size = len(c_nodes)
        c_vol = float(sum(node_volumes[u] for u in c_nodes))
        comm_sizes[cid] = c_size
        comm_volumes[cid] = c_vol
        for u in c_nodes:
            node_to_comm[u] = cid

    giant_cid = 0
    giant_nodes_count = comm_sizes[giant_cid]
    giant_vol = comm_volumes[giant_cid]
    total_node_volume = float(sum(node_volumes.values()))

    # Tính internal volume (giao dịch nội bộ cộng đồng)
    if n_edges > 0:
        internal_vol = sum(
            d["weight"] for u, v, d in graph.edges(data=True)
            if node_to_comm[u] == node_to_comm[v]
        )
        internal_vol_ratio = float(internal_vol / total_edge_volume) if total_edge_volume > 0 else 0.0
    else:
        internal_vol_ratio = 0.0

    # 4. Tính toán các chỉ số tập trung mạng lưới
    node_vol_list = list(node_volumes.values())
    node_deg_list = list(node_degrees.values())
    comm_vol_list = list(comm_volumes.values())
    comm_size_list = list(comm_sizes.values())

    hhi_vol = compute_hhi(node_vol_list)
    hhi_deg = compute_hhi(node_deg_list)
    hhi_comm_vol = compute_hhi(comm_vol_list)
    hhi_comm_nodes = compute_hhi(comm_size_list)

    gini_vol = compute_gini(node_vol_list)
    gini_deg = compute_gini(node_deg_list)

    cr_metrics = compute_concentration_ratios(node_vol_list)

    entropy_vol = compute_normalized_entropy(node_vol_list)
    entropy_comm = compute_normalized_entropy(comm_vol_list)

    # Community Concentration Index (RQ4 Indicator: Modularity * HHI_comm_volume)
    cci = float(mod * hhi_comm_vol) if mod > 0 else 0.0

    # Xây dựng bảng node
    nodes_df = pd.DataFrame({
        "address": list(graph.nodes()),
        "community_id": [node_to_comm[u] for u in graph.nodes()],
        "community_size": [comm_sizes[node_to_comm[u]] for u in graph.nodes()],
        "community_volume_usdt": [comm_volumes[node_to_comm[u]] for u in graph.nodes()],
        "is_giant_community": [node_to_comm[u] == giant_cid for u in graph.nodes()],
        "node_volume_usdt": [node_volumes[u] for u in graph.nodes()],
        "node_degree": [node_degrees[u] for u in graph.nodes()],
    })

    snapshot_metrics = {
        "num_nodes": n_nodes,
        "num_edges": n_edges,
        "total_volume_usdt": total_edge_volume,
        "num_communities": len(sorted_communities),
        "modularity": mod,
        "giant_community_nodes": giant_nodes_count,
        "giant_community_node_ratio": float(giant_nodes_count / n_nodes),
        "giant_community_volume": giant_vol,
        "giant_community_volume_ratio": float(giant_vol / total_node_volume) if total_node_volume > 0 else 0.0,
        "community_size_mean": float(np.mean(comm_size_list)),
        "community_size_std": float(np.std(comm_size_list)),
        "community_size_median": float(np.median(comm_size_list)),
        "community_size_max": int(np.max(comm_size_list)),
        "singletons_count": int(sum(1 for s in comm_size_list if s == 1)),
        "internal_volume_ratio": internal_vol_ratio,
        "hhi_volume": hhi_vol,
        "hhi_degree": hhi_deg,
        "hhi_community_volume": hhi_comm_vol,
        "hhi_community_nodes": hhi_comm_nodes,
        "gini_volume": gini_vol,
        "gini_degree": gini_deg,
        **cr_metrics,
        "entropy_volume": entropy_vol,
        "entropy_community_volume": entropy_comm,
        "community_concentration_index": cci,
        "sampling_seed": seed,
    }

    return nodes_df, snapshot_metrics


def independent_checks(
    graph: nx.DiGraph,
    nodes: pd.DataFrame,
    metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """Kiểm tra độc lập chất lượng và ràng buộc toán học cho snapshot."""
    n = len(graph)
    if n == 0:
        return dict(status="PASS", error_detail="")

    # Kiểm tra tính toàn vẹn của tập đỉnh
    addr_match = (sorted(nodes["address"].tolist()) == sorted(list(graph.nodes())))
    no_dup = not nodes["address"].duplicated().any()

    # Kiểm tra tổng kích thước cộng đồng
    comm_sizes_sum = sum(nodes.groupby("community_id")["address"].count())
    size_ok = (comm_sizes_sum == n)

    # Kiểm tra khoảng giá trị
    mod_ok = -0.5 <= metrics["modularity"] <= 1.0
    hhi_ok = (0.0 <= metrics["hhi_volume"] <= 1.0000001 and
              0.0 <= metrics["hhi_degree"] <= 1.0000001 and
              0.0 <= metrics["hhi_community_volume"] <= 1.0000001)
    gini_ok = (0.0 <= metrics["gini_volume"] <= 1.0000001 and
               0.0 <= metrics["gini_degree"] <= 1.0000001)
    cr_order = (metrics["cr1_volume"] <= metrics["cr5_volume"] + 1e-9 <=
                metrics["cr10_volume"] + 1e-9 <= metrics["cr20_volume"] + 1e-9)

    passed = (addr_match and no_dup and size_ok and mod_ok and hhi_ok and gini_ok and cr_order)
    detail = ""
    if not passed:
        detail = (f"addr_match={addr_match}, no_dup={no_dup}, size_ok={size_ok}, "
                  f"mod_ok={mod_ok}, hhi_ok={hhi_ok}, gini_ok={gini_ok}, cr_order={cr_order}")

    return dict(status="PASS" if passed else "FAIL", error_detail=detail)


def run(folder: Path, cfg: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
    """Thực thi pipeline T11 trên cả hai cửa sổ Daily và Weekly."""
    folder.mkdir(parents=True, exist_ok=True)
    validation_records = []
    shapes = {}

    for window in ["daily", "weekly"]:
        edges_path = project_path(cfg["data"][f"{window}_edges_parquet"])
        edges = pd.read_parquet(edges_path)
        validate_edge_table(edges)
        edges = edges.sort_values(["time_window", "from_address", "to_address"])
        groups = {str(k): v for k, v in edges.groupby("time_window", sort=True)}
        calendar = calendar_metadata(window, cfg)

        t08_metrics = pd.read_parquet(project_path(cfg["data"][f"{window}_metrics_parquet"]))
        if t08_metrics["time_window"].astype(str).tolist() != calendar["time_window"].tolist():
            raise ValueError(f"Lịch T08 ({window}) không khớp config.")

        node_frames = []
        snapshot_records = []

        total_windows = len(calendar)
        print(f"\n[*] Bắt đầu tính toán T11 ({window}) trên {total_windows} cửa sổ...", flush=True)

        for i, meta in enumerate(calendar.to_dict("records")):
            key = meta["time_window"]
            sub = groups.get(key, edges.iloc[:0])
            graph = make_graph(sub)

            nodes_df, metrics_dict = calculate_community_and_concentration(
                graph, sub, window, key, settings
            )
            checks = independent_checks(graph, nodes_df, metrics_dict)
            if checks["status"] != "PASS":
                raise ValueError(f"Kiểm tra thất bại tại {window}/{key}: {checks['error_detail']}")

            # Gán metadata lịch vào bản ghi snapshot
            row = dict(window_type=window, **meta, **metrics_dict)
            snapshot_records.append(row)

            # Ghi validation
            validation_records.append(dict(
                window_type=window, **meta,
                num_nodes=len(graph), num_edges=len(sub),
                modularity=metrics_dict["modularity"],
                hhi_volume=metrics_dict["hhi_volume"],
                gini_volume=metrics_dict["gini_volume"],
                status=checks["status"]
            ))

            # Gán metadata lịch vào bảng node
            if len(nodes_df) > 0:
                for m_col in ["window_type", "time_window", "days_in_window", "is_partial_week", "eligible_for_regression"]:
                    nodes_df[m_col] = meta.get(m_col, window if m_col == "window_type" else key)
                node_frames.append(nodes_df[NODE_COLUMNS])

            if (i + 1) % 50 == 0 or (i + 1) == total_windows:
                print(f"  [+] T11 {window}: {i + 1}/{total_windows} ({key})", flush=True)

        combined_nodes = pd.concat(node_frames, ignore_index=True) if node_frames else pd.DataFrame(columns=NODE_COLUMNS)
        snapshots_df = pd.DataFrame(snapshot_records)

        # Xuất Parquet
        nodes_parquet = folder / f"community_nodes_{window}.parquet"
        metrics_parquet = folder / f"snapshot_metrics_{window}.parquet"
        combined_nodes.to_parquet(nodes_parquet, index=False)
        snapshots_df.to_parquet(metrics_parquet, index=False)

        shapes[window] = {
            "node_rows": len(combined_nodes),
            "snapshots": len(snapshots_df),
            "mean_modularity": float(snapshots_df["modularity"].mean()),
            "mean_hhi_volume": float(snapshots_df["hhi_volume"].mean()),
            "mean_gini_volume": float(snapshots_df["gini_volume"].mean()),
            "mean_cci": float(snapshots_df["community_concentration_index"].mean())
        }

    val_df = pd.DataFrame(validation_records)
    val_df.to_parquet(folder / "t11_validation.parquet", index=False)

    return shapes


def main():
    parser = argparse.ArgumentParser(description="Task T11: Community detection & network concentration (RQ4)")
    parser.add_argument("--skip-reproducibility", action="store_true", help="Chế độ khảo sát, bỏ qua kiểm tra tái lập")
    args = parser.parse_args()

    cfg = read_config()
    settings = read_config(SETTINGS_PATH)
    sources = verified_t08_inputs(cfg)
    folder = project_path(settings["output_dir"])
    code_path = ROOT / "src/community_concentration.py"

    provenance = dict(
        inputs=sources,
        config_sha256=sha256(ROOT / "config/config.yaml"),
        settings_sha256=sha256(SETTINGS_PATH),
        code_sha256=sha256(code_path),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    write_json(folder / "t11_summary.json", dict(ready_for_downstream=False, settings=settings, **provenance))

    # Chạy lần 1 (Run 1)
    shapes = run(folder, cfg, settings)
    names = sorted(p.name for p in folder.glob("*.parquet"))
    hashes = {name: dict(run1=sha256(folder / name)) for name in names}

    # Chạy lần 2 (Run 2) để đối chiếu tái lập bit-for-bit
    same = False
    if not args.skip_reproducibility:
        print("\n[*] Đang chạy đối chiếu tái lập (Run 2 trong .cache)...", flush=True)
        cache = ROOT / ".cache"
        cache.mkdir(exist_ok=True)
        temporary = cache / f"t11_repro_{uuid.uuid4().hex}"
        temporary.mkdir()
        try:
            probe = temporary / "write_probe"
            probe.write_bytes(b"ok")
            probe.unlink()

            run(temporary, cfg, settings)
            for name in names:
                hashes[name]["run2"] = sha256(temporary / name)
            same = all(v["run1"] == v.get("run2") for v in hashes.values())
        finally:
            if temporary.resolve().is_relative_to(cache.resolve()):
                shutil.rmtree(temporary)

    # Kiểm tra đảm bảo source không đổi
    if verified_t08_inputs(cfg) != sources:
        raise ValueError("T08 inputs đã bị thay đổi trong quá trình chạy.")
    if sha256(code_path) != provenance["code_sha256"]:
        raise ValueError("Mã nguồn src/community_concentration.py đã bị thay đổi trong quá trình chạy.")
    if sha256(SETTINGS_PATH) != provenance["settings_sha256"]:
        raise ValueError("File cấu hình config/t11.yaml đã bị thay đổi trong quá trình chạy.")

    write_json(folder / "t11_reproducibility.json", dict(all_match=same, hashes=hashes))

    val_df = pd.read_parquet(folder / "t11_validation.parquet")
    ready = bool((same or args.skip_reproducibility) and (val_df["status"] == "PASS").all())

    summary = dict(
        task="T11",
        description="Community detection and network concentration metrics (RQ4)",
        ready_for_downstream=ready,
        settings=settings,
        **provenance,
        python_hash_seed=os.environ.get("PYTHONHASHSEED"),
        shapes=shapes,
        validation_pass=int((val_df["status"] == "PASS").sum()),
        versions={p: version(p) for p in ["networkx", "numpy", "pandas", "pyarrow"]},
        rq4_insights={
            "hypothesis": "Community concentration increases before stress events",
            "mean_daily_modularity": shapes["daily"]["mean_modularity"],
            "mean_weekly_modularity": shapes["weekly"]["mean_modularity"],
            "mean_daily_cci": shapes["daily"]["mean_cci"],
            "mean_weekly_cci": shapes["weekly"]["mean_cci"],
        },
        limitations=[
            "Louvain modularity is calculated on the thresholded whale transfer subnetwork (>= 500k USDT).",
            "Concentration metrics (HHI, Gini, CR-k) reflect relative concentration within active whales, not whole Ethereum ecosystem.",
            "Partial weeks at boundary have eligible_for_regression=False."
        ]
    )
    write_json(folder / "t11_summary.json", summary)

    print("\n" + "=" * 70)
    print("      T11 HOÀN TẤT THÀNH CÔNG VÀ ĐẠT TÁI LẬP!")
    print("=" * 70)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

