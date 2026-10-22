
"""
T13 - Read Network Statistics Results

Read 20 validated Parquet outputs from T13 and
display RQ1/RQ2 research results.

Dataset:
team-crypto/Market-data-crypto-project

This script DOES NOT recalculate network statistics.
"""

import argparse
from pathlib import Path

import pandas as pd


DATASET_ID = "team-crypto/Market-data-crypto-project"
DATA_FOLDER = "data/processed/t13"

EXPECTED_FILES = [
    "central_wallet_concentration_comparison.parquet",
    "central_wallet_concentration_daily.parquet",
    "central_wallet_concentration_summary.parquet",
    "centrality_distribution_daily.parquet",
    "cmsi2_daily_regimes.parquet",
    "cmsi2_robustness_results.parquet",
    "cmsi_daily_regimes.parquet",
    "cmsi_robustness_results.parquet",
    "network_descriptive_statistics.parquet",
    "network_normal_vs_stress.parquet",
    "rq1_network_hac_fdr_results.parquet",
    "rq1_network_weekly_comparison.parquet",
    "rq2_centrality_distribution_weekly.parquet",
    "rq2_concentration_hac_tests.parquet",
    "rq2_concentration_weekly_comparison.parquet",
    "rq2_concentration_weekly_summary.parquet",
    "rq2_hac_fdr_results.parquet",
    "rv_daily_regimes.parquet",
    "rv_threshold_sensitivity.parquet",
    "rv_weekly_regimes.parquet",
]


def load_results(local_dir=None):
    """Load 20 T13 Parquet files locally or from Hugging Face."""

    if local_dir:
        folder = Path(local_dir).expanduser().resolve()
    else:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError(
                "Install huggingface_hub: pip install huggingface_hub"
            ) from exc

        snapshot = snapshot_download(
            repo_id=DATASET_ID,
            repo_type="dataset",
            revision="main",
            allow_patterns=[
                f"{DATA_FOLDER}/{name}"
                for name in EXPECTED_FILES
            ],
        )

        folder = Path(snapshot) / DATA_FOLDER

    results = {}
    missing = []

    for filename in EXPECTED_FILES:
        path = folder / filename

        if not path.is_file():
            missing.append(filename)
            continue

        df = pd.read_parquet(path)

        if df.empty:
            raise ValueError(f"Empty T13 result: {filename}")

        results[filename] = df

    if missing:
        raise FileNotFoundError(
            "Missing T13 Parquet files:\n" + "\n".join(missing)
        )

    if len(results) != 20:
        raise RuntimeError("Expected exactly 20 T13 result tables")

    return results


def display_results(results):
    """Display key RQ1 and RQ2 results."""

    print("\n========== T13 RESULTS ==========")
    print(f"Loaded {len(results)} Parquet files successfully.")

    rv = results["rv_daily_regimes.parquet"]

    print("\nMARKET REGIMES")
    print(rv["regime"].value_counts().to_string())

    print("\nRV P90 (%)")
    print(round(rv["rv"].quantile(0.90) * 100, 4))

    print("\nRQ1 - NETWORK NORMAL VS STRESS")
    print(
        results["network_normal_vs_stress.parquet"]
        .round(4)
        .to_string(index=False)
    )

    print("\nRQ1 - HAC + BH-FDR")
    rq1 = results["rq1_network_hac_fdr_results.parquet"]
    print(rq1.round(5).to_string(index=False))
    print(
        "RQ1 BH-FDR significant:",
        int(rq1["significant_bh_5pct"].sum()),
        "/",
        len(rq1),
    )

    print("\nRQ2 - CENTRAL WALLET CONCENTRATION")
    print(
        results["central_wallet_concentration_comparison.parquet"]
        .round(4)
        .to_string(index=False)
    )

    print("\nRQ2 - HAC + BH-FDR")
    rq2 = results["rq2_hac_fdr_results.parquet"]
    print(rq2.round(5).to_string(index=False))
    print(
        "RQ2 BH-FDR significant:",
        int(rq2["significant_bh_5pct"].sum()),
        "/",
        len(rq2),
    )

    print("\nT13 RESULTS LOADED SUCCESSFULLY")


def main():
    parser = argparse.ArgumentParser(
        description="Read 20 T13 Parquet research results"
    )

    parser.add_argument(
        "--local-dir",
        default=None,
        help="Optional local directory containing T13 Parquet files",
    )

    args = parser.parse_args()

    results = load_results(args.local_dir)
    display_results(results)


if __name__ == "__main__":
    main()
