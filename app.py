from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from huggingface_hub import hf_hub_download
from huggingface_hub.errors import HfHubHTTPError


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data" / "processed"
HF_DATASET_ID = "team-crypto/Market-data-crypto-project"
HF_DATASET_REVISION = "3bfb61848e1ac9bcfb0809d3aef334d1885a84a1"

BG = "#f4f6f8"
SURFACE = "#ffffff"
SURFACE_RAISED = "#edf1f5"
TEXT = "#181a20"
MUTED = "#536170"
YELLOW = "#806200"
GREEN = "#087a4f"
RED = "#c6283b"
BLUE = "#245fc1"
HAIRLINE = "#d9e0e7"
GRID = "#dce2e8"

st.set_page_config(
    page_title="Whale Network Explorer",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def read_parquet(
    relative_path: str,
    columns: tuple[str, ...] | None = None,
    filters: tuple[tuple[str, str, Any], ...] = (),
) -> pd.DataFrame:
    path = DATA_ROOT / relative_path
    is_local_lfs_pointer = False
    if path.is_file():
        with path.open("rb") as file:
            is_local_lfs_pointer = file.read(45).startswith(
                b"version https://git-lfs.github.com/spec/v1"
            )
    if not path.is_file() or is_local_lfs_pointer:
        try:
            path = Path(
                hf_hub_download(
                    repo_id=HF_DATASET_ID,
                    repo_type="dataset",
                    filename=f"data/processed/{relative_path}",
                    revision=HF_DATASET_REVISION,
                )
            )
        except (HfHubHTTPError, OSError, ValueError) as download_error:
            raise FileNotFoundError(
                f"Không tìm thấy `{relative_path}` trong dữ liệu local hoặc "
                f"dataset Hugging Face `{HF_DATASET_ID}` tại revision "
                f"`{HF_DATASET_REVISION}`. Kiểm tra kết nối và file đã được "
                "publish lên dataset."
            ) from download_error
    kwargs: dict[str, Any] = {}
    if columns is not None:
        kwargs["columns"] = list(columns)
    if filters:
        kwargs["filters"] = list(filters)
    return pd.read_parquet(path, **kwargs)


def apply_styles() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
          --app-bg: {BG};
          --app-surface: {SURFACE};
          --app-elevated: {SURFACE_RAISED};
          --app-text: {TEXT};
          --app-muted: {MUTED};
          --app-accent: {YELLOW};
          --app-positive: {GREEN};
          --app-negative: {RED};
          --app-border: {HAIRLINE};
          --app-sidebar: #eef2f5;
          --app-disclaimer: #fff8df;
          --app-grid: {GRID};
          --primary-color: {YELLOW};
          --background-color: {BG};
          --secondary-background-color: {SURFACE};
          --text-color: {TEXT};
          --border-color: {HAIRLINE};
        }}
        html, body, [data-testid="stAppViewContainer"] {{
          background: var(--app-bg);
          color: var(--app-text);
          font-family: Arial, "Helvetica Neue", sans-serif;
        }}
        [data-testid="stHeader"] {{ background: transparent; }}
        [data-testid="stSidebar"] {{
          background: var(--app-sidebar);
          border-right: 1px solid var(--app-border);
        }}
        [data-testid="stSidebar"] > div {{ padding-top: 1.2rem; }}
        [data-testid="stMetric"] {{
          background: var(--app-surface);
          border: 1px solid var(--app-border);
          border-radius: 12px;
          padding: 16px 18px;
        }}
        [data-testid="stMetricLabel"] p {{ color: var(--app-muted); }}
        [data-testid="stMetricValue"] {{
          color: var(--app-text);
          font-family: "Consolas", "SFMono-Regular", monospace;
          font-size: clamp(1.15rem, 2vw, 1.8rem);
        }}
        [data-testid="stTabs"] button {{
          min-height: 44px;
          color: var(--app-muted);
        }}
        [data-testid="stTabs"] button[aria-selected="true"] {{
          color: var(--app-accent);
          border-bottom-color: var(--app-accent);
        }}
        [data-testid="stTabs"] button:focus-visible,
        button:focus-visible, input:focus-visible {{
          outline: 2px solid var(--app-accent) !important;
          outline-offset: 2px !important;
        }}
        [data-testid="stVerticalBlockBorderWrapper"] {{
          border-color: var(--app-border);
          border-radius: 12px;
        }}
        [data-testid="stDataFrame"] {{
          border: 1px solid var(--app-border);
          border-radius: 12px;
          overflow: hidden;
        }}
        [data-testid="stDataFrame"] [role="columnheader"] {{
          background: var(--app-elevated);
          color: var(--app-text);
          font-weight: 650;
        }}
        [data-testid="stDataFrame"] [role="gridcell"] {{
          border-bottom-color: var(--app-border);
        }}
        [data-testid="stDownloadButton"] button {{
          min-height: 42px;
          border-radius: 9px;
        }}
        .eyebrow {{
          color: var(--app-accent);
          font-size: 0.75rem;
          font-weight: 700;
          letter-spacing: 0.13em;
          text-transform: uppercase;
        }}
        .page-title {{
          color: var(--app-text);
          font-size: clamp(2rem, 4vw, 3rem);
          font-weight: 700;
          letter-spacing: -0.04em;
          line-height: 1.08;
          margin: 0.35rem 0 0.55rem;
        }}
        .page-subtitle {{
          color: var(--app-muted);
          font-size: 1rem;
          line-height: 1.6;
          max-width: 850px;
        }}
        .status-pill {{
          display: inline-flex;
          align-items: center;
          gap: 8px;
          border: 1px solid var(--app-border);
          border-radius: 999px;
          color: var(--app-text);
          background: var(--app-surface);
          font-size: 0.8rem;
          padding: 7px 11px;
        }}
        .status-dot {{
          width: 7px;
          height: 7px;
          border-radius: 100%;
          background: {GREEN};
        }}
        .section-heading {{
          font-size: 1.2rem;
          font-weight: 650;
          margin: 1.2rem 0 0.2rem;
        }}
        .muted-copy {{ color: var(--app-muted); font-size: 0.9rem; line-height: 1.55; }}
        .disclaimer {{
          border-left: 3px solid var(--app-accent);
          background: var(--app-disclaimer);
          border-radius: 0 8px 8px 0;
          color: var(--app-text);
          font-size: 0.88rem;
          line-height: 1.6;
          padding: 12px 15px;
        }}
        @media (max-width: 768px) {{
          [data-testid="stMetric"] {{ padding: 12px; }}
        }}
        @media (prefers-reduced-motion: reduce) {{
          *, *::before, *::after {{ scroll-behavior: auto !important; animation-duration: 0.01ms !important; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def plot_layout(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"color": TEXT, "family": "Arial, sans-serif", "size": 12},
        margin={"l": 22, "r": 18, "t": 42, "b": 26},
        title={"x": 0.02, "xanchor": "left", "font": {"size": 14}},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        hoverlabel={"bgcolor": SURFACE_RAISED, "font": {"color": TEXT}},
        xaxis={"gridcolor": GRID, "zerolinecolor": GRID, "automargin": True},
        yaxis={"gridcolor": GRID, "zerolinecolor": GRID, "automargin": True},
        dragmode="pan",
        hovermode="x unified",
    )
    for trace in fig.data:
        values = getattr(trace, "x", None)
        if values is None:
            continue
        x_values = np.asarray(values)
        if x_values.size and isinstance(
            x_values[0], (pd.Timestamp, np.datetime64, date)
        ):
            minimum = pd.Timestamp(x_values.min()).to_pydatetime()
            maximum = pd.Timestamp(x_values.max()).to_pydatetime()
            fig.update_xaxes(
                rangeslider_visible=True,
                rangeslider_thickness=0.08,
                rangeslider_bgcolor=SURFACE_RAISED,
                rangeslider_bordercolor=HAIRLINE,
                minallowed=minimum,
                maxallowed=maximum,
            )
            break
    return fig


def render_chart(figure: go.Figure, height: int | None = None) -> None:
    config = {
        "displaylogo": False,
        "scrollZoom": True,
        "doubleClick": "reset",
        "displayModeBar": True,
    }
    if height is None:
        st.plotly_chart(figure, width="stretch", config=config)
    else:
        st.plotly_chart(figure, width="stretch", height=height, config=config)


def render_table(
    dataframe: pd.DataFrame,
    key: str,
    height: int = 420,
) -> pd.DataFrame:
    query = st.text_input(
        "Tìm trong bảng",
        key=f"{key}_search",
        placeholder="Nhập từ khóa để lọc các hàng...",
        help="Tìm không phân biệt chữ hoa/thường trên tất cả các cột.",
    ) or ""
    query = query.strip()
    filtered = dataframe
    if query:
        matches = dataframe.astype("string").apply(
            lambda values: values.str.contains(query, case=False, na=False, regex=False)
        )
        filtered = dataframe.loc[matches.any(axis=1)]
    st.caption(f"Đang hiển thị {len(filtered):,}/{len(dataframe):,} dòng")
    column_config: dict[str, Any] = {}
    for column in filtered.columns:
        if not isinstance(column, str):
            continue
        series = filtered[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            column_config[column] = st.column_config.DatetimeColumn(
                column, format="YYYY-MM-DD"
            )
        elif pd.api.types.is_numeric_dtype(series):
            lower_name = column.lower()
            if "usdt" in lower_name or "volume" in lower_name or "khối lượng" in lower_name:
                number_format = "localized"
            elif any(
                term in lower_name
                for term in ("pagerank", "điểm", "volatility", "trung bình", "ci ")
            ):
                number_format = "%.5f"
            elif pd.api.types.is_integer_dtype(series):
                number_format = "%d"
            else:
                number_format = "%.3f"
            column_config[column] = st.column_config.NumberColumn(
                column, format=number_format
            )
    st.dataframe(
        filtered,
        hide_index=True,
        width="stretch",
        height=min(max(180, height), 560),
        row_height=36,
        column_config=column_config,
    )
    return filtered


def filter_time_range(
    dataframe: pd.DataFrame,
    date_column: str,
    anchor_date: date,
    range_days: int | None,
) -> pd.DataFrame:
    end = pd.Timestamp(anchor_date)
    filtered = dataframe[dataframe[date_column].le(end)]
    if range_days is not None:
        start = end - pd.Timedelta(days=range_days - 1)
        filtered = filtered[filtered[date_column].ge(start)]
    return filtered.sort_values(date_column).reset_index(drop=True)


def render_insight(text: str) -> None:
    st.markdown(f'<div class="disclaimer">{text}</div>', unsafe_allow_html=True)


def format_usdt(value: Any) -> str:
    if pd.isna(value):
        return "—"
    number = float(value)
    if abs(number) >= 1_000_000_000:
        return f"{number / 1_000_000_000:,.2f} tỷ"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:,.2f} triệu"
    return f"{number:,.0f}"


def render_csv_download(
    dataframe: pd.DataFrame,
    filename: str,
    key: str,
) -> None:
    if dataframe.empty:
        return
    st.download_button(
        "Tải dữ liệu CSV",
        data=dataframe.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        key=key,
        help="Tải dữ liệu đang hiển thị; ví chỉ xuất hiện dưới bí danh ẩn danh.",
        icon=":material/download:",
        on_click="ignore",
        width="stretch",
    )


def selected_window_end(grain: str, window: str, days_in_window: int) -> date:
    if grain == "Tuần":
        year_text, week_text = window.split("-W")
        week_start = date.fromisocalendar(int(year_text), int(week_text), 1)
        return week_start + timedelta(days=max(days_in_window, 1) - 1)
    return date.fromisoformat(window)


def make_network_figure(
    window: str,
    grain: str,
    node_limit: int | None,
    edge_limit: int | None,
) -> tuple[go.Figure | None, pd.DataFrame]:
    suffix = "weekly" if grain == "Tuần" else "daily"
    edges = read_parquet(
        f"graphs/dynamic_edges_{suffix}.parquet",
        ("time_window", "from_address", "to_address", "total_value", "transaction_count"),
        (("time_window", "=", window),),
    )
    if edges.empty:
        return None, pd.DataFrame()

    weighted_flow = pd.concat(
        [
            edges[["from_address", "total_value"]].rename(columns={"from_address": "address"}),
            edges[["to_address", "total_value"]].rename(columns={"to_address": "address"}),
        ],
        ignore_index=True,
    ).groupby("address", sort=False)["total_value"].sum()
    address_order = weighted_flow.sort_values(ascending=False).index.tolist()
    visible_addresses = set(
        address_order if node_limit is None else address_order[:node_limit]
    )
    visible_edges = edges[
        edges["from_address"].isin(visible_addresses)
        & edges["to_address"].isin(visible_addresses)
    ]
    if edge_limit is not None:
        visible_edges = visible_edges.nlargest(edge_limit, "total_value")
    graph = nx.from_pandas_edgelist(
        visible_edges,
        source="from_address",
        target="to_address",
        edge_attr="total_value",
        create_using=nx.DiGraph,
    )
    address_rank = {address: rank for rank, address in enumerate(address_order, start=1)}
    aliases = {address: f"Ví {rank:02d}" for address, rank in address_rank.items()}
    node_metrics = read_parquet(
        f"t09/node_metrics_{suffix}.parquet",
        ("time_window", "address", "degree", "weighted_degree_usdt", "pagerank"),
        (("time_window", "=", window),),
    )
    community_nodes = read_parquet(
        f"t11/community_nodes_{suffix}.parquet",
        ("time_window", "address", "community_id"),
        (("time_window", "=", window),),
    )
    node_metrics = (
        pd.DataFrame({"time_window": window, "address": address_order})
        .merge(
            node_metrics.drop_duplicates(["time_window", "address"]),
            on=["time_window", "address"],
            how="left",
        )
        .merge(
            community_nodes.drop_duplicates(["time_window", "address"]),
            on=["time_window", "address"],
            how="left",
        )
    )
    table = node_metrics.copy()
    table["wallet_alias"] = table["address"].map(aliases)
    table = table.sort_values("weighted_degree_usdt", ascending=False)
    table = table[
        ["wallet_alias", "degree", "weighted_degree_usdt", "pagerank", "community_id"]
    ].rename(
        columns={
            "wallet_alias": "Ví ẩn danh",
            "degree": "Bậc",
            "weighted_degree_usdt": "Trọng số bậc (USDT)",
            "pagerank": "PageRank",
            "community_id": "Cộng đồng",
        }
    )
    if visible_edges.empty:
        return None, table

    positions = nx.circular_layout(graph)
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for source, target in visible_edges[
        ["from_address", "to_address"]
    ].itertuples(index=False, name=None):
        edge_x.extend([positions[source][0], positions[target][0], None])
        edge_y.extend([positions[source][1], positions[target][1], None])

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            line={"width": 0.7, "color": "rgba(144,164,174,0.35)"},
            hoverinfo="skip",
            name="Luồng giao dịch",
        )
    )
    metric_lookup = node_metrics.set_index("address")
    ordered_nodes = sorted(graph.nodes, key=lambda address: address_rank[address])
    labels = [aliases[address] for address in ordered_nodes]
    degrees = [
        int(metric_lookup.at[address, "degree"])
        if address in metric_lookup.index and pd.notna(metric_lookup.at[address, "degree"])
        else graph.degree[address]
        for address in ordered_nodes
    ]
    weighted = [
        float(metric_lookup.at[address, "weighted_degree_usdt"])
        if address in metric_lookup.index
        and pd.notna(metric_lookup.at[address, "weighted_degree_usdt"])
        else float(weighted_flow.get(address, 0))
        for address in ordered_nodes
    ]
    pageranks = [
        float(metric_lookup.at[address, "pagerank"])
        if address in metric_lookup.index and pd.notna(metric_lookup.at[address, "pagerank"])
        else np.nan
        for address in ordered_nodes
    ]
    communities = [
        str(int(metric_lookup.at[address, "community_id"]))
        if address in metric_lookup.index and pd.notna(metric_lookup.at[address, "community_id"])
        else "Chưa gán"
        for address in ordered_nodes
    ]
    community_codes = {
        name: index for index, name in enumerate(sorted(set(communities)))
    }
    max_weight = max((float(x) for x in weighted if pd.notna(x)), default=1.0)
    sizes = [
        10 + 18 * np.sqrt(max(float(value), 0) / max(max_weight, 1))
        if pd.notna(value)
        else 10
        for value in weighted
    ]
    figure.add_trace(
        go.Scatter(
            x=[positions[address][0] for address in ordered_nodes],
            y=[positions[address][1] for address in ordered_nodes],
            mode="markers",
            marker={
                "size": sizes,
                "color": [community_codes[name] for name in communities],
                "colorscale": "Viridis",
                "cmin": 0,
                "cmax": max(len(community_codes) - 1, 1),
                "line": {"width": 1, "color": BG},
                "showscale": False,
            },
            text=labels,
            customdata=[
                [int(degree), float(weight), float(pagerank), community]
                for degree, weight, pagerank, community in zip(
                    degrees, weighted, pageranks, communities
                )
            ],
            hovertemplate=(
                "<b>%{text}</b><br>Liên kết: %{customdata[0]}"
                "<br>Trọng số bậc (USDT): %{customdata[1]:,.0f}"
                "<br>PageRank: %{customdata[2]:.5f}"
                "<br>Cộng đồng: %{customdata[3]}<extra></extra>"
            ),
            name="Ví (ẩn danh)",
        )
    )
    figure.update_layout(
        showlegend=False,
        xaxis={"visible": False},
        yaxis={"visible": False},
        title="",
    )
    plot_layout(figure, height=560)
    figure.update_layout(yaxis_scaleanchor="x", yaxis_scaleratio=1)

    return figure, table


def load_window_metrics(grain: str) -> pd.DataFrame:
    suffix = "weekly" if grain == "Tuần" else "daily"
    return read_parquet(
        f"graphs/graph_metrics_{suffix}.parquet",
        ("time_window", "num_nodes", "num_edges", "total_volume_usdt", "days_in_window"),
    ).sort_values("time_window")


def render_community_chart(
    window: str,
    grain: str,
    community_limit: int | None,
) -> None:
    suffix = "weekly" if grain == "Tuần" else "daily"
    communities = read_parquet(
        f"t11/community_nodes_{suffix}.parquet",
        (
            "time_window",
            "community_id",
            "community_size",
            "community_volume_usdt",
            "is_giant_community",
        ),
        (("time_window", "=", window),),
    )
    if communities.empty:
        st.info("Không có dữ liệu cộng đồng cho cửa sổ đã chọn.")
        return
    communities = (
        communities.sort_values("community_volume_usdt", ascending=False)
        .drop_duplicates("community_id")
        .copy()
    )
    communities["Cộng đồng"] = communities["community_id"].map(lambda value: f"C{int(value)}")
    communities["Quy mô (ví)"] = communities["community_size"]
    communities["Khối lượng (USDT)"] = communities["community_volume_usdt"]
    plot_communities = (
        communities if community_limit is None else communities.head(community_limit)
    )
    figure = px.scatter(
        plot_communities,
        x="Quy mô (ví)",
        y="Khối lượng (USDT)",
        size="Quy mô (ví)",
        color="is_giant_community",
        hover_name="Cộng đồng",
        hover_data={"is_giant_community": True, "Quy mô (ví)": True},
        color_discrete_map={True: YELLOW, False: BLUE},
        labels={"is_giant_community": "Cộng đồng lớn"},
        title="",
    )
    render_chart(plot_layout(figure))
    with st.expander("Bảng dữ liệu cộng đồng"):
        community_table = communities[
            ["Cộng đồng", "Quy mô (ví)", "Khối lượng (USDT)", "is_giant_community"]
        ].rename(columns={"is_giant_community": "Cộng đồng lớn"})
        filtered_table = render_table(community_table, "community_table")
        render_csv_download(
            filtered_table,
            "community-map.csv",
            "community-map-csv",
        )
    render_insight(
        f"Bản đồ đang hiển thị {len(plot_communities):,}/{len(communities):,} cộng đồng "
        "theo khối lượng lớn nhất; "
        "kích thước điểm biểu thị số ví và khối lượng là tổng transfer quan sát được. "
        "Nhãn cộng đồng không định danh chủ sở hữu ví."
    )


def render_flow_panel(anchor_date: date, range_days: int | None) -> pd.DataFrame:
    features = read_parquet(
        "t14/t14_features_daily.parquet",
        (
            "date",
            "cex_external_in_usdt",
            "cex_external_out_usdt",
            "cex_netflow_usdt",
            "whale_to_cex_pit_usdt",
            "cex_to_whale_pit_usdt",
            "whaleflow_pit_usdt",
            "realized_vol",
        ),
    )
    features["date"] = pd.to_datetime(features["date"], errors="raise")
    visible = filter_time_range(features, "date", anchor_date, range_days)
    if visible.empty:
        st.info("Không có chuỗi dữ liệu T14.")
        return visible

    st.caption(
        f"{len(visible):,} ngày trong phạm vi đã chọn · "
        f"{pd.Timestamp(visible['date'].min()).date().isoformat()} – "
        f"{pd.Timestamp(visible['date'].max()).date().isoformat()}. "
        "Dùng con lăn để zoom, kéo để pan; "
        "thanh thời gian phía dưới cho phép chọn vùng mà không mất dữ liệu."
    )
    left, right = st.columns(2)
    with left:
        st.markdown("**Dòng CEX đã biết · USDT**")
        flow_figure = go.Figure()
        flow_figure.add_trace(
            go.Scatter(
                x=visible["date"],
                y=visible["cex_external_in_usdt"],
                name="Vào CEX",
                mode="lines",
                line={"color": GREEN, "width": 2},
            )
        )
        flow_figure.add_trace(
            go.Scatter(
                x=visible["date"],
                y=visible["cex_external_out_usdt"],
                name="Ra khỏi CEX",
                mode="lines",
                line={"color": RED, "width": 2},
            )
        )
        flow_figure.add_trace(
            go.Scatter(
                x=visible["date"],
                y=visible["cex_netflow_usdt"],
                name="Netflow CEX",
                mode="lines",
                line={"color": BLUE, "width": 1.5, "dash": "dot"},
            )
        )
        render_chart(plot_layout(flow_figure))
    with right:
        st.markdown("**Dòng cohort theo nhãn point-in-time · USDT**")
        whale_figure = go.Figure()
        whale_figure.add_trace(
            go.Scatter(
                x=visible["date"],
                y=visible["whale_to_cex_pit_usdt"],
                name="Cohort → CEX",
                mode="lines",
                line={"color": YELLOW, "width": 2},
            )
        )
        whale_figure.add_trace(
            go.Scatter(
                x=visible["date"],
                y=visible["cex_to_whale_pit_usdt"],
                name="CEX → cohort",
                mode="lines",
                line={"color": MUTED, "width": 1.5, "dash": "dot"},
            )
        )
        render_chart(plot_layout(whale_figure))

    st.markdown("**Bối cảnh biến động thực hiện**")
    volatility = go.Figure()
    volatility.add_trace(
        go.Scatter(
            x=visible["date"],
            y=visible["realized_vol"],
            name="Realized volatility",
            mode="lines",
            line={"color": GREEN, "width": 2},
            fill="tozeroy",
            fillcolor=(
                "rgba(8,122,79,0.10)"
            ),
        )
    )
    render_chart(plot_layout(volatility, height=360))
    valid_pairs = visible[
        visible["whale_to_cex_pit_usdt"].notna()
        & visible["realized_vol"].notna()
    ]
    if not valid_pairs.empty:
        correlation = valid_pairs["whale_to_cex_pit_usdt"].corr(
            valid_pairs["realized_vol"], method="spearman"
        )
        render_insight(
            f"Có {len(valid_pairs):,} ngày cùng quan sát được cohort → CEX và volatility; "
            f"tương quan Spearman mô tả = {correlation:.3f}. "
            "Tương quan trong mẫu không chứng minh quan hệ nhân quả hay khả năng dự báo."
        )
    with st.expander("Bảng thay thế cho biểu đồ dòng tiền và volatility"):
        flow_table = visible[
            [
                "date",
                "cex_external_in_usdt",
                "cex_external_out_usdt",
                "cex_netflow_usdt",
                "whale_to_cex_pit_usdt",
                "cex_to_whale_pit_usdt",
                "realized_vol",
            ]
        ].rename(
            columns={
                "date": "Ngày",
                "cex_external_in_usdt": "Vào CEX (USDT)",
                "cex_external_out_usdt": "Ra khỏi CEX (USDT)",
                "cex_netflow_usdt": "Netflow CEX (USDT)",
                "whale_to_cex_pit_usdt": "Cohort → CEX (USDT)",
                "cex_to_whale_pit_usdt": "CEX → cohort (USDT)",
                "realized_vol": "Realized volatility",
            }
        )
        filtered_flow_table = render_table(
            flow_table, "flows_volatility_table", height=500
        )
        render_csv_download(
            filtered_flow_table, "flows-volatility.csv", "flows-volatility-csv"
        )

    whale_day = anchor_date.isoformat()
    whale_scores = read_parquet(
        "t12/whale_scores_daily.parquet",
        ("time_window", "eligible_for_whale_ranking", "whale_rank", "whale_score"),
        (("time_window", "=", whale_day),),
    )
    whale_scores = whale_scores[
        whale_scores["eligible_for_whale_ranking"] & whale_scores["whale_score"].notna()
    ].sort_values("whale_rank").head(10)
    st.markdown('<div class="section-heading">Hoạt động ví nổi bật</div>', unsafe_allow_html=True)
    st.caption(
        f"Điểm whale-score theo T12 cho ngày {whale_day}. Thứ hạng chỉ là tín hiệu "
        "hoạt động trong mẫu, không khẳng định ví thuộc về một cá nhân."
    )
    if whale_scores.empty:
        st.info("Không có ví đủ điều kiện xếp hạng trong ngày được chọn.")
    else:
        whale_scores = whale_scores.reset_index(drop=True)
        whale_scores.insert(0, "Ví ẩn danh", [f"Ví {i:02d}" for i in range(1, len(whale_scores) + 1)])
        whale_scores["Điểm hoạt động"] = whale_scores["whale_score"].round(4)
        whale_scores["Thứ hạng"] = whale_scores["whale_rank"].astype("Int64")
        filtered_whale_scores = render_table(
            whale_scores[["Ví ẩn danh", "Thứ hạng", "Điểm hoạt động"]],
            "whale_activity_table",
        )
        render_insight(
            f"Top 10 điểm hoạt động có median {whale_scores['whale_score'].median():.3f} "
            f"và điểm cao nhất {float(whale_scores['whale_score'].max()):.3f}; đây là thứ hạng "
            "theo hoạt động trong mẫu, không phải định danh cá voi."
        )
        render_csv_download(
            filtered_whale_scores,
            f"whale-activity-{whale_day}.csv",
            "whale-activity-csv",
        )
    return visible


def render_event_study() -> None:
    events = read_parquet(
        "t16/t16_event_study_results.parquet",
        (
            "event_type",
            "selection_policy",
            "analysis_role",
            "block_events",
            "tau",
            "variable",
            "mean",
            "ci_lower",
            "ci_upper",
            "n_events",
        ),
    )
    events = events[events["analysis_role"].eq("primary")]
    if events.empty:
        st.info("Chưa có kết quả primary từ T16.")
        return

    event_labels = {
        "activity_cohort_net_inflow": "Net inflow cohort",
        "cex_net_inflow": "Net inflow CEX",
        "concentration": "Tăng tập trung mạng",
        "large_transfer": "Giao dịch lớn",
    }
    variable_labels = {
        "log_rv": "Log realized volatility",
        "log_volume_usdt": "Log khối lượng USDT",
        "ret_1d": "Lợi suất ngày",
        "spread_cs_proxy": "Proxy spread",
    }
    controls, _ = st.columns([1, 2])
    with controls:
        event_type = st.selectbox(
            "Loại sự kiện",
            sorted(events["event_type"].dropna().unique()),
            format_func=lambda value: event_labels.get(value) or str(value),
            key="report_event_type",
        )
    subset = events[events["event_type"].eq(event_type)]
    with _:
        variable = st.selectbox(
            "Chỉ số phản ứng",
            sorted(subset["variable"].dropna().unique()),
            format_func=lambda value: variable_labels.get(value) or str(value),
            key="report_event_variable",
        )
    subset = subset[subset["variable"].eq(variable)].sort_values("tau")
    variable_name = variable_labels.get(variable) or str(variable)
    valid_ci = subset["ci_lower"].notna() & subset["ci_upper"].notna()
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=subset["tau"],
            y=subset["mean"],
            mode="lines+markers",
            name="Trung bình",
            line={"color": YELLOW, "width": 2},
            marker={"size": 8, "symbol": "circle"},
            error_y={
                "type": "data",
                "symmetric": False,
                "array": (subset["ci_upper"] - subset["mean"]).where(valid_ci, 0),
                "arrayminus": (subset["mean"] - subset["ci_lower"]).where(valid_ci, 0),
                "color": MUTED,
                "thickness": 1,
                "width": 4,
            },
            customdata=subset[["n_events"]],
            hovertemplate="τ=%{x}<br>Trung bình=%{y:.4f}<br>Số sự kiện=%{customdata[0]}<extra></extra>",
        )
    )
    figure.add_vline(x=0, line_color=RED, line_dash="dash", line_width=1)
    figure.update_layout(
        title="",
        xaxis_title="Ngày tương đối so với sự kiện (τ)",
        yaxis_title=variable_name,
    )
    st.markdown(f"**Phản ứng quanh sự kiện · {variable_name}**")
    render_chart(plot_layout(figure, height=400))
    event_table = subset[["tau", "mean", "ci_lower", "ci_upper", "n_events"]].rename(
        columns={
            "tau": "Ngày tương đối (τ)",
            "mean": "Trung bình",
            "ci_lower": "CI 95% dưới",
            "ci_upper": "CI 95% trên",
            "n_events": "Số sự kiện",
        }
    )
    filtered_event_table = render_table(event_table, "event_time_table")
    render_csv_download(
        filtered_event_table, "event-time-response.csv", "event-time-response-csv"
    )
    valid_intervals = subset[valid_ci]
    intervals_excluding_zero = valid_intervals[
        (valid_intervals["ci_lower"] > 0) | (valid_intervals["ci_upper"] < 0)
    ]
    render_insight(
        f"{len(intervals_excluding_zero):,}/{len(valid_intervals):,} khoảng tin cậy "
        "pointwise 95% hiện có không chứa 0. Đây là phản ứng thăm dò trong cửa sổ "
        "non-overlap của T16, chưa hiệu chỉnh đa kiểm định và không suy luận nhân quả."
    )


def render_research_questions() -> None:
    st.markdown('<div class="section-heading">Kết luận cho 5 câu hỏi nghiên cứu</div>', unsafe_allow_html=True)
    st.caption(
        "Tóm tắt theo các báo cáo đã nghiệm thu. Kết quả là quan sát trong mạng USDT "
        "với transfer từ 500.000 USDT trở lên; không diễn giải như quan hệ nhân quả."
    )
    answers = [
        (
            "RQ1 · Cấu trúc mạng thay đổi thế nào giữa Normal và Stress?",
            "Có bằng chứng mạng mở rộng về quy mô/hoạt động: Nodes +21,90%, edges +28,75%, "
            "volume +33,98% và transactions +32,28%; các chỉ số này có ý nghĩa sau BH-FDR. "
            "Density lại giảm 17,79%. Do đó Stress đi kèm nhiều hoạt động và nhiều ví/cạnh hơn, "
            "nhưng mạng không dày đặc hơn; các chỉ số tập trung toàn mạng không đồng loạt tăng "
            "hoặc đạt ý nghĩa (7/11 chỉ số RQ1 có ý nghĩa).",
            "Nguồn: docs/T13_completion_report.md · mục 3. So sánh hồi cứu, Stress được gắn "
            "theo ETH/USDT realized volatility P90; không chứng minh Stress gây ra thay đổi mạng.",
        ),
        (
            "RQ2 · Ví trung tâm có vai trò dòng tiền lớn hơn không?",
            "Có, với thước đo incident flow: PageRank Top 1% chiếm 30,56% ở Normal và 35,61% "
            "ở Stress. Sau kiểm soát xu hướng, hệ số Stress là +3,964 điểm phần trăm "
            "(95% CI [1,9566; 5,9714], BH p≈0,000978); 7/9 tổ hợp RQ2 đạt ngưỡng 5%. "
            "Incident flow tính cả hai đầu giao dịch, không phải lượng tiền ròng hay giao dịch "
            "được đếm một lần.",
            "Nguồn: docs/T13_completion_report.md · mục 4. Vai trò trung tâm là mô tả thống kê, "
            "không xác định ví là cá nhân hoặc chứng minh contagion.",
        ),
        (
            "RQ3 · Transfer lớn / inflow sàn có dự báo volatility ngắn hạn không?",
            "Chưa có bằng chứng vững chắc. T15 không có flow predictor nào đạt ý nghĩa sau "
            "Holm ở h=1/3/7; pseudo-OOS T18 cho cả sáu nhánh/horizon có CI 95% của chênh lệch "
            "loss chứa 0. Event study T16 chỉ mô tả phản ứng quanh sự kiện; đây không phải bằng "
            "chứng nhân quả hay dự báo. Kết luận hiện tại là chưa xác nhận khả năng dự báo, "
            "không phải chứng minh không có quan hệ.",
            "Nguồn: docs/T15_T16_fix_completion_report.md và docs/T18_completion_report.md. "
            "T18 là pseudo-OOS hồi cứu; nhóm event-flow trong test còn thiếu/ít sự kiện.",
        ),
        (
            "RQ4 · Mức tập trung cộng đồng có tăng trước Stress không?",
            "Chưa đủ bằng chứng ở mức 5%. Trên 23 onset Stress và 434 mốc đối chứng, HHI tăng "
            "+0,005882 và CCI +0,001913; cả hai p Holm=0,2603, CI 95% đều chứa 0. Độ nhạy "
            "ghép theo thứ trong tuần có p Holm=0,0580, vẫn chưa đạt ngưỡng 5%.",
            "Nguồn: docs/RQ4_stress_lead_completion_report.md. Mẫu 23 đợt nhỏ; chỉ đo mạng "
            "USDT với ngưỡng transfer đã lọc, kết quả nhạy theo cách ghép đối chứng và không "
            "khẳng định tín hiệu dự báo.",
        ),
        (
            "RQ5 · GNN có phân loại hành vi tốt hơn mô hình tabular không?",
            "Trong protocol đã chọn theo validation, GraphSAGE đạt macro-F1 test 0,826479 so "
            "với 0,696718 của tabular MLP: chênh lệch +0,129761, bootstrap CI theo cụm địa chỉ "
            "95% [0,068828; 0,202705]. Đây là bằng chứng thuận lợi cho GraphSAGE so với MLP "
            "tabular trong mẫu này; không thể nói GNN là mô hình tốt nhất vì Node2Vec+MLP có "
            "điểm cao hơn nhưng dễ tận dụng dấu vết địa chỉ và có hạn chế về ví DEX mới.",
            "Nguồn: docs/T20_T22_completion_report.md. Kết quả không chứng minh tổng quát hóa "
            "ra ngoài mạng USDT hoặc khả năng dự báo nhãn theo thời gian.",
        ),
    ]
    for question, conclusion, caveat in answers:
        with st.container(border=True):
            st.markdown(f"#### {question}")
            st.markdown(conclusion)
            st.caption(caveat)


def render_app() -> None:
    apply_styles()
    st.sidebar.markdown('<div class="eyebrow">BỘ KHÁM PHÁ ON-CHAIN</div>', unsafe_allow_html=True)
    st.sidebar.markdown("### Bộ lọc dữ liệu")
    st.sidebar.selectbox("Tài sản", ["USDT"], help="Dataset nghiệm thu hiện chỉ bao gồm mạng chuyển USDT.")
    grain = st.sidebar.radio("Cửa sổ mạng", ["Tuần", "Ngày"], horizontal=True)
    metrics = load_window_metrics(grain)
    if metrics.empty:
        st.error("Không tìm thấy cửa sổ dữ liệu đồ thị.")
        return
    windows = metrics["time_window"].astype(str).tolist()
    window = st.sidebar.selectbox(
        "Chọn cửa sổ",
        windows,
        index=len(windows) - 1,
        help="Ngày hoặc tuần được chọn dùng cho đồ thị; các biểu đồ chuỗi thời gian giữ toàn lịch sử khả dụng.",
    )
    range_options = {
        "30 ngày": 30,
        "90 ngày": 90,
        "180 ngày": 180,
        "Toàn bộ đến ngày đã chọn": None,
    }
    selected_range = st.sidebar.selectbox(
        "Khoảng dữ liệu biểu đồ",
        list(range_options),
        index=1,
        help="Giới hạn số ngày đưa vào biểu đồ; chọn toàn bộ nếu cần xem trọn lịch sử.",
    )
    range_days = range_options[selected_range]
    graph_node_options = {
        "20 ví": 20,
        "40 ví": 40,
        "60 ví": 60,
        "Tất cả ví": None,
    }
    graph_edge_options = {
        "40 cạnh": 40,
        "160 cạnh": 160,
        "500 cạnh": 500,
        "Tất cả cạnh": None,
    }
    graph_node_label = st.sidebar.selectbox(
        "Ví trên đồ thị mạng",
        list(graph_node_options),
        index=1,
        help="Chọn top ví theo weighted degree hoặc tất cả ví. Bảng bên dưới luôn giữ toàn bộ ví.",
    )
    graph_edge_label = st.sidebar.selectbox(
        "Cạnh trên đồ thị mạng",
        list(graph_edge_options),
        index=1,
        help="Chọn cạnh có giá trị transfer lớn nhất trong nhóm ví đang hiển thị.",
    )
    node_limit = graph_node_options[graph_node_label]
    edge_limit = graph_edge_options[graph_edge_label]
    st.sidebar.markdown("---")
    st.sidebar.caption("Nguồn: Parquet T08–T16 đã nghiệm thu · Tài sản: USDT")
    st.sidebar.caption("Địa chỉ ví không được hiển thị; định danh chỉ là nhãn ẩn danh trong từng cửa sổ.")

    metric_row = metrics.loc[metrics["time_window"].astype(str).eq(window)].iloc[0]
    anchor = selected_window_end(grain, window, int(metric_row["days_in_window"]))
    st.markdown('<div class="eyebrow">ON-CHAIN NETWORK INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-title">Whale Network Explorer</div>', unsafe_allow_html=True)
    heading_left, heading_right = st.columns([3, 1])
    with heading_left:
        st.markdown(
            '<div class="page-subtitle">Khám phá cấu trúc giao dịch, dòng tiền và tín hiệu mạng '
            "trong dữ liệu USDT đã nghiệm thu. Các ví được hiển thị bằng nhãn ẩn danh.</div>",
            unsafe_allow_html=True,
        )
    with heading_right:
        st.markdown(
            '<div class="status-pill"><span class="status-dot"></span>Dữ liệu đã nghiệm thu · '
            f'{window}</div>',
            unsafe_allow_html=True,
        )
    st.write("")

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Tổng giá trị mạng", f"{format_usdt(metric_row['total_volume_usdt'])} USDT")
    kpi2.metric("Ví trong cửa sổ", f"{int(metric_row['num_nodes']):,}")
    kpi3.metric("Cạnh giao dịch", f"{int(metric_row['num_edges']):,}")
    kpi4.metric("Khoảng quan sát", f"{int(metric_row['days_in_window'])} ngày")

    tab_network, tab_flows, tab_reports, tab_research = st.tabs(
        ["Mạng lưới", "Dòng tiền & biến động", "Hình báo cáo", "Câu hỏi nghiên cứu"]
    )
    with tab_network:
        st.markdown('<div class="section-heading">Bản đồ giao dịch</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="muted-copy">Biểu đồ đang hiển thị {graph_node_label.lower()} và '
            f'{graph_edge_label.lower()}. Chọn “Tất cả” ở bộ lọc bên trái để xem đầy đủ. '
            "Bảng bên dưới luôn chứa toàn bộ ví. Kích thước nút biểu thị weighted degree; "
            "màu biểu thị cộng đồng.</div>",
            unsafe_allow_html=True,
        )
        figure, wallet_table = make_network_figure(
            window, grain, node_limit, edge_limit
        )
        if figure is None:
            st.info(
                "Không có cạnh trong nhóm lọc hiện tại. Hãy tăng số ví/cạnh hoặc chọn "
                "Tất cả để xem toàn mạng."
            )
        else:
            render_chart(figure)
            network_traces = figure.to_plotly_json()["data"]
            displayed_nodes = len(network_traces[1]["x"])
            displayed_edges = len(network_traces[0]["x"]) // 3
            render_insight(
                f"Đang vẽ {displayed_nodes:,} ví và {displayed_edges:,} cạnh trong số "
                f"{int(metric_row['num_edges']):,} cạnh của cửa sổ. Bảng bên dưới vẫn chứa đủ "
                f"{len(wallet_table):,} ví, xếp theo weighted degree."
            )
            with st.expander("Bảng ví · toàn bộ dữ liệu, bí danh ẩn danh", expanded=True):
                filtered_wallet_table = render_table(
                    wallet_table, "network_wallets_table", height=520
                )
                render_csv_download(
                    filtered_wallet_table,
                    "network-central-wallets-anonymous.csv",
                    "network-wallets-csv",
                )
        st.markdown(
            '<div class="disclaimer">Đồ thị chỉ là lát cắt của các giao dịch USDT đã lọc. '
            "Các nhãn ví là bí danh hiển thị, không xác định chủ sở hữu hoặc cá nhân.</div>",
            unsafe_allow_html=True,
        )

    with tab_flows:
        st.markdown('<div class="section-heading">Dòng tiền và bối cảnh thị trường</div>', unsafe_allow_html=True)
        st.caption("Đường cohort PIT dùng nhãn khả dụng theo giao thức T14.")
        visible_features = render_flow_panel(anchor, range_days)
        if len(visible_features):
            valid_pairs = visible_features[
                visible_features["whale_to_cex_pit_usdt"].notna()
                & visible_features["realized_vol"].notna()
            ]
            if len(valid_pairs):
                st.caption(
                    f"Có {len(valid_pairs)} ngày đủ dữ liệu cho dòng cohort → CEX và realized volatility."
                )

    with tab_reports:
        st.markdown('<div class="section-heading">Hình phục vụ báo cáo</div>', unsafe_allow_html=True)
        st.caption("Các biểu đồ dùng trực tiếp output T08, T11, T14 và T16; có thể chọn cửa sổ ở thanh bên.")
        st.markdown("**Community map**")
        community_options = {
            "Top 20": 20,
            "Top 50": 50,
            "Top 100": 100,
            "Tất cả": None,
        }
        community_label = st.selectbox(
            "Số cộng đồng trên biểu đồ",
            list(community_options),
            index=1,
            help="Bảng dữ liệu bên dưới luôn chứa mọi cộng đồng của cửa sổ.",
        )
        render_community_chart(
            window, grain, community_options[community_label]
        )

        st.markdown("**Whale inflow và volatility**")
        report_features = read_parquet(
            "t14/t14_features_daily.parquet",
            ("date", "whale_to_cex_pit_usdt", "realized_vol"),
        )
        report_features["date"] = pd.to_datetime(report_features["date"], errors="raise")
        report_features = report_features.dropna(
            subset=["whale_to_cex_pit_usdt", "realized_vol"]
        )
        report_features = filter_time_range(
            report_features, "date", anchor, range_days
        )
        if report_features.empty:
            st.info("Chưa có ngày đủ dữ liệu PIT để lập biểu đồ inflow–volatility.")
        else:
            scatter = px.scatter(
                report_features,
                x="whale_to_cex_pit_usdt",
                y="realized_vol",
                color="realized_vol",
                color_continuous_scale=[SURFACE_RAISED, YELLOW],
                hover_data={"date": True, "realized_vol": ":.5f", "whale_to_cex_pit_usdt": ":,.0f"},
                labels={
                    "whale_to_cex_pit_usdt": "Whale cohort → CEX (USDT)",
                    "realized_vol": "Realized volatility",
                    "date": "Ngày",
                },
                title="",
            )
            render_chart(plot_layout(scatter))
            correlation = report_features["whale_to_cex_pit_usdt"].corr(
                report_features["realized_vol"], method="spearman"
            )
            render_insight(
                f"Scatter gồm {len(report_features):,} ngày trong phạm vi đã chọn có cả hai phép đo; "
                f"tương quan Spearman mô tả = {correlation:.3f}. Đây không phải kiểm định "
                "dự báo hoặc quan hệ nhân quả."
            )
            with st.expander("Bảng dữ liệu inflow–volatility"):
                inflow_volatility_table = report_features[
                    ["date", "whale_to_cex_pit_usdt", "realized_vol"]
                ].rename(
                    columns={
                        "date": "Ngày",
                        "whale_to_cex_pit_usdt": "Whale cohort → CEX (USDT)",
                        "realized_vol": "Realized volatility",
                    }
                )
                filtered_inflow_table = render_table(
                    inflow_volatility_table, "inflow_volatility_table", height=500
                )
                render_csv_download(
                    filtered_inflow_table,
                    "whale-inflow-volatility.csv",
                    "whale-inflow-volatility-csv",
                )
        st.caption("Mối liên hệ trong mẫu, không phải bằng chứng tác động nhân quả hoặc dự báo.")

        st.markdown("**Event-time response**")
        render_event_study()

    with tab_research:
        render_research_questions()

    st.markdown("---")
    st.markdown(
        '<div class="disclaimer">Phạm vi nghiên cứu: mạng USDT đã lọc và các nhãn có thể hồi cứu. '
        "Whale score không khẳng định danh tính cá nhân; dòng tiền/volatility là mô tả liên hệ, "
        "không phải khuyến nghị đầu tư hay dự báo thị trường.</div>",
        unsafe_allow_html=True,
    )


try:
    render_app()
except FileNotFoundError as error:
    st.error(str(error))
    st.info("Kiểm tra hướng dẫn tải dữ liệu và chạy ứng dụng trong README.md.")
