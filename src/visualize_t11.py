"""
T11 Visualization Suite: Biểu đồ chuỗi thời gian, so sánh Stress RQ4 và bản đồ cộng đồng.
========================================================================================
Xuất các biểu đồ đạt chuẩn publication vào outputs/figures/t11/ phục vụ báo cáo và T27.
"""
from __future__ import annotations

import sys
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import networkx as nx
import numpy as np
import pandas as pd
from src.graph_config import read_config,project_path
from src.t11_reporting import REGIMES

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data/figures/t11"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR=project_path(read_config(ROOT/'config/t11.yaml')['output_dir'])

# Cấu hình thẩm mỹ đồ thị
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
plt.rcParams["axes.edgecolor"] = "#cbd5e1"
plt.rcParams["axes.linewidth"] = 0.8


def plot_modularity_timeseries(daily_df: pd.DataFrame, weekly_df: pd.DataFrame):
    """Vẽ chuỗi thời gian Modularity Q (Daily và Weekly) cùng các vùng Stress."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=False, facecolor="#ffffff")

    daily_df = daily_df.copy()
    daily_df["date"] = pd.to_datetime(daily_df["time_window"])
    daily_df = daily_df.sort_values("date")

    # Xác định ngưỡng stress: top 10% volume
    p90 = daily_df["total_volume_usdt"].quantile(0.90)
    stress_dates = daily_df[daily_df["total_volume_usdt"] >= p90]["date"]

    # 1. Daily Modularity
    ax1.plot(daily_df["date"], daily_df["modularity"], color="#94a3b8", alpha=0.45, linewidth=0.9, label="Modularity hàng ngày")
    ax1.plot(daily_df["date"], daily_df["modularity"].rolling(14, min_periods=3).mean(), color="#1e3a8a", linewidth=2.0, label="MA(14 ngày)")

    # Đánh dấu các giai đoạn Stress
    for s_date in stress_dates:
        ax1.axvline(s_date, color="#ef4444", alpha=0.08, linewidth=1.5)

    ax1.axhline(daily_df["modularity"].mean(), color="#047857", linestyle="--", linewidth=1.2, label=f"Mean = {daily_df['modularity'].mean():.4f}")
    ax1.set_title("A. Chuỗi Thời Gian Modularity Cộng Đồng Hàng Ngày ($Q_{\\text{daily}}$, 655 ngày)", fontsize=12, fontweight="bold", pad=10)
    ax1.set_ylabel("Modularity ($Q$)", fontsize=10, fontweight="bold")
    ax1.set_ylim(0.45, 0.95)
    ax1.legend(loc="lower left", framealpha=0.9)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))

    # 2. Weekly Modularity
    weekly_df = weekly_df.copy().sort_values("time_window")
    x_idx = np.arange(len(weekly_df))
    ax2.plot(x_idx, weekly_df["modularity"], color="#0369a1", marker="o", markersize=3.5, linewidth=1.6, label="Modularity hàng tuần ($Q_{\\text{weekly}}$)")
    ax2.axhline(weekly_df["modularity"].mean(), color="#047857", linestyle="--", linewidth=1.2, label=f"Mean = {weekly_df['modularity'].mean():.4f}")
    
    # Tick labels tuần
    step = 10
    ax2.set_xticks(x_idx[::step])
    ax2.set_xticklabels(weekly_df["time_window"].iloc[::step], rotation=45, ha="right", fontsize=8.5)
    ax2.set_title("B. Chuỗi Thời Gian Modularity Hàng Tuần ($Q_{\\text{weekly}}$, 94 tuần ISO)", fontsize=12, fontweight="bold", pad=10)
    ax2.set_ylabel("Modularity ($Q$)", fontsize=10, fontweight="bold")
    ax2.set_xlabel("Cửa sổ thời gian (Tuần)", fontsize=10, fontweight="bold")
    ax2.set_ylim(0.45, 0.90)
    ax2.legend(loc="lower left", framealpha=0.9)

    plt.tight_layout()
    out_path = OUTPUT_DIR / "t11_modularity_timeseries.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[+] Đã xuất biểu đồ: {out_path.name}")


def plot_concentration_timeseries(daily_df: pd.DataFrame):
    """Vẽ chuỗi thời gian các chỉ số tập trung: Gini, HHI và Top-5% Volume Share."""
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True, facecolor="#ffffff")

    daily_df = daily_df.copy()
    daily_df["date"] = pd.to_datetime(daily_df["time_window"])
    daily_df = daily_df.sort_values("date")

    # 1. Gini Volume
    ax1.plot(daily_df["date"], daily_df["gini_volume"], color="#8b5cf6", alpha=0.4, linewidth=0.9)
    ax1.plot(daily_df["date"], daily_df["gini_volume"].rolling(14, min_periods=3).mean(), color="#6d28d9", linewidth=2.0, label="Gini Volume MA(14)")
    ax1.axhline(daily_df["gini_volume"].mean(), color="#b91c1c", linestyle="--", linewidth=1.0, label=f"Mean = {daily_df['gini_volume'].mean():.4f}")
    ax1.set_title("A. Hệ Số Bất Bình Đẳng Gini Dòng Tiền Cá Voi ($Gini_{\\text{volume}}$)", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Hệ số Gini", fontsize=9.5, fontweight="bold")
    ax1.set_ylim(0.65, 0.98)
    ax1.legend(loc="lower right")

    # 2. HHI Community Volume
    ax2.plot(daily_df["date"], daily_df["hhi_community_volume"], color="#06b6d4", alpha=0.4, linewidth=0.9)
    ax2.plot(daily_df["date"], daily_df["hhi_community_volume"].rolling(14, min_periods=3).mean(), color="#0e7490", linewidth=2.0, label="HHI Community Volume MA(14)")
    ax2.axhline(daily_df["hhi_community_volume"].mean(), color="#b91c1c", linestyle="--", linewidth=1.0, label=f"Mean = {daily_df['hhi_community_volume'].mean():.4f}")
    ax2.set_title("B. Chỉ Số Tập Trung Cộng Đồng Herfindahl-Hirschman ($HHI_{\\text{community}}$)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("HHI", fontsize=9.5, fontweight="bold")
    ax2.set_ylim(0.02, 0.45)
    ax2.legend(loc="upper right")

    # 3. Top-5% Volume Share
    ax3.plot(daily_df["date"], daily_df["cr_top5pct_volume"], color="#f59e0b", alpha=0.4, linewidth=0.9)
    ax3.plot(daily_df["date"], daily_df["cr_top5pct_volume"].rolling(14, min_periods=3).mean(), color="#b45309", linewidth=2.0, label="Top 5% Whales Volume Share MA(14)")
    ax3.axhline(daily_df["cr_top5pct_volume"].mean(), color="#b91c1c", linestyle="--", linewidth=1.0, label=f"Mean = {daily_df['cr_top5pct_volume'].mean():.4f}")
    ax3.set_title("C. Tỷ Trọng Volume Của Top 5% Cá Voi Lớn Nhất ($CR_{\\text{top5\\%}}$)", fontsize=11, fontweight="bold")
    ax3.set_ylabel("Tỷ trọng (Share)", fontsize=9.5, fontweight="bold")
    ax3.set_xlabel("Thời gian (Tháng)", fontsize=10, fontweight="bold")
    ax3.set_ylim(0.40, 1.0)
    ax3.legend(loc="lower right")
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=2))

    plt.tight_layout()
    out_path = OUTPUT_DIR / "t11_concentration_timeseries.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[+] Đã xuất biểu đồ: {out_path.name}")


def plot_rq4_stress_comparison(daily_df: pd.DataFrame):
    """Đối chiếu mô tả đúng nhóm; không xác nhận stress thị trường."""
    regimes=pd.read_parquet(DATA_DIR/'rq4_daily_regimes.parquet')
    comparisons=pd.read_parquet(DATA_DIR/'rq4_comparison.parquet').set_index('metric')
    daily_df=daily_df.merge(regimes[['time_window','regime']],on='time_window',validate='one_to_one')

    metrics_to_plot = [
        ("gini_volume", "Gini Volume", "#6d28d9"),
        ("hhi_community_volume", "HHI Community Volume", "#0e7490"),
        ("modularity", "Modularity (Q)", "#1e3a8a"),
        ("community_concentration_index", "Community Concentration Index (CCI)", "#b45309")
    ]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), facecolor="#ffffff")
    axes = axes.flatten()

    for idx, (col, title, color) in enumerate(metrics_to_plot):
        ax = axes[idx]
        regime_data = [daily_df[daily_df["regime"] == r][col].dropna() for r in REGIMES]
        display=['Baseline','Pre high-volume','High-volume']
        labels=[f'{name}\n(N={len(values)})' for name,values in zip(display,regime_data)]

        bp = ax.boxplot(regime_data, tick_labels=labels,
                        patch_artist=True, medianprops=dict(color="#1a202c", linewidth=2.0), showmeans=True,
                        meanprops=dict(marker="o", markeredgecolor="#b91c1c", markerfacecolor="#b91c1c", markersize=5))

        for patch in bp["boxes"]:
            patch.set_facecolor(color)
            patch.set_alpha(0.35)

        row=comparisons.loc[col]
        ax.set_title(f"{title}\nPre vs Baseline: {row.relative_change_pct:+.2f}%\np Welch (IID)={row.p_welch_iid_exploratory:.2e}; Holm={row.p_holm_exploratory:.2e}", fontsize=9.5, fontweight="bold", pad=8)
        ax.set_ylabel(title, fontsize=9.5)

    fig.suptitle('RQ4: SO SÁNH MÔ TẢ QUANH NGÀY VOLUME CAO — KHÔNG PHẢI STRESS THỊ TRƯỜNG',fontsize=11,fontweight='bold')
    fig.text(.5,.01,'Welch: thăm dò với giả định độc lập; Holm không xử lý phụ thuộc thời gian. Loại ba ngày cuối thiếu cửa sổ tương lai.',ha='center',fontsize=8)
    plt.tight_layout(rect=[0,.035,1,.95])
    out_path = OUTPUT_DIR / "t11_rq4_stress_comparison.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[+] Đã xuất biểu đồ: {out_path.name}")


def plot_community_map_sample(sample_date: str = "2026-10-17"):
    """Vẽ bản đồ mạng lưới cộng đồng Louvain đại diện (Community Map phục vụ T27)."""
    edges_path = project_path(read_config()['data']['daily_edges_parquet'])
    nodes_path = DATA_DIR / "community_nodes_daily.parquet"

    df_edges = pd.read_parquet(edges_path)
    df_nodes = pd.read_parquet(nodes_path)

    sub_e = df_edges[df_edges["time_window"] == sample_date]
    sub_n = df_nodes[df_nodes["time_window"] == sample_date].set_index("address")

    if sub_e.empty:
        print(f"[-] Không có dữ liệu cho ngày {sample_date}")
        return

    # Lọc top 120 cạnh lớn nhất để hình vẽ rõ nét, không bị rối mắt
    sub_e_top = sub_e.sort_values("total_value", ascending=False).head(120)
    active_nodes = sorted(set(sub_e_top.from_address) | set(sub_e_top.to_address))

    G = nx.DiGraph()
    for _, r in sub_e_top.iterrows():
        G.add_edge(r["from_address"], r["to_address"], weight=float(r["total_value"]))

    pos = nx.spring_layout(G, k=0.45, iterations=60, seed=42)

    # Lấy community ID của các node
    node_comm = [sub_n.loc[u, "community_id"] if u in sub_n.index else 99 for u in G.nodes()]
    node_vol = [sub_n.loc[u, "node_volume_usdt"] / 1e6 if u in sub_n.index else 10.0 for u in G.nodes()]
    node_sizes = [min(max(v * 0.15 + 40, 50), 450) for v in node_vol]

    fig, ax = plt.subplots(figsize=(13, 10), facecolor="#f8fafc")
    ax.set_facecolor("#f8fafc")

    # Vẽ edges: phân biệt cạnh nội bộ cộng đồng (đậm) và liên cộng đồng (mảnh)
    intra_edges = [(u, v) for u, v in G.edges() if sub_n.loc[u, "community_id"] == sub_n.loc[v, "community_id"]]
    inter_edges = [(u, v) for u, v in G.edges() if sub_n.loc[u, "community_id"] != sub_n.loc[v, "community_id"]]

    nx.draw_networkx_edges(G, pos, edgelist=intra_edges, edge_color="#3b82f6", alpha=0.55, width=1.8,
                           arrowstyle="-|>", arrowsize=10, connectionstyle="arc3,rad=0.06", ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=inter_edges, edge_color="#94a3b8", alpha=0.35, width=1.0,
                           arrowstyle="-|>", arrowsize=8, connectionstyle="arc3,rad=0.06", ax=ax)

    # Vẽ nodes theo bảng màu cộng đồng
    cmap = plt.cm.tab20
    nodes_draw = nx.draw_networkx_nodes(G, pos, node_color=node_comm, cmap=cmap, node_size=node_sizes,
                                        alpha=0.92, edgecolors="#1e293b", linewidths=1.0, ax=ax)

    # Gắn nhãn cho top 8 ví có throughput lớn nhất
    top_wallets = sorted(G.nodes(), key=lambda u: sub_n.loc[u, "node_volume_usdt"] if u in sub_n.index else 0, reverse=True)[:8]
    labels = {u: f"{u[:6]}...{u[-4:]}" for u in top_wallets}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=7.5, font_weight="bold",
                            bbox=dict(boxstyle="round,pad=0.2", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.85), ax=ax)

    # Thêm ghi chú
    ax.set_title(f"BẢN ĐỒ CỘNG ĐỒNG LOUVAIN (COMMUNITY MAP) - SNAPSHOT {sample_date}\n(Top Cạnh Dòng Tiền Cá Voi | Màu sắc = Community ID | Phục vụ Task T27)",
                 fontsize=12, fontweight="bold", pad=12, color="#0f172a")

    info_box = (
        "QUY ƯỚC BẢN ĐỒ (COMMUNITY MAP):\n"
        "• Màu sắc node: Phân hoạch cộng đồng Louvain\n"
        "• Kích thước node: Tỷ lệ theo Throughput Volume ($ USDT)\n"
        "• Nét xanh dương: Luồng tiền nội bộ cùng cộng đồng (Intra-community)\n"
        "• Nét xám: Luồng tiền xuyên cộng đồng (Inter-community)"
    )
    ax.text(0.02, 0.02, info_box, transform=ax.transAxes, fontsize=8, verticalalignment="bottom",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.92))

    ax.axis("off")
    plt.tight_layout()
    out_path = OUTPUT_DIR / f"t11_community_map_{sample_date}.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"[+] Đã xuất bản đồ cộng đồng: {out_path.name}")


def main():
    print("\n" + "=" * 70)
    print("      ĐANG XUẤT CÁC BIỂU ĐỒ TRỰC QUAN T11 CHO BÁO CÁO & RQ4...")
    print("=" * 70)

    daily_path = DATA_DIR / "snapshot_metrics_daily.parquet"
    weekly_path = DATA_DIR / "snapshot_metrics_weekly.parquet"

    daily_df = pd.read_parquet(daily_path)
    weekly_df = pd.read_parquet(weekly_path)

    plot_modularity_timeseries(daily_df, weekly_df)
    plot_concentration_timeseries(daily_df)
    plot_rq4_stress_comparison(daily_df)
    plot_community_map_sample("2026-10-17")

    print("\n[+] ĐÃ HOÀN TẤT XUẤT TOÀN BỘ 4 BIỂU ĐỒ TẠI data/figures/t11/!")


if __name__ == "__main__":
    main()
