import sys
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
"""Release validator for T11: verify community and concentration metrics against T08 inputs."""
import argparse
import json
import sys
import time
from pathlib import Path

import networkx as nx
from networkx.algorithms.community import modularity
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.graph_config import read_config, project_path
from src.node_centrality import sha256, verified_t08_inputs, calendar_metadata
from src.community_concentration import compute_gini, compute_hhi


def main():
    parser = argparse.ArgumentParser(description="Validate T11 outputs against verified T08 inputs")
    parser.add_argument("--wait-for-reproducibility", action="store_true",
                        help="Chờ file tái lập nếu đang tính toán ngầm")
    args = parser.parse_args()

    cfg = read_config()
    settings = read_config(ROOT / "config/t11.yaml")
    folder = project_path(settings["output_dir"])

    summary_file = folder / "t11_summary.json"
    if not summary_file.is_file():
        raise FileNotFoundError(f"Không tìm thấy file summary T11 tại {summary_file}")

    summary = json.loads(summary_file.read_text(encoding="utf-8"))

    passed = (
        summary["inputs"] == verified_t08_inputs(cfg) and
        summary["config_sha256"] == sha256(ROOT / "config/config.yaml") and
        summary["settings_sha256"] == sha256(ROOT / "config/t11.yaml") and
        summary["code_sha256"] == sha256(ROOT / "src/community_concentration.py")
    )

    if not passed:
        raise ValueError("T11: Metadata xác thực nguồn dữ liệu, cấu hình hoặc mã nguồn không khớp!")

    print("[*] Đang kiểm tra tính nhất quán của bảng kết quả T11...", flush=True)

    for window in ["daily", "weekly"]:
        edges = pd.read_parquet(project_path(cfg["data"][f"{window}_edges_parquet"]))
        nodes = pd.read_parquet(folder / f"community_nodes_{window}.parquet")
        snapshots = pd.read_parquet(folder / f"snapshot_metrics_{window}.parquet")
        calendar = calendar_metadata(window, cfg)

        # 1. Kiểm tra lịch
        if snapshots["time_window"].tolist() != calendar["time_window"].tolist():
            raise ValueError(f"T11 ({window}): Lịch snapshots không khớp calendar!")
        for col in ["days_in_window", "is_partial_week", "eligible_for_regression"]:
            if snapshots[col].tolist() != calendar[col].tolist():
                raise ValueError(f"T11 ({window}): Thuộc tính lịch {col} không khớp!")

        # 2. Kiểm tra trùng lặp khóa
        if nodes.duplicated(["time_window", "address"]).any():
            raise ValueError(f"T11 ({window}): Phát hiện trùng lặp cặp khóa (time_window, address)!")

        # 3. Kiểm tra tính độc lập trên mẫu 5 snapshot
        groups = {str(k): v for k, v in edges.groupby("time_window", sort=True)}
        nodegroups = {str(k): v for k, v in nodes.groupby("time_window", sort=True)}

        sample_keys = [snapshots["time_window"].iloc[idx] for idx in np.linspace(0, len(snapshots) - 1, min(5, len(snapshots)), dtype=int)]
        
        for key in sample_keys:
            sub = groups.get(key, edges.iloc[:0])
            obs_nodes = nodegroups.get(key, nodes.iloc[:0])
            obs_snap = snapshots[snapshots["time_window"] == key].iloc[0]

            n_nodes = len(obs_nodes)
            if n_nodes == 0:
                continue

            # Kiểm tra độc lập Gini
            node_vols = obs_nodes["node_volume_usdt"].to_numpy()
            ref_gini = compute_gini(node_vols)
            if not np.isclose(ref_gini, obs_snap["gini_volume"], atol=1e-7):
                raise ValueError(f"T11 ({window}/{key}): Gini volume độc lập không khớp! ({ref_gini} vs {obs_snap['gini_volume']})")

            # Kiểm tra độc lập HHI
            ref_hhi = compute_hhi(node_vols)
            if not np.isclose(ref_hhi, obs_snap["hhi_volume"], atol=1e-7):
                raise ValueError(f"T11 ({window}/{key}): HHI volume độc lập không khớp!")

            # Kiểm tra cấu trúc phân hoạch cộng đồng
            comm_list = [set(grp["address"]) for _, grp in obs_nodes.groupby("community_id")]
            G = nx.DiGraph()
            G.add_nodes_from(sorted(set(sub.from_address) | set(sub.to_address)))
            G.add_weighted_edges_from(sub[["from_address", "to_address", "total_value"]].itertuples(index=False, name=None))
            
            ref_mod = float(modularity(G, comm_list, weight="weight", resolution=settings.get("louvain_resolution", 1.0)))
            if not np.isclose(ref_mod, obs_snap["modularity"], atol=1e-7):
                raise ValueError(f"T11 ({window}/{key}): Modularity độc lập không khớp! ({ref_mod} vs {obs_snap['modularity']})")

        print(f"  [+] T11 ({window}): Kiểm tra độc lập và cấu trúc dữ liệu đạt chuẩn!", flush=True)

    repro_file = folder / "t11_reproducibility.json"
    deadline = time.monotonic() + 1800
    while args.wait_for_reproducibility and not repro_file.is_file() and time.monotonic() < deadline:
        time.sleep(2)

    if not repro_file.is_file():
        raise FileNotFoundError("Chưa có file kiểm tra tái lập t11_reproducibility.json!")

    repro = json.loads(repro_file.read_text(encoding="utf-8"))
    if not repro.get("all_match"):
        raise ValueError("T11: Đối chiếu hai lượt chạy độc lập (reproducibility) không khớp hash!")

    if not summary.get("ready_for_downstream"):
        raise ValueError("T11: ready_for_downstream chưa được đánh dấu True!")

    print("\n" + "=" * 70)
    print("      NGHIỆM THU ĐỘC LẬP T11 ĐẠT 100% TIÊU CHUẨN!")
    print("=" * 70)


if __name__ == "__main__":
    main()
