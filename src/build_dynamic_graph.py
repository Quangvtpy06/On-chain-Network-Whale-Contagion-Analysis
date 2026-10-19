"""
Task T08: Xây dựng Dynamic Transaction Graph (G_t)
- Người thực hiện: TV1 - Yến Vy
- Reviewer: TV4 / Hương
- Tiền đề: T05 (data/interim/usdt_whale_transfers_interim.parquet)

Đặc tả kỹ thuật:
- Chuỗi đồ thị có hướng G_t = (V_t, E_t) theo cửa sổ thời gian (daily và weekly).
- Cạnh có hướng (u -> v) với trọng số:
    + total_value: Tổng giá trị token chuyển giao (sum of amount USDT).
    + transaction_count: Số lượng giao dịch chuyển giao (count of transfer events).
    + mean_value: Giá trị trung bình mỗi giao dịch.
    + min_value, max_value: Giá trị giao dịch nhỏ nhất và lớn nhất.
- Node attributes:
    + in_degree, out_degree
    + in_volume, out_volume
    + Tích hợp nhãn thực thể từ T07 (CEX, DEX, DeFi,...) nếu có.
- Xuất file kết quả chuẩn hóa vào: data/processed/graphs/
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import networkx as nx

# Fix encoding cho Windows console
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Cấu hình đường dẫn mặc định
DEFAULT_INPUT_PARQUET = Path("data/interim/usdt_whale_transfers_interim.parquet")
DEFAULT_LABELS_CSV = Path("data/external/t07_verified_labels.csv")
DEFAULT_OUTPUT_DIR = Path("data/processed/graphs")


def load_normalized_transfers(path: Path) -> pd.DataFrame:
    """Đọc dữ liệu transfer đã chuẩn hóa từ Task T05."""
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file dữ liệu: {path}")
    
    print(f"[*] Đang nạp dữ liệu từ: {path}...")
    df = pd.read_parquet(path)
    required_cols = {"from_address", "to_address", "amount", "block_timestamp"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Dữ liệu thiếu các cột bắt buộc: {missing}")
    
    # Đảm bảo kiểu dữ liệu chuẩn
    df["from_address"] = df["from_address"].astype(str).str.lower().str.strip()
    df["to_address"] = df["to_address"].astype(str).str.lower().str.strip()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["block_timestamp"] = pd.to_datetime(df["block_timestamp"], utc=True)
    
    # Tạo các cột chuỗi thời gian
    if "tx_date" not in df.columns:
        df["tx_date"] = df["block_timestamp"].dt.date
    else:
        df["tx_date"] = pd.to_datetime(df["tx_date"]).dt.date
        
    # Tạo nhãn tuần (ISO format: YYYY-WW, bắt đầu từ Thứ 2)
    df["tx_week"] = df["block_timestamp"].dt.strftime("%G-W%V")
    
    print(f"[+] Nạp thành công {len(df):,} giao dịch.")
    print(f"    Khoảng thời gian: từ {df['tx_date'].min()} đến {df['tx_date'].max()} ({df['tx_date'].nunique()} ngày)")
    return df


def aggregate_dynamic_edges(df: pd.DataFrame, window: str = "daily") -> pd.DataFrame:
    """
    Gom nhóm các giao dịch thành danh sách cạnh có trọng số cho từng snapshot G_t.
    - window: 'daily' (theo tx_date) hoặc 'weekly' (theo tx_week).
    """
    time_col = "tx_date" if window == "daily" else "tx_week"
    print(f"[*] Đang gom nhóm cạnh đồ thị theo cửa sổ: {window.upper()} ({time_col})...")
    
    grouped = df.groupby([time_col, "from_address", "to_address"], as_index=False).agg(
        total_value=("amount", "sum"),
        transaction_count=("amount", "count"),
        mean_value=("amount", "mean"),
        min_value=("amount", "min"),
        max_value=("amount", "max"),
        first_timestamp=("block_timestamp", "min"),
        last_timestamp=("block_timestamp", "max")
    )
    
    # Đổi tên cột thời gian thống nhất thành 'time_window'
    grouped = grouped.rename(columns={time_col: "time_window"})
    grouped["window_type"] = window
    
    # Sắp xếp theo thời gian và trọng số giá trị giảm dần
    grouped = grouped.sort_values(by=["time_window", "total_value"], ascending=[True, False]).reset_index(drop=True)
    print(f"[+] Tạo thành công {len(grouped):,} cạnh có trọng số qua {grouped['time_window'].nunique()} snapshot thời gian.")
    return grouped


def calculate_snapshot_metrics(edges_df: pd.DataFrame, window_name: str) -> pd.DataFrame:
    """
    Tính toán các chỉ số mạng lưới tổng quát cho từng snapshot G_t:
    - Số nodes |V_t|, Số edges |E_t|
    - Tổng volume, tổng giao dịch
    - Mật độ đồ thị (density)
    - Tỷ lệ tương hỗ (reciprocity)
    - Số thành phần liên thông mạnh/yếu
    """
    print(f"[*] Đang tính toán các chỉ số đồ thị mạng lưới cho {window_name}...")
    metrics_list = []
    
    # Gom nhóm theo time_window
    windows = edges_df["time_window"].unique()
    total_w = len(windows)
    
    for idx, w in enumerate(windows, 1):
        if idx % 50 == 0 or idx == total_w:
            print(f"    Tiến độ: [{idx}/{total_w}] snapshot ({w})...")
            
        sub = edges_df[edges_df["time_window"] == w]
        
        # Xây dựng đồ thị NetworkX có hướng
        G = nx.DiGraph()
        for _, row in sub.iterrows():
            G.add_edge(
                row["from_address"],
                row["to_address"],
                weight=float(row["total_value"]),
                tx_count=int(row["transaction_count"])
            )
            
        num_nodes = G.number_of_nodes()
        num_edges = G.number_of_edges()
        total_vol = float(sub["total_value"].sum())
        total_tx = int(sub["transaction_count"].sum())
        
        # Mật độ đồ thị (Density)
        density = nx.density(G) if num_nodes > 1 else 0.0
        
        # Reciprocity (Tỷ lệ dòng tiền 2 chiều)
        reciprocity = nx.reciprocity(G) if num_edges > 0 else 0.0
        
        # Thành phần liên thông
        num_wcc = nx.number_weakly_connected_components(G)
        num_scc = nx.number_strongly_connected_components(G)
        
        # Top active nodes (Degree)
        in_degrees = dict(G.in_degree())
        out_degrees = dict(G.out_degree())
        max_in_node = max(in_degrees, key=in_degrees.get) if in_degrees else None
        max_out_node = max(out_degrees, key=out_degrees.get) if out_degrees else None
        
        metrics_list.append({
            "time_window": str(w),
            "num_nodes": num_nodes,
            "num_edges": num_edges,
            "total_volume_usdt": total_vol,
            "total_transactions": total_tx,
            "density": round(density, 6),
            "reciprocity": round(reciprocity, 4),
            "num_weakly_connected_components": num_wcc,
            "num_strongly_connected_components": num_scc,
            "max_in_degree": in_degrees.get(max_in_node, 0) if max_in_node else 0,
            "max_in_address": max_in_node,
            "max_out_degree": out_degrees.get(max_out_node, 0) if max_out_node else 0,
            "max_out_address": max_out_node,
        })
        
    metrics_df = pd.DataFrame(metrics_list)
    return metrics_df


class DynamicGraphLoader:
    """
    Lớp tiện ích phục vụ cho các Task tiếp theo (T09, T10, Contagion Simulation):
    - Trích xuất nhanh nx.DiGraph tại snapshot bất kỳ.
    - Lặp qua chuỗi đồ thị theo thứ tự thời gian.
    - Gán nhãn thực thể (Entity Label) vào các nút.
    """
    def __init__(self, edges_parquet_path: Path | str, labels_csv_path: Path | str = None):
        self.edges_path = Path(edges_parquet_path)
        self.df_edges = pd.read_parquet(self.edges_path)
        self.labels = {}
        
        if labels_csv_path and Path(labels_csv_path).is_file():
            df_lbl = pd.read_csv(labels_csv_path)
            if "address" in df_lbl.columns and "entity_type" in df_lbl.columns:
                df_lbl["address"] = df_lbl["address"].astype(str).str.lower().str.strip()
                for _, r in df_lbl.iterrows():
                    self.labels[r["address"]] = {
                        "entity_name": r.get("entity_name", "Unknown"),
                        "entity_type": r.get("entity_type", "Unknown")
                    }
                    
    def get_time_windows(self) -> list:
        """Lấy danh sách các mốc thời gian có trong đồ thị."""
        return sorted(self.df_edges["time_window"].unique().tolist())
        
    def build_snapshot_graph(self, time_window: str) -> nx.DiGraph:
        """Tạo đối tượng nx.DiGraph cho 1 snapshot thời gian cụ thể."""
        sub = self.df_edges[self.df_edges["time_window"] == time_window]
        if sub.empty:
            raise ValueError(f"Không có dữ liệu cho mốc thời gian: {time_window}")
            
        G = nx.DiGraph(time_window=str(time_window), window_type=sub["window_type"].iloc[0])
        
        for _, row in sub.iterrows():
            u = row["from_address"]
            v = row["to_address"]
            G.add_edge(
                u, v,
                weight=float(row["total_value"]),
                transaction_count=int(row["transaction_count"]),
                mean_value=float(row["mean_value"])
            )
            
        # Gán nhãn thực thể cho các nút (nếu có nhãn)
        if self.labels:
            for node in G.nodes():
                if node in self.labels:
                    G.nodes[node]["entity_name"] = self.labels[node]["entity_name"]
                    G.nodes[node]["entity_type"] = self.labels[node]["entity_type"]
                else:
                    G.nodes[node]["entity_name"] = "Unknown"
                    G.nodes[node]["entity_type"] = "Unknown"
                    
        return G


def run_pipeline(input_path: Path, output_dir: Path, labels_path: Path = None):
    """Thực thi toàn bộ pipeline xây dựng Dynamic Graph T08."""
    print("=" * 65)
    print("      TASK T08: XÂY DỰNG DYNAMIC TRANSACTION GRAPH (G_t)")
    print("=" * 65)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Nạp dữ liệu
    df_transfers = load_normalized_transfers(input_path)
    
    # 2. Xây dựng đồ thị Daily G_{t, daily}
    daily_edges = aggregate_dynamic_edges(df_transfers, window="daily")
    daily_edges_path = output_dir / "dynamic_edges_daily.parquet"
    daily_edges.to_parquet(daily_edges_path, index=False)
    print(f"[+] Đã lưu danh sách cạnh Daily: {daily_edges_path}")
    
    # 3. Xây dựng đồ thị Weekly G_{t, weekly}
    weekly_edges = aggregate_dynamic_edges(df_transfers, window="weekly")
    weekly_edges_path = output_dir / "dynamic_edges_weekly.parquet"
    weekly_edges.to_parquet(weekly_edges_path, index=False)
    print(f"[+] Đã lưu danh sách cạnh Weekly: {weekly_edges_path}")
    
    # 4. Tính toán Metrics cho Daily
    metrics_daily = calculate_snapshot_metrics(daily_edges, window_name="DAILY SNAPSHOTS")
    metrics_daily_pq = output_dir / "graph_metrics_daily.parquet"
    metrics_daily_csv = output_dir / "graph_metrics_daily.csv"
    metrics_daily.to_parquet(metrics_daily_pq, index=False)
    metrics_daily.to_csv(metrics_daily_csv, index=False, encoding="utf-8-sig")
    print(f"[+] Đã lưu chỉ số mạng lưới Daily: {metrics_daily_pq} và {metrics_daily_csv}")
    
    # 5. Tính toán Metrics cho Weekly
    metrics_weekly = calculate_snapshot_metrics(weekly_edges, window_name="WEEKLY SNAPSHOTS")
    metrics_weekly_pq = output_dir / "graph_metrics_weekly.parquet"
    metrics_weekly_csv = output_dir / "graph_metrics_weekly.csv"
    metrics_weekly.to_parquet(metrics_weekly_pq, index=False)
    metrics_weekly.to_csv(metrics_weekly_csv, index=False, encoding="utf-8-sig")
    print(f"[+] Đã lưu chỉ số mạng lưới Weekly: {metrics_weekly_pq} và {metrics_weekly_csv}")
    
    # 6. Tạo file tổng hợp kết quả T08 Summary JSON
    summary = {
        "task": "T08 - Build Dynamic Transaction Graph",
        "input_file": str(input_path),
        "total_transfers_processed": int(len(df_transfers)),
        "time_range": {
            "start_date": str(df_transfers["tx_date"].min()),
            "end_date": str(df_transfers["tx_date"].max()),
            "total_days": int(df_transfers["tx_date"].nunique())
        },
        "daily_graph": {
            "total_snapshots": int(len(metrics_daily)),
            "total_weighted_edges": int(len(daily_edges)),
            "avg_nodes_per_day": round(float(metrics_daily["num_nodes"].mean()), 2),
            "avg_edges_per_day": round(float(metrics_daily["num_edges"].mean()), 2),
            "max_daily_volume_usdt": float(metrics_daily["total_volume_usdt"].max()),
            "output_edges_parquet": str(daily_edges_path),
            "output_metrics_parquet": str(metrics_daily_pq),
            "output_metrics_csv": str(metrics_daily_csv)
        },
        "weekly_graph": {
            "total_snapshots": int(len(metrics_weekly)),
            "total_weighted_edges": int(len(weekly_edges)),
            "avg_nodes_per_week": round(float(metrics_weekly["num_nodes"].mean()), 2),
            "avg_edges_per_week": round(float(metrics_weekly["num_edges"].mean()), 2),
            "max_weekly_volume_usdt": float(metrics_weekly["total_volume_usdt"].max()),
            "output_edges_parquet": str(weekly_edges_path),
            "output_metrics_parquet": str(metrics_weekly_pq),
            "output_metrics_csv": str(metrics_weekly_csv)
        },
        "edge_attributes": [
            {"name": "total_value", "description": "Tổng khối lượng token USDT chuyển giữa u -> v trong cửa sổ t"},
            {"name": "transaction_count", "description": "Số lượng giao dịch giữa u -> v trong cửa sổ t"},
            {"name": "mean_value", "description": "Giá trị giao dịch trung bình"}
        ],
        "generated_at": datetime.now().isoformat()
    }
    
    summary_path = output_dir / "t08_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] Đã lưu báo cáo tóm tắt: {summary_path}")
    
    print("\n" + "=" * 65)
    print("           HOÀN THÀNH XUẤT SẮC NHIỆM VỤ T08!")
    print("=" * 65)
    print(f"Tổng snapshots Daily: {len(metrics_daily)} ngày | Tổng cạnh: {len(daily_edges):,}")
    print(f"Tổng snapshots Weekly: {len(metrics_weekly)} tuần | Tổng cạnh: {len(weekly_edges):,}")
    print(f"Thư mục lưu trữ: {output_dir.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="T08: Xây dựng Dynamic Transaction Graph G_t (Daily & Weekly)")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PARQUET, help="Đường dẫn file transfers interim parquet")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="Thư mục lưu kết quả graphs")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_CSV, help="File nhãn ví t07 (tùy chọn)")
    args = parser.parse_args()
    
    run_pipeline(args.input, args.output, args.labels)


if __name__ == "__main__":
    main()

