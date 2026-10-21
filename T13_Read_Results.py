
"""
T13 - Read Network Statistics Results

Read the 20 CSV outputs from T13 and display RQ1/RQ2 results.

Data repository:
team-crypto/Market-data-crypto-project

This script DOES NOT recalculate network statistics.
"""

import argparse
from pathlib import Path

import pandas as pd


DATASET_ID = "team-crypto/Market-data-crypto-project"
DATA_FOLDER = "data/processed/t13"

EXPECTED_FILES = [
    "central_wallet_concentration_comparison.csv",
    "central_wallet_concentration_daily.csv",
    "central_wallet_concentration_summary.csv",
    "centrality_distribution_daily.csv",
    "cmsi2_daily_regimes.csv",
    "cmsi2_robustness_results.csv",
    "cmsi_daily_regimes.csv",
    "cmsi_robustness_results.csv",
    "network_descriptive_statistics.csv",
    "network_normal_vs_stress.csv",
    "rq1_network_hac_fdr_results.csv",
    "rq1_network_weekly_comparison.csv",
    "rq2_centrality_distribution_weekly.csv",
    "rq2_concentration_hac_tests.csv",
    "rq2_concentration_weekly_comparison.csv",
    "rq2_concentration_weekly_summary.csv",
    "rq2_hac_fdr_results.csv",
    "rv_daily_regimes.csv",
    "rv_threshold_sensitivity.csv",
    "rv_weekly_regimes.csv",
]


def load_results(local_dir=None):
    """Read T13 CSVs from local folder or Hugging Face."""

    if local_dir:
        folder = Path(local_dir).expanduser()
    else:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError(
                "Install huggingface_hub: pip install huggingface_hub"
            ) from exc

        folder = Path(
            snapshot_download(
                repo_id=DATASET_ID,
                repo_type="dataset",
                allow_patterns=f"{DATA_FOLDER}/*.csv",
            )
        ) / DATA_FOLDER

    results = {}
    missing = []

    for filename in EXPECTED_FILES:
        path = folder / filename

        if path.is_file():
            results[filename] = pd.read_csv(path)
        else:
            missing.append(filename)

    if missing:
        raise FileNotFoundError(
            "Missing T13 CSV files:\n" + "\n".join(missing)
        )

    return results


def display_results(results):
    print("\n========== T13 RESULTS ==========")
    print(f"Loaded {len(results)} CSV files successfully.")

    rv = results["rv_daily_regimes.csv"]
    print("\nMARKET REGIMES")
    print(rv["regime"].value_counts().to_string())

    print("\nRQ1 - NETWORK NORMAL VS STRESS")
    print(
        results["network_normal_vs_stress.csv"]
        .round(4)
        .to_string(index=False)
    )

    print("\nRQ1 - HAC + BH-FDR")
    print(
        results["rq1_network_hac_fdr_results.csv"]
        .round(5)
        .to_string(index=False)
    )

    print("\nRQ2 - CENTRAL WALLET CONCENTRATION")
    print(
        results["central_wallet_concentration_comparison.csv"]
        .round(4)
        .to_string(index=False)
    )

    print("\nRQ2 - HAC + BH-FDR")
    print(
        results["rq2_hac_fdr_results.csv"]
        .round(5)
        .to_string(index=False)
    )

    print("\nT13 RESULTS LOADED SUCCESSFULLY")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--local-dir",
        default=None,
        help="Optional local directory containing T13 CSV files",
    )

    args = parser.parse_args()

    results = load_results(args.local_dir)
    display_results(results)


if __name__ == "__main__":
    main()
