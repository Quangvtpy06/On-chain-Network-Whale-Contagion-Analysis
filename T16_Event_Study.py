"""
T16_Event_Study.py
==================
Event study for three on-chain event types:
  1. large_transfer  — daily large-transfer count exceeds rolling-90d p95
  2. whale_inflow    — pit_cex_netflow_z > +2.0 (whale-to-exchange PIT inflow spike)
  3. concentration   — community_concentration_index exceeds rolling-90d p90

For each event type, compute the average and median response of:
  volatility (log_rv), volume (log_volume_usdt), spread (spread_cs_proxy), return (ret_1d)
across the event window tau = -k ... +k days (default k=5).

Bootstrap 95% confidence intervals for the mean at each tau.

Results describe *event-linked associations*, not causal effects.

Dependencies: T14 (t14_features_daily.parquet), T11 (snapshot_metrics_daily.parquet)
Does NOT depend on T13.

Outputs
-------
  data/market_data/data/processed/t16/t16_event_study_results.parquet
  data/market_data/data/processed/t16/t16_event_list.parquet
  data/market_data/data/processed/t16/figures/t16_<event_type>_response.png  (x3)

Usage
-----
  python T16_Event_Study.py [--window K] [--event-type {all,large_transfer,whale_inflow,concentration}]
                            [--bootstrap-n N] [--seed S]
"""

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.resolve()
_PROCESSED = _REPO_ROOT / "data" / "market_data" / "data" / "processed"

# T14 features (primary input)
_T14_PRIMARY = _PROCESSED / "t14" / "t14_features_daily.parquet"
_T14_FALLBACK = _REPO_ROOT / "data" / "processed" / "t14" / "t14_features_daily.parquet"

# T11 snapshot metrics (for concentration index)
_T11_PRIMARY = _PROCESSED / "t11" / "snapshot_metrics_daily.parquet"

# Output directory
_OUT_DIR = _PROCESSED / "t16"
_FIG_DIR = _OUT_DIR / "figures"

# ---------------------------------------------------------------------------
# Constants — thresholds are DEFAULT assumptions, not yet confirmed with team
# ---------------------------------------------------------------------------
LARGE_TRANSFER_LOOKBACK = 90   # rolling window for percentile (days)
LARGE_TRANSFER_PERCENTILE = 0.95  # [DEFAULT] p95 of rolling count

WHALE_INFLOW_Z_THRESHOLD = 2.0  # [DEFAULT] pit_cex_netflow_z > +2.0 std

CONCENTRATION_LOOKBACK = 90   # rolling window for percentile (days)
CONCENTRATION_PERCENTILE = 0.90  # [DEFAULT] p90 of rolling community_concentration_index

RESPONSE_VARS = ["log_rv", "log_volume_usdt", "spread_cs_proxy", "ret_1d"]
RESPONSE_LABELS = {
    "log_rv": "Log Realized Volatility",
    "log_volume_usdt": "Log Volume (USDT)",
    "spread_cs_proxy": "Spread (CS proxy)",
    "ret_1d": "Daily Return",
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_t14() -> pd.DataFrame:
    """Load T14 features parquet; try primary path, fall back to secondary."""
    for path in [_T14_PRIMARY, _T14_FALLBACK]:
        if path.exists():
            df = pd.read_parquet(path)
            print(f"[INFO] Loaded T14 from: {path}")
            print(f"[INFO] T14 shape: {df.shape}")
            return df
    raise FileNotFoundError(
        f"T14 parquet not found at:\n  {_T14_PRIMARY}\n  {_T14_FALLBACK}"
    )


def _load_t11() -> pd.DataFrame:
    """Load T11 daily snapshot metrics (for concentration index)."""
    if not _T11_PRIMARY.exists():
        raise FileNotFoundError(f"T11 parquet not found at: {_T11_PRIMARY}")
    df = pd.read_parquet(_T11_PRIMARY)
    print(f"[INFO] Loaded T11 from: {_T11_PRIMARY}")
    # Keep only daily rows
    if "window_type" in df.columns:
        df = df[df["window_type"] == "daily"].copy()
    return df


def _build_combined(df14: pd.DataFrame, df11: pd.DataFrame) -> pd.DataFrame:
    """
    Merge T14 and T11 on date string, producing a single daily DataFrame
    with all response variables and event signal columns.
    """
    # Ensure date columns are consistent string format "YYYY-MM-DD"
    df14 = df14.copy()
    df14["date"] = pd.to_datetime(df14["date"]).dt.strftime("%Y-%m-%d")

    df11 = df11.copy()
    df11["date"] = pd.to_datetime(df11["time_window"]).dt.strftime("%Y-%m-%d")

    # Select only needed T11 columns to avoid name conflicts
    t11_cols = ["date", "community_concentration_index", "hhi_volume", "hhi_community_volume"]
    t11_cols = [c for c in t11_cols if c in df11.columns]
    df11_sub = df11[t11_cols].drop_duplicates("date")

    combined = df14.merge(df11_sub, on="date", how="left", suffixes=("", "_t11"))
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.sort_values("date").reset_index(drop=True)
    print(f"[INFO] Combined shape after merge: {combined.shape}")
    print(f"[INFO] Date range: {combined['date'].min().date()} -> {combined['date'].max().date()}")
    return combined


# ---------------------------------------------------------------------------
# Event detection (all point-in-time: thresholds based on past data only)
# ---------------------------------------------------------------------------

def _rolling_pit_percentile(series: pd.Series, window: int, q: float) -> pd.Series:
    """
    Compute rolling backward-looking percentile threshold (point-in-time).
    At each time t, threshold = quantile(series[t-window : t-1], q).
    Returns the threshold series (NaN for first `window` rows).
    """
    # shift(1) ensures we never include the current observation in the threshold
    return series.shift(1).rolling(window=window, min_periods=max(30, window // 3)).quantile(q)


def detect_large_transfer_events(df: pd.DataFrame) -> pd.Series:
    """
    Event type 1: large_transfer_count > rolling-90d p95 (point-in-time).
    Returns boolean Series aligned to df index.
    [DEFAULT threshold: p95, lookback=90d — not yet confirmed with team]
    """
    col = "large_transfer_count"
    if col not in df.columns:
        warnings.warn(f"Column '{col}' not found; large_transfer events will be empty.")
        return pd.Series(False, index=df.index)

    threshold = _rolling_pit_percentile(df[col], LARGE_TRANSFER_LOOKBACK, LARGE_TRANSFER_PERCENTILE)
    events = (df[col] > threshold) & df[col].notna() & threshold.notna()
    return events


def detect_whale_inflow_events(df: pd.DataFrame) -> pd.Series:
    """
    Event type 2: pit_cex_netflow_z > +2.0 (whale-to-exchange inflow spike, PIT).
    The column is already standardised PIT, so a fixed threshold suffices.
    [DEFAULT threshold: +2.0 std — not yet confirmed with team]
    """
    col = "pit_cex_netflow_z"
    if col not in df.columns:
        warnings.warn(f"Column '{col}' not found; whale_inflow events will be empty.")
        return pd.Series(False, index=df.index)

    events = (df[col] > WHALE_INFLOW_Z_THRESHOLD) & df[col].notna()
    return events


def detect_concentration_events(df: pd.DataFrame) -> pd.Series:
    """
    Event type 3: community_concentration_index > rolling-90d p90 (point-in-time).
    [DEFAULT threshold: p90, lookback=90d — not yet confirmed with team]
    """
    col = "community_concentration_index"
    if col not in df.columns:
        warnings.warn(f"Column '{col}' not found; concentration events will be empty.")
        return pd.Series(False, index=df.index)

    threshold = _rolling_pit_percentile(df[col], CONCENTRATION_LOOKBACK, CONCENTRATION_PERCENTILE)
    events = (df[col] > threshold) & df[col].notna() & threshold.notna()
    return events


# ---------------------------------------------------------------------------
# Event window extraction
# ---------------------------------------------------------------------------

def extract_event_windows(
    df: pd.DataFrame,
    event_mask: pd.Series,
    response_vars: list[str],
    k: int,
) -> pd.DataFrame:
    """
    For each event date, extract a window of tau = -k ... +k rows.
    Returns long-format DataFrame with columns:
      event_date, tau, <response_var_1>, <response_var_2>, ...

    Rows where any response variable is missing are kept (NaN propagates to mean).
    """
    event_idx = df.index[event_mask].tolist()
    records = []
    n = len(df)

    for idx in event_idx:
        event_date = df.loc[idx, "date"]
        for tau in range(-k, k + 1):
            target_idx = idx + tau
            if target_idx < 0 or target_idx >= n:
                continue
            row = {"event_date": event_date, "tau": tau}
            for var in response_vars:
                row[var] = df.loc[target_idx, var] if var in df.columns else np.nan
            records.append(row)

    if not records:
        return pd.DataFrame(columns=["event_date", "tau"] + response_vars)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------

def _bootstrap_ci(arr: np.ndarray, n_boot: int, seed: int, alpha: float = 0.05):
    """
    Compute bootstrap (percentile) 95% CI for the mean of arr.
    Returns (lower, upper). NaN values are dropped before resampling.
    """
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    boots = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo = np.percentile(boots, 100 * alpha / 2)
    hi = np.percentile(boots, 100 * (1 - alpha / 2))
    return lo, hi


def compute_event_study_stats(
    windows_df: pd.DataFrame,
    response_vars: list[str],
    k: int,
    n_boot: int,
    seed: int,
) -> pd.DataFrame:
    """
    Aggregate event windows into mean, median, CI per (tau, variable).
    Returns long-format DataFrame:
      tau | variable | mean | median | ci_lower | ci_upper | n_events
    """
    rows = []
    taus = list(range(-k, k + 1))

    for tau in taus:
        tau_df = windows_df[windows_df["tau"] == tau]
        n_events = len(tau_df)
        for var in response_vars:
            if var not in tau_df.columns:
                continue
            vals = tau_df[var].values.astype(float)
            valid = vals[~np.isnan(vals)]
            mean_val = float(np.mean(valid)) if len(valid) > 0 else np.nan
            median_val = float(np.median(valid)) if len(valid) > 0 else np.nan
            ci_lo, ci_hi = _bootstrap_ci(vals, n_boot, seed + tau + hash(var) % 1000)
            rows.append(
                {
                    "tau": tau,
                    "variable": var,
                    "mean": mean_val,
                    "median": median_val,
                    "ci_lower": ci_lo,
                    "ci_upper": ci_hi,
                    "n_observations": int(np.sum(~np.isnan(vals))),
                    "n_events_at_tau": n_events,
                }
            )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_event_study(
    stats_df: pd.DataFrame,
    event_type: str,
    n_events: int,
    response_vars: list[str],
    out_path: Path,
    k: int,
) -> None:
    """
    One figure per event type: 2x2 subplot grid (one per response variable).
    Shows mean ± 95% bootstrap CI, with tau=0 highlighted.
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    axes = axes.flatten()

    title_map = {
        "large_transfer": "Event Type 1: Large Transfer Spike",
        "whale_inflow": "Event Type 2: Whale-to-Exchange Inflow Spike",
        "concentration": "Event Type 3: Network Concentration Spike",
    }
    fig.suptitle(
        f"{title_map.get(event_type, event_type)}\n"
        f"n={n_events} events | Event-linked response (not causal)",
        fontsize=13,
        fontweight="bold",
    )

    taus = sorted(stats_df["tau"].unique())

    for ax, var in zip(axes, response_vars):
        sub = stats_df[stats_df["variable"] == var].sort_values("tau")
        if sub.empty:
            ax.set_title(RESPONSE_LABELS.get(var, var))
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            continue

        t = sub["tau"].values
        mean_ = sub["mean"].values
        ci_lo = sub["ci_lower"].values
        ci_hi = sub["ci_upper"].values

        ax.axvline(0, color="red", linestyle="--", linewidth=1.2, alpha=0.7, label="Event (tau=0)")
        ax.axhline(0, color="grey", linestyle="-", linewidth=0.6, alpha=0.4)
        ax.fill_between(t, ci_lo, ci_hi, alpha=0.25, color="steelblue", label="95% CI (bootstrap)")
        ax.plot(t, mean_, marker="o", markersize=4, color="steelblue", linewidth=1.5, label="Mean")

        ax.set_title(RESPONSE_LABELS.get(var, var), fontsize=11)
        ax.set_xlabel("tau (days relative to event)")
        ax.set_xticks(list(range(-k, k + 1)))
        ax.legend(fontsize=8, loc="best")
        ax.grid(True, alpha=0.3)

    # Hide unused axes if fewer than 4 variables
    for ax in axes[len(response_vars):]:
        ax.set_visible(False)

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[INFO] Figure saved: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="T16 Event Study — on-chain event-linked response analysis")
    parser.add_argument(
        "--window", "-k",
        type=int,
        default=5,
        help="Half-width of event window in days (default: 5, i.e. tau=-5..+5). [DEFAULT — not yet confirmed with team]",
    )
    parser.add_argument(
        "--event-type",
        choices=["all", "large_transfer", "whale_inflow", "concentration"],
        default="all",
        help="Which event type(s) to run (default: all).",
    )
    parser.add_argument(
        "--bootstrap-n",
        type=int,
        default=1000,
        help="Number of bootstrap resamples for CI (default: 1000).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for bootstrap (default: 42).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    k = args.window
    n_boot = args.bootstrap_n
    seed = args.seed
    run_types = (
        ["large_transfer", "whale_inflow", "concentration"]
        if args.event_type == "all"
        else [args.event_type]
    )

    print("=" * 60)
    print("T16 Event Study")
    print("=" * 60)
    print(f"[INFO] Window k={k} (tau={-k}..{+k}), bootstrap_n={n_boot}, seed={seed}")
    print(
        "[NOTE] All event thresholds are DEFAULT assumptions — not yet confirmed with team:\n"
        f"       large_transfer: rolling-{LARGE_TRANSFER_LOOKBACK}d p{int(LARGE_TRANSFER_PERCENTILE*100)}\n"
        f"       whale_inflow:   pit_cex_netflow_z > {WHALE_INFLOW_Z_THRESHOLD}\n"
        f"       concentration:  rolling-{CONCENTRATION_LOOKBACK}d p{int(CONCENTRATION_PERCENTILE*100)}"
    )
    print("-" * 60)

    # --- Load data ---
    df14 = _load_t14()
    df11 = _load_t11()
    df = _build_combined(df14, df11)

    # Detect which response vars are actually available
    avail_vars = [v for v in RESPONSE_VARS if v in df.columns]
    missing_vars = [v for v in RESPONSE_VARS if v not in df.columns]
    if missing_vars:
        print(f"[WARN] Response variables not found, skipping: {missing_vars}")
    print(f"[INFO] Response variables: {avail_vars}")

    # --- Define event detectors ---
    detectors = {
        "large_transfer": detect_large_transfer_events,
        "whale_inflow": detect_whale_inflow_events,
        "concentration": detect_concentration_events,
    }

    all_results = []      # aggregated stats per event type
    all_event_lists = []  # raw event list

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _FIG_DIR.mkdir(parents=True, exist_ok=True)

    for event_type in run_types:
        print()
        print(f"--- Event type: {event_type} ---")
        detect_fn = detectors[event_type]
        event_mask = detect_fn(df)
        n_events = int(event_mask.sum())
        print(f"[INFO] Events detected: {n_events}")

        if n_events == 0:
            print(f"[WARN] No events found for '{event_type}'; skipping.")
            continue

        # Build event list
        event_dates = df.loc[event_mask, "date"].copy()
        ev_list = pd.DataFrame(
            {
                "event_type": event_type,
                "event_date": event_dates.values,
            }
        )
        # Attach signal value for reference
        signal_col = {
            "large_transfer": "large_transfer_count",
            "whale_inflow": "pit_cex_netflow_z",
            "concentration": "community_concentration_index",
        }.get(event_type)
        if signal_col and signal_col in df.columns:
            ev_list["signal_value"] = df.loc[event_mask, signal_col].values

        all_event_lists.append(ev_list)

        # Extract event windows
        windows_df = extract_event_windows(df, event_mask, avail_vars, k)

        # Compute stats
        stats_df = compute_event_study_stats(windows_df, avail_vars, k, n_boot, seed)
        stats_df.insert(0, "event_type", event_type)

        # Print summary
        print(f"\n{'tau':>6}  {'variable':<22}  {'mean':>10}  {'ci_lo':>10}  {'ci_hi':>10}  {'n_obs':>6}")
        print("-" * 70)
        for _, row in stats_df[stats_df["tau"].isin([-2, -1, 0, 1, 2])].iterrows():
            print(
                f"  {int(row['tau']):>3}  {row['variable']:<22}  "
                f"{row['mean']:>10.4f}  {row['ci_lower']:>10.4f}  {row['ci_upper']:>10.4f}  "
                f"{int(row['n_observations']):>6}"
            )

        all_results.append(stats_df)

        # Plot
        fig_path = _FIG_DIR / f"t16_{event_type}_response.png"
        plot_event_study(stats_df, event_type, n_events, avail_vars, fig_path, k)

    # --- Save outputs ---
    if not all_results:
        print("\n[WARN] No results to save — no events were detected across all types.")
        sys.exit(0)

    results_df = pd.concat(all_results, ignore_index=True)
    event_list_df = pd.concat(all_event_lists, ignore_index=True) if all_event_lists else pd.DataFrame()

    results_path = _OUT_DIR / "t16_event_study_results.parquet"
    event_list_path = _OUT_DIR / "t16_event_list.parquet"

    results_df.to_parquet(results_path, index=False)
    event_list_df.to_parquet(event_list_path, index=False)

    # Save summary JSON (human-readable stats for tau=0)
    summary = {}
    for event_type in run_types:
        sub = results_df[
            (results_df["event_type"] == event_type) & (results_df["tau"] == 0)
        ]
        summary[event_type] = {
            row["variable"]: {
                "tau0_mean": round(row["mean"], 6) if pd.notna(row["mean"]) else None,
                "tau0_median": round(row["median"], 6) if pd.notna(row["median"]) else None,
                "tau0_ci_lower": round(row["ci_lower"], 6) if pd.notna(row["ci_lower"]) else None,
                "tau0_ci_upper": round(row["ci_upper"], 6) if pd.notna(row["ci_upper"]) else None,
                "n_observations": int(row["n_observations"]) if pd.notna(row["n_observations"]) else None,
            }
            for _, row in sub.iterrows()
        }
        # Add event count
        ev_count = (
            event_list_df[event_list_df["event_type"] == event_type].shape[0]
            if not event_list_df.empty
            else 0
        )
        summary[event_type]["_n_events"] = ev_count

    summary_path = _OUT_DIR / "t16_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "t16_event_study": {
                    "window_k": k,
                    "bootstrap_n": n_boot,
                    "seed": seed,
                    "thresholds": {
                        "large_transfer": f"rolling-{LARGE_TRANSFER_LOOKBACK}d p{int(LARGE_TRANSFER_PERCENTILE*100)} [DEFAULT]",
                        "whale_inflow": f"pit_cex_netflow_z > {WHALE_INFLOW_Z_THRESHOLD} [DEFAULT]",
                        "concentration": f"rolling-{CONCENTRATION_LOOKBACK}d p{int(CONCENTRATION_PERCENTILE*100)} [DEFAULT]",
                    },
                    "note": "All thresholds are default assumptions; not yet confirmed with team.",
                    "causal_disclaimer": (
                        "Results describe event-linked associations only. "
                        "No causal inference is made or implied."
                    ),
                    "results_by_event_type": summary,
                }
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 60)
    print("Files created (NOT committed, NOT uploaded):")
    for p in [results_path, event_list_path, summary_path]:
        size = p.stat().st_size if p.exists() else 0
        print(f"  {p}  ({size:,} bytes)")
    for event_type in run_types:
        fig_p = _FIG_DIR / f"t16_{event_type}_response.png"
        if fig_p.exists():
            print(f"  {fig_p}  ({fig_p.stat().st_size:,} bytes)")
    print("=" * 60)
    print("T16 complete.")


if __name__ == "__main__":
    main()

