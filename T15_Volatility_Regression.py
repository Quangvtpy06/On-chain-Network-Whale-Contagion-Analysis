"""T15: Volatility regression – Vol_{t+h} ~ WhaleFlow_t + X_t across multiple horizons.

Estimates the predictive association between on-chain whale flows and future realised
volatility using OLS with HAC (Newey-West) standard errors.  The regression is purely
reduced-form; coefficients capture lead-lag relationships, NOT causal effects.

Run from the project root:

    python T15_Volatility_Regression.py [--no-cache]

Depends only on T14 output (t14_features_daily.parquet).  Never reads T12 or T13 directly.

Output files (written to the T15 output directory, NOT uploaded):
    t15_volatility_regression_results.parquet  – full coefficient table, all horizons/models
    t15_volatility_regression_summary.csv      – human-readable summary table
    t15_regression_report.md                   – markdown report with interpretation notes
    t15_summary.json                           – machine-readable metadata / R² per horizon

HAC maxlags choice
------------------
At horizon h, the OLS residuals have an MA(h-1) structure under the null of no
predictability (Hodrick 1992).  We use

    maxlags = max(h, int(np.ceil(4.0 * (n / 100) ** (2 / 9))))

This satisfies two desiderata: (a) covers at least h lags to accommodate the
moving-average error structure, and (b) uses the Andrews (1991) / Newey-West
data-driven bandwidth rule as a floor.  maxlags is capped at n // 5 to avoid
over-smoothing with small samples.
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from src.graph_config import ROOT

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SETTINGS_PATH = ROOT / "config/t14.yaml"

# The parquet lives inside the market_data sub-repository.  If the config path
# (data/processed/t14) resolves to a directory that exists, use it; otherwise
# fall back to the known market_data submodule location.
_CONFIG_PARQUET = ROOT / "data/processed/t14/t14_features_daily.parquet"
_FALLBACK_PARQUET = ROOT / "data/market_data/data/processed/t14/t14_features_daily.parquet"

T15_OUTPUT_DIR = ROOT / "data/market_data/data/processed/t15"

FEATURES_FILE = "t14_features_daily.parquet"
RESULTS_FILE = "t15_volatility_regression_results.parquet"
SUMMARY_CSV = "t15_volatility_regression_summary.csv"
REPORT_MD = "t15_regression_report.md"
META_JSON = "t15_summary.json"

# ---------------------------------------------------------------------------
# Regression specification
# ---------------------------------------------------------------------------

# Horizons confirmed from t14.yaml and t14_summary.json.
HORIZONS = [1, 3, 7]

# Primary PIT predictor (point-in-time evidence; preferred for forecasting).
PIT_WHALE = "whaleflow_pit_z"

# Retrospective predictor (uses current T07 labels – NOT point-in-time evidence;
# included only for robustness / comparison.  Never treat as the main result).
RETRO_WHALE = "whaleflow_z"

# HAR-style volatility controls (all known at D+1 00:00 UTC).
# log_rv  = log RV of day D  (most recent completed day)
# log_rv_week  = 7-day rolling average log RV
# log_rv_month = 30-day rolling average log RV
CONTROLS = [
    "ret_1d",           # daily return, controls for momentum / leverage effect
    "log_volume_usdt",  # log trading volume, proxy for liquidity
    "log_rv",           # HAR lag-1 component
    "log_rv_week",      # HAR lag-week component
    "log_rv_month",     # HAR lag-month component
]

# Optional extended controls (used if all are present in the data).
EXTENDED_CONTROLS = [
    "log_trade_count",
    "taker_imbalance",
    "spread_cs_proxy",
    "parkinson_var",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _locate_parquet() -> Path:
    """Return the path to t14_features_daily.parquet (config path or fallback)."""
    if _CONFIG_PARQUET.exists():
        return _CONFIG_PARQUET
    if _FALLBACK_PARQUET.exists():
        return _FALLBACK_PARQUET
    raise FileNotFoundError(
        f"Cannot find {FEATURES_FILE}.\n"
        f"  Tried: {_CONFIG_PARQUET}\n"
        f"  Tried: {_FALLBACK_PARQUET}\n"
        "Please run T14 first or check the output_dir in config/t14.yaml."
    )


def _hac_maxlags(n: int, h: int) -> int:
    """HAC bandwidth: max(h, Andrews-NW rule), capped at n//5.

    Covers at least h lags for the MA(h-1) forecast-error structure AND applies
    the standard Newey-West data-driven bandwidth as a floor.
    """
    nw_rule = int(np.ceil(4.0 * (n / 100) ** (2 / 9)))
    lags = max(h, nw_rule)
    return min(lags, n // 5)


def _run_ols_hac(y: pd.Series, X: pd.DataFrame, h: int) -> dict:
    """Fit OLS with Newey-West HAC SE and return a results dict."""
    data = pd.concat([y, X], axis=1).dropna()
    n = len(data)
    if n < 30:
        return None  # too few observations

    y_ = data.iloc[:, 0]
    X_ = sm.add_constant(data.iloc[:, 1:], has_constant="add")

    maxlags = _hac_maxlags(n, h)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = sm.OLS(y_, X_).fit(
            cov_type="HAC",
            cov_kwds={"maxlags": maxlags, "use_correction": True},
        )

    rows = []
    for var in model.params.index:
        rows.append({
            "variable": var,
            "coef": model.params[var],
            "hac_se": model.bse[var],
            "t_stat": model.tvalues[var],
            "p_value": model.pvalues[var],
        })

    return {
        "n_obs": n,
        "r2": model.rsquared,
        "r2_adj": model.rsquared_adj,
        "maxlags_hac": maxlags,
        "coefs": rows,
    }


def _build_results_table(horizon: int, model_name: str, whale_col: str,
                         controls: list, res: dict) -> pd.DataFrame:
    """Convert a results dict into a tidy DataFrame row per coefficient."""
    if res is None:
        return pd.DataFrame()

    records = []
    for row in res["coefs"]:
        records.append({
            "horizon_h": horizon,
            "model": model_name,
            "whale_predictor": whale_col,
            "variable": row["variable"],
            "coef": row["coef"],
            "hac_se": row["hac_se"],
            "t_stat": row["t_stat"],
            "p_value": row["p_value"],
            "significant_5pct": row["p_value"] < 0.05,
            "n_obs": res["n_obs"],
            "r2": res["r2"],
            "r2_adj": res["r2_adj"],
            "maxlags_hac": res["maxlags_hac"],
        })
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Main regression loop
# ---------------------------------------------------------------------------

def run_regressions(df: pd.DataFrame, extended: bool = True) -> tuple[pd.DataFrame, dict]:
    """Run all regressions for all horizons and both whale predictor variants.

    Returns
    -------
    results_df : tidy DataFrame with one row per (horizon, model, variable)
    meta       : dict with summary statistics per horizon
    """
    # Determine which extended controls are actually in the data.
    if extended:
        ext = [c for c in EXTENDED_CONTROLS if c in df.columns]
    else:
        ext = []

    controls = [c for c in CONTROLS if c in df.columns]
    all_frames = []
    meta = {"horizons": HORIZONS, "models": {}}

    for h in HORIZONS:
        target_col = f"target_log_rv_h{h}"
        if target_col not in df.columns:
            print(f"  [WARNING] Target column {target_col} missing – skipping h={h}")
            continue

        y = df[target_col]
        horizon_meta = {}

        # ------------------------------------------------------------------ #
        # Model 1 (MAIN): PIT WhaleFlow + controls                           #
        # ------------------------------------------------------------------ #
        pit_features = [PIT_WHALE] + controls + ext
        pit_features = [c for c in pit_features if c in df.columns]

        res_pit = _run_ols_hac(y, df[pit_features], h)
        frame_pit = _build_results_table(h, "pit_whaleflow", PIT_WHALE,
                                         pit_features, res_pit)
        all_frames.append(frame_pit)

        if res_pit:
            horizon_meta["pit_whaleflow"] = {
                "r2": round(res_pit["r2"], 4),
                "r2_adj": round(res_pit["r2_adj"], 4),
                "n_obs": res_pit["n_obs"],
                "maxlags_hac": res_pit["maxlags_hac"],
            }
            # Check significance of whale predictor
            whale_row = next(
                (r for r in res_pit["coefs"] if r["variable"] == PIT_WHALE), None
            )
            if whale_row:
                horizon_meta["pit_whaleflow"]["whale_coef"] = round(whale_row["coef"], 4)
                horizon_meta["pit_whaleflow"]["whale_hac_se"] = round(whale_row["hac_se"], 4)
                horizon_meta["pit_whaleflow"]["whale_t_stat"] = round(whale_row["t_stat"], 3)
                horizon_meta["pit_whaleflow"]["whale_p"] = round(whale_row["p_value"], 4)
                horizon_meta["pit_whaleflow"]["whale_sig5"] = whale_row["p_value"] < 0.05

        # ------------------------------------------------------------------ #
        # Model 2 (ROBUSTNESS ONLY – retrospective, not point-in-time):      #
        # Replaces whaleflow_pit_z with whaleflow_z for comparison.          #
        # Do NOT interpret this as the main forecasting result.              #
        # ------------------------------------------------------------------ #
        retro_features = [RETRO_WHALE] + controls + ext
        retro_features = [c for c in retro_features if c in df.columns]

        res_retro = _run_ols_hac(y, df[retro_features], h)
        frame_retro = _build_results_table(h, "retro_whaleflow_comparison",
                                            RETRO_WHALE, retro_features, res_retro)
        # Label retrospective rows clearly so they are never confused with main results.
        frame_retro["model"] = "retro_whaleflow_ROBUSTNESS_NOT_MAIN"
        all_frames.append(frame_retro)

        if res_retro:
            retro_whale_row = next(
                (r for r in res_retro["coefs"] if r["variable"] == RETRO_WHALE), None
            )
            horizon_meta["retro_whaleflow_robustness"] = {
                "r2": round(res_retro["r2"], 4),
                "r2_adj": round(res_retro["r2_adj"], 4),
                "n_obs": res_retro["n_obs"],
                "maxlags_hac": res_retro["maxlags_hac"],
                "whale_coef": round(retro_whale_row["coef"], 4) if retro_whale_row else None,
                "whale_hac_se": round(retro_whale_row["hac_se"], 4) if retro_whale_row else None,
                "whale_t_stat": round(retro_whale_row["t_stat"], 3) if retro_whale_row else None,
                "whale_p": round(retro_whale_row["p_value"], 4) if retro_whale_row else None,
                "note": "Retrospective: uses current T07 labels, NOT point-in-time evidence.",
            }

        # ------------------------------------------------------------------ #
        # Model 3 (BASELINE): HAR-RV only, no whale predictor                #
        # ------------------------------------------------------------------ #
        har_features = controls
        har_features = [c for c in har_features if c in df.columns]

        res_har = _run_ols_hac(y, df[har_features], h)
        frame_har = _build_results_table(h, "har_baseline", "(none)",
                                         har_features, res_har)
        all_frames.append(frame_har)

        if res_har:
            horizon_meta["har_baseline"] = {
                "r2": round(res_har["r2"], 4),
                "r2_adj": round(res_har["r2_adj"], 4),
                "n_obs": res_har["n_obs"],
            }

        meta["models"][f"h{h}"] = horizon_meta
        print(f"  h={h}: PIT R²={horizon_meta.get('pit_whaleflow', {}).get('r2', 'N/A'):.4f}  "
              f"HAR-baseline R²={horizon_meta.get('har_baseline', {}).get('r2', 'N/A'):.4f}  "
              f"n={horizon_meta.get('pit_whaleflow', {}).get('n_obs', '?')}")

    results_df = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()
    return results_df, meta


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def build_summary_table(results_df: pd.DataFrame) -> pd.DataFrame:
    """Build a concise summary: R², whale coefficient, SE, p-value per horizon."""
    rows = []
    pit_main = results_df[results_df.model == "pit_whaleflow"]

    for h in HORIZONS:
        sub = pit_main[pit_main.horizon_h == h]
        if sub.empty:
            continue
        # Metadata from any row of this horizon-model
        meta_row = sub.iloc[0]
        # Whale predictor row
        whale = sub[sub.variable == PIT_WHALE]
        if whale.empty:
            continue
        w = whale.iloc[0]
        rows.append({
            "horizon_h": h,
            "model": "pit_whaleflow (MAIN)",
            "n_obs": int(meta_row.n_obs),
            "r2": round(meta_row.r2, 4),
            "r2_adj": round(meta_row.r2_adj, 4),
            "whale_coef": round(w.coef, 4),
            "whale_hac_se": round(w.hac_se, 4),
            "whale_t_stat": round(w.t_stat, 3),
            "whale_p_value": round(w.p_value, 4),
            "significant_5pct": w.p_value < 0.05,
            "maxlags_hac": int(meta_row.maxlags_hac),
        })

    # Add HAR baseline for comparison
    har = results_df[results_df.model == "har_baseline"]
    for h in HORIZONS:
        sub = har[har.horizon_h == h]
        if sub.empty:
            continue
        meta_row = sub.iloc[0]
        rows.append({
            "horizon_h": h,
            "model": "har_baseline",
            "n_obs": int(meta_row.n_obs),
            "r2": round(meta_row.r2, 4),
            "r2_adj": round(meta_row.r2_adj, 4),
            "whale_coef": None,
            "whale_hac_se": None,
            "whale_t_stat": None,
            "whale_p_value": None,
            "significant_5pct": None,
            "maxlags_hac": int(meta_row.maxlags_hac),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def build_report(results_df: pd.DataFrame, summary_df: pd.DataFrame,
                 meta: dict) -> str:
    """Generate a Markdown regression report."""
    lines = [
        "# T15 Volatility Regression Report",
        "",
        "**Task:** Estimate the predictive association between on-chain whale flows",
        "and future ETH realised volatility across multiple forecast horizons.",
        "",
        "> **Interpretation note:** All coefficients capture *predictive associations*",
        "> (lead-lag relationships). They do NOT imply causal effects.",
        "",
        "## 1. Specification",
        "",
        "```",
        "Vol_{t+h} ~ const + whaleflow_pit_z_t + ret_1d_t + log_volume_usdt_t",
        "           + log_rv_t + log_rv_week_t + log_rv_month_t + [extended controls]",
        "```",
        "",
        "- **Vol_{t+h}** = `target_log_rv_h{h}` = log(RV) of UTC day D+h,",
        "  where RV = sum of squared 1-minute log returns (1440 bars per day).",
        "- **whaleflow_pit_z** = point-in-time z-scored WhaleFlow; known at D+1 00:00 UTC.",
        "- Standard errors: HAC Newey-West,",
        "  `maxlags = max(h, ceil(4 * (n/100)^(2/9)))`, capped at n//5.",
        "- Retrospective model (`whaleflow_z`) is labelled **ROBUSTNESS_NOT_MAIN** and",
        "  uses current T07 labels (not point-in-time evidence).",
        "",
        "## 2. Main Results – PIT WhaleFlow",
        "",
    ]

    pit = summary_df[summary_df.model == "pit_whaleflow (MAIN)"]
    if not pit.empty:
        lines.append("| h | n | R² | R²_adj | whale coef | HAC SE | t-stat | p-value | sig (5%) |")
        lines.append("|---|---|----|--------|-----------|--------|--------|---------|---------|")
        for _, row in pit.iterrows():
            sig = "✓" if row.significant_5pct else ""
            lines.append(
                f"| {int(row.horizon_h)} | {int(row.n_obs)} | {row.r2:.4f} | {row.r2_adj:.4f} "
                f"| {row.whale_coef:.4f} | {row.whale_hac_se:.4f} "
                f"| {row.whale_t_stat:.3f} | {row.whale_p_value:.4f} | {sig} |"
            )
        lines.append("")

    # Add Retrospective comparison table
    retro = results_df[results_df.model == "retro_whaleflow_ROBUSTNESS_NOT_MAIN"]
    if not retro.empty:
        lines += [
            "## 3. Retrospective Robustness (Comparison Only – NOT Main Result)",
            "",
            "> **Disclaimer:** Uses current T07 labels with future information leakage (retrospective).",
            "> Included purely for methodological comparison against the PIT branch.",
            "",
            "| h | n | R² | R²_adj | whale coef (retro) | HAC SE | t-stat | p-value | sig (5%) |",
            "|---|---|----|--------|-------------------|--------|--------|---------|---------|",
        ]
        for h in HORIZONS:
            sub = retro[(retro.horizon_h == h) & (retro.variable == RETRO_WHALE)]
            if not sub.empty:
                r = sub.iloc[0]
                sig = "✓" if r.significant_5pct else ""
                lines.append(
                    f"| {int(r.horizon_h)} | {int(r.n_obs)} | {r.r2:.4f} | {r.r2_adj:.4f} "
                    f"| {r.coef:.4f} | {r.hac_se:.4f} "
                    f"| {r.t_stat:.3f} | {r.p_value:.4f} | {sig} |"
                )
        lines.append("")

    lines += [
        "## 4. HAR Baseline (no whale predictor)",
        "",
    ]
    har = summary_df[summary_df.model == "har_baseline"]
    if not har.empty:
        lines.append("| h | n | R² | R²_adj |")
        lines.append("|---|---|----|----|")
        for _, row in har.iterrows():
            lines.append(f"| {int(row.horizon_h)} | {int(row.n_obs)} | {row.r2:.4f} | {row.r2_adj:.4f} |")
        lines.append("")

    lines += [
        "## 5. Caveats",
        "",
        "- WhaleFlow PIT uses v2 activity cohort membership (not a new filtered cohort).",
        "- The regression sample is limited by whale-flow availability (~595 days).",
        "- Estimating regressions across multiple horizons (h=1, 3, 7) constitutes multiple hypothesis testing; significance levels should be interpreted with caution against false positive discovery.",
        "- Retrospective branch results must not be used as the primary forecasting evidence.",
        "- No causal interpretation; coefficients reflect predictive associations only.",
        "",
        "## 6. Output Files",
        "",
        f"- `t15_volatility_regression_results.parquet` — full coefficient table",
        f"- `t15_volatility_regression_summary.csv` — concise summary",
        f"- `t15_regression_report.md` — this report",
        f"- `t15_summary.json` — machine-readable metadata",
        "",
        "---",
        "*Generated by T15_Volatility_Regression.py. Not uploaded to Hugging Face.*",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="T15 volatility regression.")
    parser.add_argument("--no-extended", action="store_true",
                        help="Skip extended controls (log_trade_count etc.) for a leaner spec.")
    args = parser.parse_args()

    print("=" * 60)
    print("T15 Volatility Regression")
    print("=" * 60)

    # ---- Locate input ----
    parquet_path = _locate_parquet()
    print(f"\n[INFO] Reading features from: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    print(f"[INFO] Loaded {len(df)} rows, {len(df.columns)} columns.")
    print(f"[INFO] Date range: {df.index.min()} to {df.index.max()}")

    # ---- Validate required columns ----
    missing_targets = [f"target_log_rv_h{h}" for h in HORIZONS
                       if f"target_log_rv_h{h}" not in df.columns]
    if missing_targets:
        raise ValueError(f"Missing target columns in parquet: {missing_targets}")

    missing_pit = PIT_WHALE not in df.columns
    missing_retro = RETRO_WHALE not in df.columns
    if missing_pit:
        raise ValueError(f"Column '{PIT_WHALE}' not found in parquet.")
    if missing_retro:
        print(f"[WARNING] '{RETRO_WHALE}' not found – retrospective model will be skipped.")

    missing_controls = [c for c in CONTROLS if c not in df.columns]
    if missing_controls:
        print(f"[WARNING] Some controls missing: {missing_controls}")

    print(f"\n[INFO] Running regressions: horizons={HORIZONS}, "
          f"extended_controls={not args.no_extended}")
    print("-" * 60)

    # ---- Run regressions ----
    results_df, meta = run_regressions(df, extended=not args.no_extended)

    # ---- Build summary ----
    summary_df = build_summary_table(results_df)

    # ---- Print significance summary ----
    print("\n" + "=" * 60)
    print("SIGNIFICANCE SUMMARY (whaleflow_pit_z, α = 0.05)")
    print("=" * 60)
    pit_rows = summary_df[summary_df.model == "pit_whaleflow (MAIN)"]
    if pit_rows.empty:
        print("  No PIT results available.")
    else:
        for _, row in pit_rows.iterrows():
            sig_str = "SIGNIFICANT ✓" if row.significant_5pct else "not significant"
            print(f"  h={int(row.horizon_h):2d}: coef={row.whale_coef:+.4f}  "
                  f"p={row.whale_p_value:.4f}  {sig_str}")

    # ---- Save outputs ----
    T15_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Parquet (full coefficient table)
    results_path = T15_OUTPUT_DIR / RESULTS_FILE
    results_df.to_parquet(results_path, index=False)
    print(f"\n[INFO] Saved: {results_path}")

    # CSV summary
    csv_path = T15_OUTPUT_DIR / SUMMARY_CSV
    summary_df.to_csv(csv_path, index=False)
    print(f"[INFO] Saved: {csv_path}")

    # Markdown report
    report_text = build_report(results_df, summary_df, meta)
    report_path = T15_OUTPUT_DIR / REPORT_MD
    report_path.write_text(report_text, encoding="utf-8")
    print(f"[INFO] Saved: {report_path}")

    # JSON metadata
    meta_out = {
        "protocol_id": "t15_volatility_regression_v1",
        "horizons": HORIZONS,
        "pit_predictor": PIT_WHALE,
        "retro_predictor_robustness_only": RETRO_WHALE,
        "controls": CONTROLS,
        "hac_formula": "maxlags = max(h, ceil(4*(n/100)^(2/9))), capped at n//5",
        "models": meta["models"],
        "output_files": [RESULTS_FILE, SUMMARY_CSV, REPORT_MD, META_JSON],
        "note": "Coefficients reflect predictive associations (lead-lag), NOT causal effects.",
        "upload_ready": False,
    }
    meta_path = T15_OUTPUT_DIR / META_JSON
    meta_path.write_text(json.dumps(meta_out, indent=2, default=str), encoding="utf-8")
    print(f"[INFO] Saved: {meta_path}")

    print("\n" + "=" * 60)
    print("Files created (NOT committed, NOT uploaded):")
    for f in [results_path, csv_path, report_path, meta_path]:
        print(f"  {f}")
    print("=" * 60)
    print("T15 complete.")


if __name__ == "__main__":
    main()

