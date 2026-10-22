
"""
T13 - Network Statistics, Centrality & Market Stress
Research Questions: RQ1 and RQ2

Inputs:
- T06: ETHUSDT 1-minute OHLCV, 2025-01-01 to 2026-10-17
- T08: Daily and weekly network metrics
- T09: Daily and weekly node centrality metrics

Outputs:
- 20 research CSV files
- 4 PNG figures

Method:
- Realized Volatility (RV), threshold P90
- CMSI-3 / CMSI-2 robustness
- Network Normal vs Stress comparisons
- Wallet centrality distributions
- Top-K wallet flow concentration
- OLS with HAC (Newey-West) errors
- Benjamini-Hochberg FDR
- RV threshold sensitivity (P80/P90/P95)

This is a reconstructed reproducibility pipeline.
Compare results against archived T13 CSVs before merging.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from statsmodels.stats.multitest import multipletests


PROJECT_ROOT = Path(__file__).resolve().parent

START_DATE = "2025-01-01"
END_DATE = "2026-10-17"

TOP_FRACTIONS = (0.01, 0.05, 0.10)

RANKING_METRICS = (
    "degree",
    "pagerank",
    "weighted_degree_usdt",
)

NODE_METRICS = (
    "degree",
    "weighted_degree_usdt",
    "pagerank",
)

GRAPH_METRICS = (
    "num_nodes",
    "num_edges",
    "total_volume_usdt",
    "total_transactions",
    "density",
    "reciprocity",
    "num_weakly_connected_components",
    "num_strongly_connected_components",
    "top10_volume_share",
    "gini_volume",
    "hhi_volume",
)


@dataclass
class Config:
    input_root: Path
    out_dir: Path
    fig_dir: Path
    start: str = START_DATE
    end: str = END_DATE
    strict: bool = True
    skip_figures: bool = False


def log(message):
    print(f"[T13] {message}", flush=True)


def require_columns(df, columns, name):
    missing = [c for c in columns if c not in df.columns]

    if missing:
        raise ValueError(
            f"{name}: Missing columns {missing}"
        )


def parse_dates(values, name):
    dates = pd.to_datetime(
        values,
        utc=True,
        errors="coerce",
    )

    if dates.isna().any():
        raise ValueError(
            f"{name}: Invalid datetime values"
        )

    return dates.dt.tz_localize(None).dt.normalize()


def locate_file(relative_path, root):
    """
    Resolve data locally first, then use the team's
    Hugging Face loader when available.
    """

    relative_path = str(relative_path)

    stripped = relative_path.removeprefix("data/")

    candidates = [
        root / relative_path,
        root / stripped,
        PROJECT_ROOT / relative_path,
        PROJECT_ROOT / stripped,
    ]

    for path in candidates:
        if path.is_file():
            return path

    try:
        from src.data_loader import get_data_path

    except ImportError:
        get_data_path = None

    if get_data_path is not None:
        for remote_path in dict.fromkeys(
            [relative_path, stripped]
        ):
            try:
                resolved = Path(
                    get_data_path(remote_path)
                )

                if resolved.is_file():
                    return resolved

            except Exception:
                continue

    raise FileNotFoundError(
        f"Missing input data: {relative_path}. "
        "Check Hugging Face access or --input-root."
    )


def read_parquet(relative_path, root):
    path = locate_file(relative_path, root)

    return pd.read_parquet(path)


def write_csv(df, filename, cfg, index=False):
    cfg.out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = cfg.out_dir / filename

    df.to_csv(path, index=index, encoding="utf-8-sig")
    parquet_path = path.with_suffix(".parquet")
    parquet_df = df.reset_index() if index else df
    if isinstance(parquet_df.columns, pd.MultiIndex):
        parquet_df = parquet_df.copy()
        parquet_df.columns = [
            "_".join(str(part) for part in column if part)
            for column in parquet_df.columns
        ]
    parquet_df.to_parquet(parquet_path, index=False, compression="zstd")

    log(f"Saved {filename}: {len(df):,} rows")


def get_minute_file(day, root):
    filename = (
        f"ETHUSDT_1m_{day:%Y-%m-%d}.parquet"
    )

    paths = [
        f"data/market/processed/ohlcv_1m/{filename}",
        f"market/processed/ohlcv_1m/{filename}",
    ]

    for candidate in paths:
        try:
            return locate_file(candidate, root)

        except FileNotFoundError:
            pass

    raise FileNotFoundError(
        f"Cannot find T06 data: {filename}"
    )


def compute_market_days(cfg):
    """
    Daily realized volatility:

    RV_d = sqrt(sum(r_m ** 2))

    r_m = log(close_m / close_(m-1))

    Calculated within each UTC day.
    """

    rows = []
    previous_close = None
    previous_date = None

    days = pd.date_range(
        cfg.start,
        cfg.end,
        freq="D",
    )

    for i, day in enumerate(days, 1):

        path = get_minute_file(
            day,
            cfg.input_root,
        )

        candles = pd.read_parquet(path)

        require_columns(
            candles,
            (
                "close",
                "buy_volume_usdt",
                "sell_volume_usdt",
            ),
            str(path),
        )

        if "minute" in candles.columns:
            timestamps = pd.DatetimeIndex(
                pd.to_datetime(
                    candles["minute"],
                    utc=True,
                )
            )

        elif isinstance(
            candles.index,
            pd.DatetimeIndex,
        ):
            timestamps = pd.DatetimeIndex(
                pd.to_datetime(
                    candles.index,
                    utc=True,
                )
            )

        else:
            raise ValueError(
                f"{path}: Missing minute timestamps"
            )

        expected = pd.date_range(
            day,
            periods=1440,
            freq="min",
            tz="UTC",
        )

        if not timestamps.equals(expected):
            raise ValueError(
                f"{path}: Invalid 1-minute timestamps"
            )

        close = pd.to_numeric(
            candles["close"],
            errors="coerce",
        ).to_numpy(dtype=float)

        if (
            len(close) != 1440
            or not np.isfinite(close).all()
            or (close <= 0).any()
        ):
            raise ValueError(
                f"{path}: Invalid close prices"
            )

        returns = np.diff(np.log(close))
        if previous_close is not None and previous_date == day - pd.Timedelta(days=1):
            returns = np.insert(returns, 0, np.log(close[0] / previous_close))
        previous_close = float(close[-1])
        previous_date = day

        rv = float(
            np.sqrt(
                np.sum(returns ** 2)
            )
        )

        downside = float(
            np.sqrt(
                np.sum(
                    np.minimum(returns, 0) ** 2
                )
            )
        )

        buy = pd.to_numeric(
            candles["buy_volume_usdt"],
            errors="coerce",
        ).sum()

        sell = pd.to_numeric(
            candles["sell_volume_usdt"],
            errors="coerce",
        ).sum()

        total_volume = buy + sell

        if (
            not np.isfinite(total_volume)
            or total_volume <= 0
        ):
            raise ValueError(
                f"{path}: Invalid trading volume"
            )

        sell_pressure = float(
            sell / total_volume
        )

        rows.append({
            "date": day,
            "rv": rv,
            "rv_pct": rv * 100,
            "minute_returns": len(returns),
            "candles": len(close),
            "downside": downside,
            "sell_pressure": sell_pressure,
        })

        if (
            i % 50 == 0
            or i == len(days)
        ):
            log(
                f"Processed OHLCV: "
                f"{i}/{len(days)} days"
            )

    data = pd.DataFrame(rows)

    threshold = data["rv"].quantile(0.90)

    data["regime"] = np.where(
        data["rv"] > threshold,
        "Stress",
        "Normal",
    )

    output = data[
        [
            "date",
            "rv",
            "rv_pct",
            "minute_returns",
            "candles",
            "regime",
        ]
    ].copy()

    output["date"] = output[
        "date"
    ].dt.strftime("%Y-%m-%d")

    write_csv(
        output,
        "rv_daily_regimes.csv",
        cfg,
    )

    log(
        f"Daily RV P90 = "
        f"{threshold * 100:.4f}%"
    )

    log(
        "Stress days = "
        f"{(data.regime == 'Stress').sum()}"
    )

    return data


def regime_cmsi(market, cfg):
    """
    CMSI-3:
        mean(z_RV, z_downside, z_sell_pressure)

    CMSI-2:
        mean(z_RV, z_sell_pressure)
    """

    out = market[
        [
            "date",
            "rv",
            "downside",
            "sell_pressure",
            "regime",
        ]
    ].copy()

    for metric in [
        "rv",
        "downside",
        "sell_pressure",
    ]:

        std = out[metric].std(ddof=1)

        if std <= 0:
            raise ValueError(
                f"Cannot standardize {metric}"
            )

        out[f"z_{metric}"] = (
            out[metric] - out[metric].mean()
        ) / std

    out["cmsi"] = out[
        [
            "z_rv",
            "z_downside",
            "z_sell_pressure",
        ]
    ].mean(axis=1)

    out["cmsi2"] = out[
        [
            "z_rv",
            "z_sell_pressure",
        ]
    ].mean(axis=1)

    threshold3 = out[
        "cmsi"
    ].quantile(0.90)

    threshold2 = out[
        "cmsi2"
    ].quantile(0.90)

    out["regime_cmsi"] = np.where(
        out["cmsi"] > threshold3,
        "Stress",
        "Normal",
    )

    out["stress2"] = (
        out["cmsi2"] > threshold2
    ).astype(int)

    out["regime_rv"] = out["regime"]

    ordered = [
        "date",
        "rv",
        "downside",
        "sell_pressure",
        "z_rv",
        "z_downside",
        "z_sell_pressure",
        "cmsi",
        "regime_cmsi",
        "regime_rv",
    ]

    cmsi3 = out[ordered].copy()

    cmsi3["date"] = cmsi3[
        "date"
    ].dt.strftime("%Y-%m-%d")

    write_csv(
        cmsi3,
        "cmsi_daily_regimes.csv",
        cfg,
    )

    cmsi2 = out[
        ordered + [
            "cmsi2",
            "stress2",
        ]
    ].copy()

    cmsi2["date"] = cmsi2[
        "date"
    ].dt.strftime("%Y-%m-%d")

    write_csv(
        cmsi2,
        "cmsi2_daily_regimes.csv",
        cfg,
    )

    return out

# ============================================================
# PART 2 - RQ1 & RQ2 NETWORK ANALYSIS
# ============================================================


def get_graph_daily(cfg):
    """Read T08 daily graph metrics."""

    graph = read_parquet(
        "data/processed/graphs/graph_metrics_daily.parquet",
        cfg.input_root,
    )

    require_columns(
        graph,
        ["time_window", *GRAPH_METRICS],
        "T08 daily graph metrics",
    )

    graph = graph.copy()

    graph["date"] = parse_dates(
        graph["time_window"],
        "T08 daily dates",
    )

    graph = graph.sort_values("date")

    if graph["date"].duplicated().any():
        raise ValueError(
            "Duplicate dates in T08 daily graph metrics"
        )

    return graph


def get_graph_weekly(cfg):
    """Read T08 weekly graph metrics."""

    graph = read_parquet(
        "data/processed/graphs/graph_metrics_weekly.parquet",
        cfg.input_root,
    )

    require_columns(
        graph,
        [
            "time_window",
            *GRAPH_METRICS,
            "days_in_window",
            "is_partial_week",
            "eligible_for_regression",
        ],
        "T08 weekly graph metrics",
    )

    graph = graph.copy()

    graph["time_window"] = graph["time_window"].astype(str)
    if not graph["time_window"].str.fullmatch(r"\d{4}-W\d{2}").all():
        raise ValueError("Unexpected T08 ISO weekly key")

    graph = graph.sort_values("time_window")

    return graph


def get_node_daily(cfg):
    """Read T09 daily centrality metrics."""

    nodes = read_parquet(
        "data/processed/t09/node_metrics_daily.parquet",
        cfg.input_root,
    )

    require_columns(
        nodes,
        [
            "time_window",
            "address",
            *NODE_METRICS,
        ],
        "T09 daily centrality",
    )

    nodes = nodes.copy()

    nodes["date"] = parse_dates(
        nodes["time_window"],
        "T09 daily dates",
    )

    return nodes


def get_node_weekly(cfg):
    """Read T09 weekly centrality metrics."""

    nodes = read_parquet(
        "data/processed/t09/node_metrics_weekly.parquet",
        cfg.input_root,
    )

    require_columns(
        nodes,
        [
            "time_window",
            "address",
            *NODE_METRICS,
        ],
        "T09 weekly centrality",
    )

    nodes = nodes.copy()

    nodes["time_window"] = nodes["time_window"].astype(str)
    if not nodes["time_window"].str.fullmatch(r"\d{4}-W\d{2}").all():
        raise ValueError("Unexpected T09 ISO weekly key")

    return nodes


def compare_regimes(
    df,
    metrics,
    regime_col="regime",
):
    """
    Compare mean metric values between
    Normal and Stress periods.
    """

    records = []

    for metric in metrics:

        require_columns(
            df,
            [metric, regime_col],
            "Regime comparison",
        )

        values = df[
            [metric, regime_col]
        ].copy()

        values[metric] = pd.to_numeric(
            values[metric],
            errors="coerce",
        )

        normal = values.loc[
            values[regime_col] == "Normal",
            metric,
        ].dropna()

        stress = values.loc[
            values[regime_col] == "Stress",
            metric,
        ].dropna()

        normal_mean = float(normal.mean())
        stress_mean = float(stress.mean())

        if (
            not np.isfinite(normal_mean)
            or normal_mean == 0
        ):
            difference = np.nan

        else:
            difference = (
                (stress_mean / normal_mean - 1)
                * 100
            )

        records.append({
            "metric": metric,
            "normal_mean": normal_mean,
            "stress_mean": stress_mean,
            "difference_pct": difference,
        })

    return pd.DataFrame(records)


def fit_hac(
    df,
    outcome,
    stress_col="stress",
    maxlags=7,
):
    """
    OLS regression with:
    - Stress indicator
    - Linear time trend
    - Newey-West HAC standard errors

    y_t = alpha + beta * Stress_t
          + gamma * trend_t + error_t
    """

    data = df[
        [outcome, stress_col]
    ].copy()

    data[outcome] = pd.to_numeric(
        data[outcome],
        errors="coerce",
    )

    data[stress_col] = pd.to_numeric(
        data[stress_col],
        errors="coerce",
    )

    data = data.replace(
        [np.inf, -np.inf],
        np.nan,
    ).dropna()

    if len(data) < 20:
        raise ValueError(
            f"Insufficient observations for {outcome}"
        )

    if data[stress_col].nunique() < 2:
        raise ValueError(
            f"Stress indicator has no variation: {outcome}"
        )

    data["trend"] = np.arange(
        len(data),
        dtype=float,
    )

    x = sm.add_constant(
        data[
            [stress_col, "trend"]
        ],
        has_constant="add",
    )

    y = data[outcome]

    model = sm.OLS(
        y,
        x,
    ).fit(
        cov_type="HAC",
        cov_kwds={
            "maxlags": maxlags,
        },
    )

    ci = model.conf_int().loc[
        stress_col
    ]

    return {
        "n_days": len(data),
        "stress_coef": float(
            model.params[stress_col]
        ),
        "hac_se": float(
            model.bse[stress_col]
        ),
        "p_value": float(
            model.pvalues[stress_col]
        ),
        "ci_lower": float(ci.iloc[0]),
        "ci_upper": float(ci.iloc[1]),
    }


def add_bh_fdr(df):
    """
    Benjamini-Hochberg correction
    across all tests in the input table.
    """

    result = df.copy()

    if result.empty:
        result["p_value_bh"] = pd.Series(
            dtype=float
        )
        result["significant_bh_5pct"] = pd.Series(
            dtype=bool
        )
        return result

    rejected, adjusted, _, _ = multipletests(
        result["p_value"].to_numpy(),
        alpha=0.05,
        method="fdr_bh",
    )

    result["p_value_bh"] = adjusted

    result["significant_bh_5pct"] = rejected

    return result


def build_rq1_daily(
    cfg,
    market,
    graph,
):
    """
    RQ1:
    How does network structure differ
    between Normal and Stress periods?
    """

    log("Running RQ1 daily analysis")

    data = graph.merge(
        market[
            ["date", "regime"]
        ],
        on="date",
        how="inner",
        validate="one_to_one",
    )

    data = data.sort_values(
        "date"
    ).reset_index(drop=True)

    if len(data) != len(market):
        raise ValueError(
            "T08 daily data does not cover "
            "the complete T06 market period"
        )

    descriptive = data.groupby(
        "regime"
    )[list(GRAPH_METRICS)].agg(
        ["mean", "median", "std"]
    )

    write_csv(
        descriptive,
        "network_descriptive_statistics.csv",
        cfg,
        index=True,
    )

    comparison = compare_regimes(
        data,
        GRAPH_METRICS,
    )

    write_csv(
        comparison,
        "network_normal_vs_stress.csv",
        cfg,
    )

    data["stress"] = (
        data["regime"] == "Stress"
    ).astype(int)

    tests = []

    for metric in GRAPH_METRICS:

        result = fit_hac(
            data,
            metric,
        )

        tests.append({
            "metric": metric,
            **result,
        })

    tests = pd.DataFrame(tests)

    tests = add_bh_fdr(tests)

    write_csv(
        tests,
        "rq1_network_hac_fdr_results.csv",
        cfg,
    )

    return data, comparison, tests


def distribution_summary(
    nodes,
    regime_col="regime",
):
    """
    Descriptive distribution of node-level
    centrality metrics by market regime.
    """

    records = []

    for regime in [
        "Normal",
        "Stress",
    ]:

        subset = nodes.loc[
            nodes[regime_col] == regime
        ]

        for metric in NODE_METRICS:

            values = pd.to_numeric(
                subset[metric],
                errors="coerce",
            ).replace(
                [np.inf, -np.inf],
                np.nan,
            ).dropna()

            records.append({
                "regime": regime,
                "metric": metric,
                "count": len(values),
                "mean": values.mean(),
                "median": values.median(),
                "std": values.std(),
                "p90": values.quantile(0.90),
                "p95": values.quantile(0.95),
                "p99": values.quantile(0.99),
                "max": values.max(),
            })

    return pd.DataFrame(records)


def compute_topk_concentration(
    nodes,
    window_col,
    graph,
):
    """
    Calculate the share of total incident
    flow associated with Top-K wallets.

    Each transfer contributes to both:
    sender out-strength and receiver
    in-strength.

    Therefore:
        sum(weighted_degree_usdt)
        = 2 * total network transfer volume

    Top-K flow share:
        sum(Top-K weighted degree)
        / sum(All weighted degree)

    Wallet ranking metrics:
    - degree
    - pagerank
    - weighted_degree_usdt
    """

    require_columns(
        nodes,
        [
            window_col,
            "address",
            "weighted_degree_usdt",
            *RANKING_METRICS,
        ],
        "T09 concentration input",
    )

    records = []

    grouped = nodes.groupby(
        window_col,
        sort=True,
    )

    for window, subset in grouped:

        subset = subset.copy()

        n = len(subset)

        if n == 0:
            continue

        total_flow = pd.to_numeric(
            subset["weighted_degree_usdt"],
            errors="coerce",
        ).sum()

        if graph is not None:
            matching = graph.loc[graph[window_col] == window]
            if len(matching) != 1:
                raise ValueError(f"T08 missing/duplicate window: {window}")
            ref = matching.iloc[0]
            if n != int(ref["num_nodes"]):
                raise ValueError(f"T08/T09 node mismatch: {window}")
            if not np.isclose(total_flow, 2 * float(ref["total_volume_usdt"]), rtol=1e-6, atol=1e-6):
                raise ValueError(f"T08/T09 incident flow mismatch: {window}")

        if (
            not np.isfinite(total_flow)
            or total_flow <= 0
        ):
            continue

        for ranking_metric in RANKING_METRICS:

            ranked = subset.sort_values(
                [
                    ranking_metric,
                    "address",
                ],
                ascending=[
                    False,
                    True,
                ],
                kind="stable",
            )

            for fraction in TOP_FRACTIONS:

                top_k = max(
                    1,
                    math.ceil(
                        n * fraction
                    ),
                )

                top = ranked.head(top_k)

                top_flow = pd.to_numeric(
                    top["weighted_degree_usdt"],
                    errors="coerce",
                ).sum()

                share = float(
                    top_flow / total_flow
                )

                node_share = (
                    top_k / n * 100
                )

                records.append({
                    window_col: window,
                    "ranking_metric": ranking_metric,
                    "top_fraction": fraction,
                    "num_nodes": n,
                    "top_k": top_k,
                    "flow_share": share,
                    "flow_share_pct": share * 100,
                    "node_share_pct": node_share,
                    "concentration_ratio": (
                        share * 100 / node_share
                    ),
                })

    result = pd.DataFrame(records)

    if result.empty:
        raise ValueError(
            "No valid Top-K concentration snapshots"
        )

    return result


def concentration_summary(
    concentration,
):
    """Regime-wise Top-K concentration summary."""

    summary = (
        concentration.groupby(
            [
                "regime",
                "ranking_metric",
                "top_fraction",
            ],
            as_index=False,
        )
        .agg(
            snapshots=(
                "flow_share_pct",
                "size",
            ),
            mean_flow_share_pct=(
                "flow_share_pct",
                "mean",
            ),
            median_flow_share_pct=(
                "flow_share_pct",
                "median",
            ),
            std_flow_share_pct=(
                "flow_share_pct",
                "std",
            ),
            mean_concentration_ratio=(
                "concentration_ratio",
                "mean",
            ),
        )
    )

    return summary


def concentration_comparison(
    concentration,
):
    """
    Mean Top-K flow share in Normal
    versus Stress periods.
    """

    comparison = (
        concentration.groupby(
            [
                "ranking_metric",
                "top_fraction",
                "regime",
            ]
        )["flow_share_pct"]
        .mean()
        .unstack("regime")
        .reset_index()
    )

    for regime in [
        "Normal",
        "Stress",
    ]:
        if regime not in comparison.columns:
            raise ValueError(
                f"Missing regime in concentration: "
                f"{regime}"
            )

    comparison["difference_pp"] = (
        comparison["Stress"]
        - comparison["Normal"]
    )

    return comparison[
        [
            "ranking_metric",
            "top_fraction",
            "Normal",
            "Stress",
            "difference_pp",
        ]
    ]


def concentration_hac(
    concentration,
):
    """
    HAC regression for each combination of:
    - Wallet ranking metric
    - Top-K fraction
    """

    records = []

    for ranking_metric in RANKING_METRICS:

        for fraction in TOP_FRACTIONS:

            subset = concentration.loc[
                (
                    concentration[
                        "ranking_metric"
                    ] == ranking_metric
                )
                &
                (
                    np.isclose(
                        concentration[
                            "top_fraction"
                        ].to_numpy(),
                        fraction,
                    )
                )
            ].sort_values("date")

            result = fit_hac(
                subset,
                "flow_share_pct",
            )

            records.append({
                "ranking_metric": ranking_metric,
                "top_fraction": fraction,
                "stress_coef_pp": result[
                    "stress_coef"
                ],
                "hac_se": result[
                    "hac_se"
                ],
                "p_value": result[
                    "p_value"
                ],
                "ci_lower": result[
                    "ci_lower"
                ],
                "ci_upper": result[
                    "ci_upper"
                ],
                "n_days": result[
                    "n_days"
                ],
                "significant_5pct": (
                    result["p_value"] < 0.05
                ),
            })

    return pd.DataFrame(records)


def build_rq2_daily(
    cfg,
    market,
    nodes,
    graph_daily,
):
    """
    RQ2:
    Do central wallets account for a
    disproportionate share of transfer flows?
    """

    log("Running RQ2 daily analysis")

    nodes = nodes.merge(
        market[
            ["date", "regime"]
        ],
        on="date",
        how="inner",
        validate="many_to_one",
    )

    if nodes.empty:
        raise ValueError(
            "No T09 node data matched T06 dates"
        )

    distribution = distribution_summary(
        nodes
    )

    write_csv(
        distribution,
        "centrality_distribution_daily.csv",
        cfg,
    )

    concentration = compute_topk_concentration(
        nodes,
        "date",
        graph_daily,
    )

    concentration = concentration.merge(
        market[
            ["date", "regime"]
        ],
        on="date",
        how="left",
        validate="many_to_one",
    )

    concentration = concentration.sort_values(
        [
            "date",
            "ranking_metric",
            "top_fraction",
        ]
    ).reset_index(drop=True)

    daily_output = concentration.copy()

    daily_output["date"] = daily_output[
        "date"
    ].dt.strftime("%Y-%m-%d")

    write_csv(
        daily_output,
        "central_wallet_concentration_daily.csv",
        cfg,
    )

    summary = concentration_summary(
        concentration
    )

    write_csv(
        summary,
        "central_wallet_concentration_summary.csv",
        cfg,
    )

    comparison = concentration_comparison(
        concentration
    )

    write_csv(
        comparison,
        "central_wallet_concentration_comparison.csv",
        cfg,
    )

    concentration["stress"] = (
        concentration["regime"] == "Stress"
    ).astype(int)

    tests = concentration_hac(
        concentration
    )

    write_csv(
        tests,
        "rq2_concentration_hac_tests.csv",
        cfg,
    )

    tests_fdr = add_bh_fdr(
        tests
    )

    write_csv(
        tests_fdr,
        "rq2_hac_fdr_results.csv",
        cfg,
    )

    return (
        nodes,
        concentration,
        distribution,
        comparison,
        tests_fdr,
    )

# ============================================================
# PART 3 - WEEKLY, ROBUSTNESS, FIGURES & MAIN
# ============================================================


def build_weekly(
    cfg,
    market,
    graph_weekly,
    nodes_weekly,
):
    """
    Weekly RQ1/RQ2 analysis.

    Only complete 7-day weeks are included
    in comparisons and statistical summaries.

    Weekly RV:
        sqrt(sum(daily RV ** 2))
    """

    log("Running weekly analysis")

    daily = market[
        ["date", "rv"]
    ].copy()

    iso = daily["date"].dt.isocalendar()
    daily["time_window"] = (
        iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    )

    weekly_rv = (
        daily.groupby(
            "time_window",
            as_index=False,
        )
        .agg(
            rv_weekly=(
                "rv",
                lambda x: float(
                    np.sqrt(
                        np.sum(
                            np.square(
                                x.to_numpy(
                                    dtype=float
                                )
                            )
                        )
                    )
                ),
            ),
            observed_days=(
                "date",
                "nunique",
            ),
        )
    )

    weekly = graph_weekly.merge(
        weekly_rv,
        on="time_window",
        how="left",
        validate="one_to_one",
    )

    complete = (
        weekly["days_in_window"].eq(7)
        & weekly["eligible_for_regression"].eq(True)
        & weekly["observed_days"].eq(7)
        & weekly["rv_weekly"].notna()
    )

    if not complete.any():
        raise ValueError(
            "No complete T08/T06 weekly observations"
        )

    threshold = weekly.loc[
        complete,
        "rv_weekly",
    ].quantile(0.90)

    weekly["regime"] = np.where(
        complete
        & (weekly["rv_weekly"] > threshold),
        "Stress",
        "Normal",
    )

    weekly.loc[
        ~complete,
        "regime",
    ] = "Excluded"

    weekly_out = weekly.loc[complete].copy()

    write_csv(
        weekly_out,
        "rv_weekly_regimes.csv",
        cfg,
    )

    eligible = weekly.loc[
        complete
    ].copy()

    weekly_comparison = compare_regimes(
        eligible,
        GRAPH_METRICS,
    )

    write_csv(
        weekly_comparison,
        "rq1_network_weekly_comparison.csv",
        cfg,
    )

    # Only T09 weekly node snapshots
    # associated with complete T08 weeks.
    node_data = nodes_weekly.merge(
        eligible[
            ["time_window", "regime"]
        ],
        on="time_window",
        how="inner",
        validate="many_to_one",
    )

    if node_data.empty:
        raise ValueError(
            "No valid T09 weekly centrality data"
        )

    distribution_rows = []
    # First calculate each week's statistics; then average weeks in each regime.
    for (week, regime), group in node_data.groupby(["time_window", "regime"], sort=True):
        for metric in NODE_METRICS:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            distribution_rows.append({
                "time_window": week, "regime": regime, "metric": metric,
                "mean": values.mean(), "median": values.median(),
                "p95": values.quantile(.95), "p99": values.quantile(.99),
            })
    per_week = pd.DataFrame(distribution_rows)
    distribution = per_week.groupby(["regime", "metric"], as_index=False).agg(
        weeks=("time_window", "nunique"), mean=("mean", "mean"),
        median=("median", "mean"), p95=("p95", "mean"),
        p99=("p99", "mean"),
    )

    write_csv(
        distribution,
        "rq2_centrality_distribution_weekly.csv",
        cfg,
    )

    concentration = compute_topk_concentration(
        node_data,
        "time_window",
        eligible,
    )

    concentration = concentration.merge(
        eligible[
            ["time_window", "regime"]
        ],
        on="time_window",
        how="left",
        validate="many_to_one",
    )

    summary = (
        concentration.groupby(
            [
                "regime",
                "ranking_metric",
                "top_fraction",
            ],
            as_index=False,
        )
        .agg(
            weeks=(
                "flow_share_pct",
                "size",
            ),
            mean_flow_share_pct=(
                "flow_share_pct",
                "mean",
            ),
            median_flow_share_pct=(
                "flow_share_pct",
                "median",
            ),
            mean_concentration_ratio=(
                "concentration_ratio",
                "mean",
            ),
        )
    )

    write_csv(
        summary,
        "rq2_concentration_weekly_summary.csv",
        cfg,
    )

    comparison = concentration_comparison(
        concentration
    )

    write_csv(
        comparison,
        "rq2_concentration_weekly_comparison.csv",
        cfg,
    )

    return (
        weekly,
        eligible,
        weekly_comparison,
        node_data,
        distribution,
        concentration,
        comparison,
    )


def fit_robustness(
    data,
    outcome,
    stress_indicator,
):
    """
    HAC model with alternative stress indicator.

    Returns the Stress coefficient and
    HAC-based confidence interval.
    """

    frame = data.copy()

    frame["_alternative_stress"] = (
        stress_indicator
    )

    return fit_hac(
        frame,
        outcome,
        stress_col="_alternative_stress",
        maxlags=7,
    )


def build_robustness(
    cfg,
    market,
    cmsi,
    rq1_daily,
    concentration,
):
    """
    Robustness analyses:

    1. RV P80/P90/P95 thresholds
    2. CMSI-3 alternative regime
    3. CMSI-2 alternative regime

    Primary outcomes:
    - RQ1 num_edges
    - RQ1 total_volume_usdt
    - RQ2 PageRank Top 1% flow share
    """

    log("Running sensitivity and robustness tests")

    rq2 = concentration.loc[
        (
            concentration["ranking_metric"]
            == "pagerank"
        )
        &
        (
            np.isclose(
                concentration[
                    "top_fraction"
                ].to_numpy(),
                0.01,
            )
        )
    ][
        ["date", "flow_share_pct"]
    ].copy()

    if rq2["date"].duplicated().any():
        raise ValueError(
            "Duplicate RQ2 PageRank Top 1% dates"
        )

    rq1 = rq1_daily[
        [
            "date",
            "num_edges",
            "total_volume_usdt",
        ]
    ].copy()

    combined = (
        market[
            ["date", "rv"]
        ]
        .merge(
            rq1,
            on="date",
            validate="one_to_one",
        )
        .merge(
            rq2,
            on="date",
            validate="one_to_one",
        )
        .merge(
            cmsi[
                [
                    "date",
                    "regime_cmsi",
                    "stress2",
                ]
            ],
            on="date",
            validate="one_to_one",
        )
        .sort_values("date")
        .reset_index(drop=True)
    )

    if len(combined) != len(market):
        raise ValueError(
            "Robustness inputs do not cover "
            "all market dates"
        )

    outcomes = [
        ("RQ1", "num_edges", "num_edges"),
        (
            "RQ1",
            "total_volume_usdt",
            "total_volume_usdt",
        ),
        (
            "RQ2",
            "pagerank_top1_flow_share_pct",
            "flow_share_pct",
        ),
    ]

    sensitivity_rows = []

    for quantile in [
        0.80,
        0.90,
        0.95,
    ]:
        threshold = combined[
            "rv"
        ].quantile(quantile)

        stress = (
            combined["rv"] > threshold
        ).astype(int)

        for rq, label, outcome in outcomes:

            result = fit_robustness(
                combined,
                outcome,
                stress,
            )

            sensitivity_rows.append({
                "rq": rq,
                "metric": label,
                "rv_quantile": quantile,
                "rv_threshold_pct": (
                    threshold * 100
                ),
                "stress_days": int(
                    stress.sum()
                ),
                "stress_coef": result[
                    "stress_coef"
                ],
                "p_value": result[
                    "p_value"
                ],
                "ci_lower": result[
                    "ci_lower"
                ],
                "ci_upper": result[
                    "ci_upper"
                ],
            })

    sensitivity = pd.DataFrame(
        sensitivity_rows
    )

    write_csv(
        sensitivity,
        "rv_threshold_sensitivity.csv",
        cfg,
    )

    # CMSI-3: RV + downside + sell pressure
    cmsi3_stress = (
        combined["regime_cmsi"]
        == "Stress"
    ).astype(int)

    cmsi3_rows = []

    for rq, label, outcome in outcomes:

        result = fit_robustness(
            combined,
            outcome,
            cmsi3_stress,
        )

        cmsi3_rows.append({
            "rq": rq,
            "metric": label,
            "stress_coef": result[
                "stress_coef"
            ],
            "p_value": result[
                "p_value"
            ],
            "ci_lower": result[
                "ci_lower"
            ],
            "ci_upper": result[
                "ci_upper"
            ],
            "n_days": result[
                "n_days"
            ],
        })

    cmsi3_results = pd.DataFrame(
        cmsi3_rows
    )

    write_csv(
        cmsi3_results,
        "cmsi_robustness_results.csv",
        cfg,
    )

    # CMSI-2: RV + sell pressure
    cmsi2_stress = combined[
        "stress2"
    ].astype(int)

    cmsi2_rows = []

    for rq, label, outcome in outcomes:

        result = fit_robustness(
            combined,
            outcome,
            cmsi2_stress,
        )

        cmsi2_rows.append({
            "rq": rq,
            "metric": label,
            "stress_coef": result[
                "stress_coef"
            ],
            "p_value": result[
                "p_value"
            ],
            "ci_lower": result[
                "ci_lower"
            ],
            "ci_upper": result[
                "ci_upper"
            ],
        })

    cmsi2_results = pd.DataFrame(
        cmsi2_rows
    )

    write_csv(
        cmsi2_results,
        "cmsi2_robustness_results.csv",
        cfg,
    )

    return (
        sensitivity,
        cmsi3_results,
        cmsi2_results,
    )


def build_figures(cfg, market, rq1_daily, rq1_comparison, distribution, concentration):
    """Reproduce the original four T13 PNG plots."""
    if cfg.skip_figures:
        return
    cfg.fig_dir.mkdir(parents=True, exist_ok=True)
    daily = rq1_daily.sort_values("date").copy()
    dates = pd.to_datetime(daily["date"])
    stress = daily["regime"].eq("Stress")

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(dates, daily["num_edges"], linewidth=1)
    ax.scatter(dates[stress], daily.loc[stress, "num_edges"], s=12, label="Stress days")
    ax.set(title="USDT Network Dynamics", xlabel="Date", ylabel="Number of edges")
    ax.legend(); fig.autofmt_xdate(); fig.tight_layout()
    fig.savefig(cfg.fig_dir / "network_dynamics.png", dpi=200); plt.close(fig)

    nodes = read_parquet("data/processed/t09/node_metrics_daily.parquet", cfg.input_root)
    degrees = pd.to_numeric(nodes["degree"], errors="coerce").dropna()
    if degrees.empty or (degrees < 0).any():
        raise ValueError("Invalid degree distribution")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(np.log1p(degrees), bins=70)
    ax.set(title="Daily Node Degree Distribution", xlabel="log(1 + Degree)", ylabel="Node-window frequency")
    fig.tight_layout()
    fig.savefig(cfg.fig_dir / "centrality_distribution.png", dpi=200); plt.close(fig)

    pr = concentration.loc[concentration["ranking_metric"].eq("pagerank")]
    pivot = pr.groupby(["top_fraction", "regime"])["flow_share_pct"].mean().unstack()
    pivot = pivot.loc[[0.01, 0.05, 0.10], ["Normal", "Stress"]]
    fig, ax = plt.subplots(figsize=(9, 5))
    xs = np.arange(3); width = .36
    ax.bar(xs - width/2, pivot["Normal"], width, label="Normal")
    ax.bar(xs + width/2, pivot["Stress"], width, label="Stress")
    ax.set_xticks(xs, ["Top 1%", "Top 5%", "Top 10%"])
    ax.set(title="PageRank Central Wallet Flow Concentration", ylabel="Incident flow share (%)")
    ax.legend(); fig.tight_layout()
    fig.savefig(cfg.fig_dir / "flow_concentration.png", dpi=200); plt.close(fig)

    metrics = ["num_nodes", "num_edges", "total_transactions"]
    changes = rq1_comparison.set_index("metric").loc[metrics, "difference_pct"]
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(["Nodes", "Edges", "Transactions"], changes)
    ax.bar_label(bars, fmt="%.1f%%", padding=3)
    ax.set(title="Network Activity: Stress vs Normal", ylabel="Difference in means (%)")
    fig.tight_layout()
    fig.savefig(cfg.fig_dir / "normal_vs_stress.png", dpi=200); plt.close(fig)
    log("Saved four original-style T13 figures")



def validate_pipeline(
    cfg,
    market,
    graph_daily,
    nodes_daily,
    eligible_weekly,
):
    """
    Validate the primary sample structure.

    Expected:
    - 655 daily observations
    - 589 Normal days
    - 66 Stress days
    - 92 complete weekly observations
    """

    expected_days = len(
        pd.date_range(
            cfg.start,
            cfg.end,
            freq="D",
        )
    )

    if len(market) != expected_days:
        raise ValueError(
            "Market daily sample length mismatch"
        )

    normal = int(
        market["regime"].eq("Normal").sum()
    )

    stress = int(
        market["regime"].eq("Stress").sum()
    )

    if len(graph_daily) != expected_days:
        raise ValueError(
            "T08 daily sample length mismatch"
        )

    node_days = nodes_daily[
        "date"
    ].nunique()

    if node_days != expected_days:
        raise ValueError(
            "T09 daily coverage mismatch"
        )

    log(
        f"Daily sample: {expected_days}, "
        f"Normal: {normal}, Stress: {stress}"
    )

    log(
        f"Eligible weekly observations: "
        f"{len(eligible_weekly)}"
    )

    if cfg.strict:
        if (
            expected_days != 655
            or normal != 589
            or stress != 66
            or len(eligible_weekly) != 92
        ):
            raise ValueError(
                "Strict T13 sample validation failed"
            )

    log("Pipeline validation completed")


def run_pipeline(cfg):
    """
    Execute the complete T13 research workflow.
    """

    log("=" * 60)
    log("T13 NETWORK STATISTICS PIPELINE")
    log("=" * 60)

    cfg.out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    cfg.fig_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Step 1: Market stress regimes
    market = compute_market_days(
        cfg
    )

    cmsi = regime_cmsi(
        market,
        cfg,
    )

    # Step 2: Load T08 and T09
    graph_daily = get_graph_daily(
        cfg
    )

    graph_weekly = get_graph_weekly(
        cfg
    )

    nodes_daily = get_node_daily(
        cfg
    )

    nodes_weekly = get_node_weekly(
        cfg
    )

    # Step 3: Daily RQ1
    (
        rq1_daily,
        rq1_comparison,
        rq1_tests,
    ) = build_rq1_daily(
        cfg,
        market,
        graph_daily,
    )

    # Step 4: Daily RQ2
    (
        node_daily,
        concentration,
        distribution,
        rq2_comparison,
        rq2_tests,
    ) = build_rq2_daily(
        cfg,
        market,
        nodes_daily,
        graph_daily,
    )

    # Step 5: Weekly RQ1/RQ2
    (
        weekly,
        eligible_weekly,
        weekly_comparison,
        node_weekly,
        weekly_distribution,
        weekly_concentration,
        weekly_concentration_comparison,
    ) = build_weekly(
        cfg,
        market,
        graph_weekly,
        nodes_weekly,
    )

    # Step 6: Sensitivity and CMSI robustness
    build_robustness(
        cfg,
        market,
        cmsi,
        rq1_daily,
        concentration,
    )

    # Step 7: Visualizations
    build_figures(
        cfg,
        market,
        rq1_daily,
        rq1_comparison,
        distribution,
        concentration,
    )

    # Step 8: Sample validation
    validate_pipeline(
        cfg,
        market,
        graph_daily,
        node_daily,
        eligible_weekly,
    )

    log("=" * 60)
    log("T13 PIPELINE FINISHED")
    log(f"CSV directory: {cfg.out_dir}")
    log(f"Figure directory: {cfg.fig_dir}")
    log("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run T13 network statistics, "
            "centrality and stress analysis"
        )
    )

    parser.add_argument(
        "--input-root",
        type=Path,
        default=PROJECT_ROOT,
        help=(
            "Local project/data root. "
            "Falls back to the shared data loader."
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "data"
            / "processed"
            / "t13_recomputed"
        ),
        help="Directory for T13 CSV outputs",
    )

    parser.add_argument(
        "--figure-dir",
        type=Path,
        default=(
            PROJECT_ROOT
            / "outputs"
            / "figures"
            / "t13_recomputed"
        ),
        help="Directory for T13 PNG figures",
    )

    parser.add_argument(
        "--start",
        default=START_DATE,
    )

    parser.add_argument(
        "--end",
        default=END_DATE,
    )

    parser.add_argument(
        "--no-strict",
        action="store_true",
        help=(
            "Disable fixed 655-day and "
            "92-week reference checks"
        ),
    )

    parser.add_argument(
        "--skip-figures",
        action="store_true",
    )

    args = parser.parse_args()

    cfg = Config(
        input_root=args.input_root,
        out_dir=args.output_dir,
        fig_dir=args.figure_dir,
        start=args.start,
        end=args.end,
        strict=not args.no_strict,
        skip_figures=args.skip_figures,
    )

    if cfg.out_dir.resolve() == (PROJECT_ROOT / "data/processed/t13").resolve():
        raise ValueError("Refusing to overwrite archived T13 output folder")
    run_pipeline(cfg)


if __name__ == "__main__":
    main()
