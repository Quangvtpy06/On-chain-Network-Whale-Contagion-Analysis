"""
Task T08: Xây dựng Dynamic Transaction Graph (G_t)
==================================================
- Tên nhiệm vụ (WBS): Xây dynamic transaction graph
- Mô tả: Đồ thị G_t theo cửa sổ daily hoặc weekly, cạnh có trọng số theo value và số giao dịch
- Thực hiện: TV1 - Yến Vy
- Reviewer: TV4 / Hương
- Tiền đề phụ thuộc: T05 (data/interim/usdt_whale_transfers_interim.parquet)

Đặc tả kỹ thuật:
----------------
1. Chuỗi đồ thị có hướng G_t = (V_t, E_t, W_t) theo cửa sổ thời gian t:
   - Daily: G_{t, daily} (24 giờ UTC, 655 ngày)
   - Weekly: G_{t, weekly} (7 ngày ISO Week, 94 tuần)
2. Cạnh có hướng (u -> v) biểu diễn dòng tiền USDT từ ví nguồn u sang ví đích v.
3. Trọng số cạnh (Edge Weights):
   - total_value (Value Weight): Tổng giá trị token USDT chuyển giao giữa u -> v trong cửa sổ t.
   - transaction_count (Frequency Weight): Số lượng giao dịch chuyển giao giữa u -> v trong cửa sổ t.
   - mean_value: Giá trị trung bình mỗi giao dịch.
   - min_value, max_value: Giá trị giao dịch nhỏ nhất và lớn nhất.
   - first_timestamp, last_timestamp: Thời gian giao dịch đầu tiên và cuối cùng trong cửa sổ.
4. Lớp DynamicGraphLoader:
   - Cung cấp phương thức build_snapshot_graph(t) trích xuất trực tiếp đối tượng networkx.DiGraph.
   - Tự động gán thuộc tính trọng số (weight, transaction_count) cho từng cạnh.
   - Tích hợp nhãn thực thể từ Task T07 (nếu có).
5. Trực quan hóa tự động:
   - Tự động hiển thị đồ thị động G_t của snapshot mẫu ngay trên màn hình (trình duyệt & GUI) sau khi chạy.
"""

from __future__ import annotations

import os
import sys
import json
import argparse
import webbrowser
from pathlib import Path
from datetime import datetime, date
from typing import Union, List, Dict, Any

import pandas as pd
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
import plotly.graph_objects as go

# Fix UTF-8 encoding cho Windows console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Cấu hình đường dẫn mặc định
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_PARQUET = PROJECT_ROOT / "data" / "interim" / "usdt_whale_transfers_interim.parquet"
DEFAULT_LABELS_CSV = PROJECT_ROOT / "data" / "external" / "t07_verified_labels.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "graphs"


def load_whale_transfers(path: Path) -> pd.DataFrame:
    """Nạp dữ liệu giao dịch cá voi USDT đã được chuẩn hóa từ Task T05."""
    if not path.is_file():
        raise FileNotFoundError(f"[-] Không tìm thấy file dữ liệu: {path.resolve()}")
    
    print(f"[*] Đang nạp dữ liệu giao dịch cá voi từ: {path.name}...")
    df = pd.read_parquet(path)
    
    required_cols = {"from_address", "to_address", "amount", "block_timestamp"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"[-] Dữ liệu thiếu các cột bắt buộc: {missing}")
    
    df["from_address"] = df["from_address"].astype(str).str.lower().str.strip()
    df["to_address"] = df["to_address"].astype(str).str.lower().str.strip()
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df["block_timestamp"] = pd.to_datetime(df["block_timestamp"], utc=True)
    
    if "tx_date" not in df.columns:
        df["tx_date"] = df["block_timestamp"].dt.date
    else:
        df["tx_date"] = pd.to_datetime(df["tx_date"]).dt.date
        
    df["tx_week"] = df["block_timestamp"].dt.strftime("%G-W%V")
    
    print(f"[+] Nạp thành công {len(df):,} giao dịch cá voi.")
    print(f"    Khoảng thời gian: từ {df['tx_date'].min()} đến {df['tx_date'].max()} ({df['tx_date'].nunique()} ngày liên tục)")
    return df


def build_dynamic_edges(df: pd.DataFrame, window: str = "daily") -> pd.DataFrame:
    """Gom nhóm các giao dịch thành danh sách cạnh có hướng cho từng snapshot G_t."""
    time_col = "tx_date" if window == "daily" else "tx_week"
    print(f"\n[*] Đang xây dựng đồ thị động G_t theo cửa sổ: {window.upper()} ({time_col})...")
    
    grouped = df.groupby([time_col, "from_address", "to_address"], as_index=False).agg(
        total_value=("amount", "sum"),
        transaction_count=("amount", "count"),
        mean_value=("amount", "mean"),
        min_value=("amount", "min"),
        max_value=("amount", "max"),
        first_timestamp=("block_timestamp", "min"),
        last_timestamp=("block_timestamp", "max")
    )
    
    grouped = grouped.rename(columns={time_col: "time_window"})
    grouped["window_type"] = window
    grouped = grouped.sort_values(by=["time_window", "total_value"], ascending=[True, False]).reset_index(drop=True)
    
    num_snapshots = grouped["time_window"].nunique()
    total_edges = len(grouped)
    total_volume = grouped["total_value"].sum()
    print(f"[+] Hoàn thành đồ thị {window.upper()}:")
    print(f"    - Số snapshot thời gian (t): {num_snapshots}")
    print(f"    - Tổng số cạnh có hướng có trọng số: {total_edges:,}")
    print(f"    - Tổng khối lượng USDT luân chuyển: ${total_volume:,.2f}")
    return grouped


def compute_graph_metrics(edges_df: pd.DataFrame, window_type: str) -> pd.DataFrame:
    """Tính toán chỉ số topology cho từng snapshot đồ thị G_t."""
    print(f"[*] Đang tính toán chỉ số mạng lưới cho {window_type}...")
    metrics_list = []
    
    windows = edges_df["time_window"].unique()
    total_w = len(windows)
    
    for idx, w in enumerate(windows, 1):
        if idx % 50 == 0 or idx == total_w:
            print(f"    Tiến độ: [{idx}/{total_w}] snapshot ({w})...")
            
        sub = edges_df[edges_df["time_window"] == w]
        
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
        
        density = nx.density(G) if num_nodes > 1 else 0.0
        reciprocity = nx.reciprocity(G) if num_edges > 0 else 0.0
        num_wcc = nx.number_weakly_connected_components(G)
        num_scc = nx.number_strongly_connected_components(G)
        
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
        
    return pd.DataFrame(metrics_list)


class DynamicGraphLoader:
    """Lớp tiện ích phục vụ nạp và trích xuất đồ thị động G_t."""
    def __init__(self, edges_parquet_path: Union[Path, str], labels_csv_path: Union[Path, str, None] = None):
        self.edges_path = Path(edges_parquet_path)
        if not self.edges_path.is_file():
            raise FileNotFoundError(f"[-] Không tìm thấy file đồ thị: {self.edges_path}")
            
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
                    
    def get_time_windows(self) -> List[str]:
        return sorted([str(x) for x in self.df_edges["time_window"].unique().tolist()])
        
    def build_snapshot_graph(self, time_window: Union[str, date]) -> nx.DiGraph:
        target_str = str(time_window)
        sub = self.df_edges[self.df_edges["time_window"].astype(str) == target_str]
        if sub.empty:
            raise ValueError(f"[-] Không có dữ liệu cho mốc thời gian: {time_window}")
            
        G = nx.DiGraph(time_window=target_str, window_type=sub["window_type"].iloc[0])
        
        for _, row in sub.iterrows():
            u = row["from_address"]
            v = row["to_address"]
            G.add_edge(
                u, v,
                weight=float(row["total_value"]),
                total_value=float(row["total_value"]),
                transaction_count=int(row["transaction_count"]),
                tx_count=int(row["transaction_count"]),
                mean_value=float(row["mean_value"])
            )
            
        if self.labels:
            for node in G.nodes():
                if node in self.labels:
                    G.nodes[node]["entity_name"] = self.labels[node]["entity_name"]
                    G.nodes[node]["entity_type"] = self.labels[node]["entity_type"]
                else:
                    G.nodes[node]["entity_name"] = "Unknown"
                    G.nodes[node]["entity_type"] = "Unknown"
                    
        return G


def show_dynamic_graph_snapshot(
    edges_parquet_path: Path,
    time_window: str = "2025-01-01",
    top_k_edges: int = 120,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    auto_open: bool = True
):
    """Trích xuất snapshot G_t và hiển thị trực quan trực tiếp."""
    print(f"\n" + "-" * 70)
    print(f"[*] ĐANG HIỂN THỊ ĐỒ THỊ ĐỘNG G_t (SNAPSHOT: {time_window})...")
    print("-" * 70)
    
    loader = DynamicGraphLoader(edges_parquet_path)
    G = loader.build_snapshot_graph(time_window)
    
    print(f"[+] Snapshot G_t ({time_window}) có: {G.number_of_nodes()} ví cá voi, {G.number_of_edges()} luồng giao dịch.")
    
    total_snapshot_edges = G.number_of_edges()
    if top_k_edges and top_k_edges > 0 and top_k_edges < total_snapshot_edges:
        edges_sorted = sorted(G.edges(data=True), key=lambda x: x[2].get("weight", 0), reverse=True)[:top_k_edges]
        is_sub = True
    else:
        edges_sorted = list(G.edges(data=True))
        is_sub = False
        
    subG = nx.DiGraph()
    for u, v, d in edges_sorted:
        subG.add_edge(u, v, **d)
        
    pos = nx.spring_layout(subG, k=0.55, iterations=80, seed=42)
    degrees = dict(subG.degree())
    total_val_m = sum(d.get("weight", 0) for _, _, d in edges_sorted) / 1e6
    
    if is_sub:
        title_label = f"Mạng lưới Giao dịch Động G_t - Snapshot {time_window} (Top {len(subG.edges())}/{total_snapshot_edges} Cạnh | ${total_val_m:,.1f}M Volume)"
        plt_subtitle = f"(Top {len(subG.edges())}/{total_snapshot_edges} Cạnh | {subG.number_of_nodes()} Ví Cá Voi | Volume: ${total_val_m:,.1f}M USDT)"
    else:
        title_label = f"Mạng lưới Giao dịch Động G_t - Snapshot {time_window} (Toàn bộ {len(subG.edges())} Cạnh | ${total_val_m:,.1f}M Volume)"
        plt_subtitle = f"(Toàn bộ {len(subG.edges())} Cạnh | {subG.number_of_nodes()} Ví Cá Voi | Volume: ${total_val_m:,.1f}M USDT)"
        
    # --- A. Tạo file đồ thị tương tác HTML (Plotly) ---
    edge_x, edge_y = [], []
    for edge in subG.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1.2, color='#a0aec0'),
        hoverinfo='none',
        mode='lines'
    )
    
    node_x, node_y, node_text, node_sizes = [], [], [], []
    in_degrees = dict(subG.in_degree())
    out_degrees = dict(subG.out_degree())
    for node in subG.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        deg = degrees[node]
        node_sizes.append(min(deg * 5 + 10, 42))
        node_text.append(
            f"<b>Ví cá voi:</b> {node}<br>"
            f"<b>Tổng bậc kết nối:</b> {deg}<br>"
            f"<b>In-degree:</b> {in_degrees[node]} | <b>Out-degree:</b> {out_degrees[node]}"
        )
        
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers',
        hoverinfo='text',
        text=node_text,
        marker=dict(
            showscale=True,
            colorscale='Plasma',
            color=list(degrees.values()),
            size=node_sizes,
            colorbar=dict(thickness=15, title=dict(text='Bậc (Degree)', side='right')),
            line=dict(width=1.5, color='#2d3748')
        )
    )
    
    fig_plotly = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title=dict(
                text=title_label,
                font=dict(size=16, color='#2d3748')
            ),
            showlegend=False,
            hovermode='closest',
            margin=dict(b=20, l=10, r=10, t=50),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor='#f8f9fa',
            paper_bgcolor='#ffffff'
        )
    )
    
    html_path = output_dir / f"dynamic_graph_interactive_{time_window}.html"
    fig_plotly.write_html(str(html_path))
    print(f"[+] Đã tạo file đồ thị tương tác HTML: {html_path.name}")
    
    fig_plt, ax = plt.subplots(figsize=(14, 11), facecolor="#f8f9fa")
    ax.set_facecolor("#f8f9fa")
    weights = [subG[u][v]["weight"] for u, v in subG.edges()]
    max_w = max(weights) if weights else 1.0
    widths = [0.8 + 2.2 * (w / max_w) for w in weights]
    
    nx.draw_networkx_edges(
        subG, pos,
        arrowstyle="-|>",
        arrowsize=13,
        edge_color="#718096",
        alpha=0.5,
        width=widths,
        connectionstyle="arc3,rad=0.08",
        ax=ax
    )
    
    nodes_draw = nx.draw_networkx_nodes(
        subG, pos,
        node_size=[degrees[n] * 65 + 70 for n in subG.nodes()],
        node_color=[degrees[n] for n in subG.nodes()],
        cmap=plt.cm.plasma,
        alpha=0.92,
        edgecolors="#2d3748",
        linewidths=1.2,
        ax=ax
    )
    
    top_hubs = sorted(degrees, key=degrees.get, reverse=True)[:12]
    labels = {n: n[:6] + "..." + n[-4:] for n in top_hubs}
    nx.draw_networkx_labels(
        subG, pos, labels=labels,
        font_size=7.5, font_family="sans-serif", font_weight="bold", font_color="#1a202c",
        bbox=dict(boxstyle="round,pad=0.2", facecolor="#ffffff", edgecolor="#cbd5e0", alpha=0.85),
        ax=ax
    )
    
    cbar = plt.colorbar(nodes_draw, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label("Bậc kết nối (Degree)", fontsize=10, fontweight="bold")
    ax.set_title(
        f"DYNAMIC TRANSACTION GRAPH G_t - SNAPSHOT {time_window}\n{plt_subtitle}",
        fontsize=13, fontweight="bold", pad=15, color="#1a202c"
    )
    ax.axis("off")
    plt.tight_layout()
    
    png_path = output_dir / f"dynamic_graph_snapshot_{time_window}.png"
    plt.savefig(png_path, dpi=300, bbox_inches="tight")
    print(f"[+] Đã lưu ảnh đồ thị tĩnh: {png_path.name}")
    
    if auto_open:
        print(f"\n[>>>] ĐANG MỞ ĐỒ THỊ TRÊN MÀN HÌNH CỦA BẠN...")
        try:
            os.startfile(str(html_path.resolve()))
            print(f"[+] Đã tự động mở đồ thị tương tác HTML trong trình duyệt Web!")
        except Exception:
            try:
                webbrowser.open(html_path.resolve().as_uri())
                print(f"[+] Đã mở đồ thị tương tác HTML qua trình duyệt Web.")
            except Exception as e:
                print(f"[-] Không thể tự mở trình duyệt: {e}")
                
        try:
            plt.show()
        except Exception:
            pass
            
    plt.close()


def execute_t08_pipeline(
    input_path: Path, 
    output_dir: Path, 
    window_mode: str = "both", 
    labels_path: Path = None,
    auto_visualize: bool = True,
    snapshot_date: str = "2025-01-01"
):
    print("=" * 70)
    print("  TASK T08: XÂY DỰNG DYNAMIC TRANSACTION GRAPH (G_t)")
    print("  Cửa sổ: Daily / Weekly | Trọng số: total_value & transaction_count")
    print("=" * 70)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    df_transfers = load_whale_transfers(input_path)
    
    summary_data: Dict[str, Any] = {
        "task": "T08 - Build Dynamic Transaction Graph",
        "description": "Đồ thị G_t theo cửa sổ daily hoặc weekly, cạnh có trọng số theo value và số giao dịch",
        "input_file": str(input_path.resolve()),
        "total_transfers_processed": int(len(df_transfers)),
        "time_range": {
            "start_date": str(df_transfers["tx_date"].min()),
            "end_date": str(df_transfers["tx_date"].max()),
            "total_days": int(df_transfers["tx_date"].nunique())
        },
        "edge_weights": {
            "total_value": "Tổng khối lượng token USDT chuyển giữa cặp ví u -> v trong cửa sổ thời gian t",
            "transaction_count": "Số lượng giao dịch chuyển nhượng giữa cặp ví u -> v trong cửa sổ thời gian t",
            "mean_value": "Giá trị trung bình trên mỗi giao dịch"
        },
        "generated_at": datetime.now().isoformat()
    }
    
    daily_edges_path = output_dir / "dynamic_edges_daily.parquet"
    
    if window_mode in ("both", "daily"):
        daily_edges = build_dynamic_edges(df_transfers, window="daily")
        daily_edges.to_parquet(daily_edges_path, index=False)
        print(f"[+] Đã lưu danh sách cạnh Daily: {daily_edges_path.name}")
        
        metrics_daily = compute_graph_metrics(daily_edges, window_type="DAILY SNAPSHOTS")
        metrics_daily_csv = output_dir / "graph_metrics_daily.csv"
        metrics_daily.to_csv(metrics_daily_csv, index=False, encoding="utf-8-sig")
        print(f"[+] Đã lưu chỉ số mạng lưới Daily: {metrics_daily_csv.name}")
        
        summary_data["daily_graph"] = {
            "total_snapshots": int(len(metrics_daily)),
            "total_weighted_edges": int(len(daily_edges)),
            "avg_nodes_per_day": round(float(metrics_daily["num_nodes"].mean()), 2),
            "avg_edges_per_day": round(float(metrics_daily["num_edges"].mean()), 2),
            "max_daily_volume_usdt": float(metrics_daily["total_volume_usdt"].max()),
            "output_edges_parquet": str(daily_edges_path.name),
            "output_metrics_csv": str(metrics_daily_csv.name)
        }
        
    if window_mode in ("both", "weekly"):
        weekly_edges = build_dynamic_edges(df_transfers, window="weekly")
        weekly_edges_path = output_dir / "dynamic_edges_weekly.parquet"
        weekly_edges.to_parquet(weekly_edges_path, index=False)
        print(f"[+] Đã lưu danh sách cạnh Weekly: {weekly_edges_path.name}")
        
        metrics_weekly = compute_graph_metrics(weekly_edges, window_type="WEEKLY SNAPSHOTS")
        metrics_weekly_csv = output_dir / "graph_metrics_weekly.csv"
        metrics_weekly.to_csv(metrics_weekly_csv, index=False, encoding="utf-8-sig")
        print(f"[+] Đã lưu chỉ số mạng lưới Weekly: {metrics_weekly_csv.name}")
        
        summary_data["weekly_graph"] = {
            "total_snapshots": int(len(metrics_weekly)),
            "total_weighted_edges": int(len(weekly_edges)),
            "avg_nodes_per_week": round(float(metrics_weekly["num_nodes"].mean()), 2),
            "avg_edges_per_week": round(float(metrics_weekly["num_edges"].mean()), 2),
            "max_weekly_volume_usdt": float(metrics_weekly["total_volume_usdt"].max()),
            "output_edges_parquet": str(weekly_edges_path.name),
            "output_metrics_csv": str(metrics_weekly_csv.name)
        }
        
    summary_path = output_dir / "t08_summary.json"
    summary_path.write_text(json.dumps(summary_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[+] Đã lưu file tóm tắt nghiệm thu: {summary_path.name}")
    
    print("\n" + "=" * 70)
    print("      ĐÃ HOÀN TẤT XÂY DỰNG DYNAMIC TRANSACTION GRAPH G_t!")
    print("=" * 70)
    
    if auto_visualize and daily_edges_path.exists():
        show_dynamic_graph_snapshot(
            edges_parquet_path=daily_edges_path,
            time_window=snapshot_date,
            output_dir=output_dir,
            auto_open=True
        )


def main():
    parser = argparse.ArgumentParser(
        description="Task T08: Xây dynamic transaction graph G_t theo cửa sổ daily/weekly, cạnh có trọng số theo value và số giao dịch"
    )
    parser.add_argument("--window", type=str, choices=["both", "daily", "weekly"], default="both",
                        help="Chế độ cửa sổ thời gian: 'both' (cả hai), 'daily', hoặc 'weekly'")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PARQUET,
                        help="Đường dẫn file interim giao dịch cá voi (.parquet)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Thư mục xuất các đồ thị kết quả")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_CSV,
                        help="File nhãn ví T07 (tùy chọn)")
    parser.add_argument("--date", type=str, default="2025-01-01",
                        help="Mốc ngày snapshot muốn hiển thị (mặc định: 2025-01-01)")
    parser.add_argument("--show-only", action="store_true",
                        help="Chỉ mở hiển thị đồ thị ngay lập tức từ dữ liệu đã có (không chạy lại pipeline)")
    parser.add_argument("--no-show", action="store_true",
                        help="Không tự động mở cửa sổ đồ thị (chế độ headless/chạy ngầm)")
    parser.add_argument("--top-k", type=int, default=120,
                        help="Số cạnh lớn nhất muốn hiển thị trên biểu đồ (mặc định: 120)")
    parser.add_argument("--all-edges", action="store_true",
                        help="Hiển thị toàn bộ 100%% tất cả các cạnh trong snapshot")
    args = parser.parse_args()
    
    effective_top_k = 0 if args.all_edges else args.top_k
    
    # Lựa chọn file đồ thị theo cửa sổ daily hoặc weekly
    is_weekly = (args.window == "weekly") or ("-W" in args.date)
    edges_path = args.output / ("dynamic_edges_weekly.parquet" if is_weekly else "dynamic_edges_daily.parquet")
    
    if args.show_only:
        if not edges_path.exists():
            print(f"[-] Chưa tìm thấy file dữ liệu: {edges_path}. Đang tiến hành chạy pipeline trước...")
            execute_t08_pipeline(
                input_path=args.input,
                output_dir=args.output,
                window_mode=args.window,
                labels_path=args.labels,
                auto_visualize=not args.no_show,
                snapshot_date=args.date
            )
        else:
            show_dynamic_graph_snapshot(
                edges_parquet_path=edges_path,
                time_window=args.date,
                top_k_edges=effective_top_k,
                output_dir=args.output,
                auto_open=not args.no_show
            )
    else:
        execute_t08_pipeline(
            input_path=args.input,
            output_dir=args.output,
            window_mode=args.window,
            labels_path=args.labels,
            auto_visualize=not args.no_show,
            snapshot_date=args.date
        )


if __name__ == "__main__":
    main()
