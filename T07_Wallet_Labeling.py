"""T07 Wallet Labeling for Ethereum USDT Transfer events.

Dependencies: pandas, pyarrow, numpy
Run from project root: python T07_Wallet_Labeling.py
Optional verified labels: data/external/t07_verified_labels.csv
Columns: address, entity_name, entity_type, source_url, confidence

No identity attribution is inferred from transaction activity. Activity labels
are descriptive of the input sample, not wallet balances or true ownership.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ADDRESS_RE = re.compile(r"^0x[a-f0-9]{40}$")
REQUIRED = {"from_address", "to_address", "amount", "transaction_hash", "log_index", "block_timestamp"}
ZERO = "0x" + "0" * 40
ENTITY_TYPES = {"CEX", "DEX", "DeFi", "Bridge", "Custodian", "Contract", "Protocol", "Issuer", "Other", "Unknown"}


def load_transfers(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Missing input: {path}")
    df = pd.read_parquet(path)
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"Input missing columns: {sorted(missing)}")
    for col in ("from_address", "to_address", "transaction_hash"):
        df[col] = df[col].astype("string").str.strip().str.lower()
    for col in ("from_address", "to_address"):
        bad = ~df[col].str.fullmatch(ADDRESS_RE.pattern).fillna(False)
        if bad.any():
            raise ValueError(f"Invalid {col} in {int(bad.sum())} row(s)")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    if df["amount"].isna().any() or (~np.isfinite(df["amount"])).any() or (df["amount"] < 0).any():
        raise ValueError("amount contains missing, non-finite or negative values")
    df["block_timestamp"] = pd.to_datetime(df["block_timestamp"], utc=True, errors="coerce")
    if df["block_timestamp"].isna().any():
        raise ValueError("Invalid block_timestamp")
    # A transfer event is unique by (chain, transaction hash, log index).
    duplicates = df.duplicated(["transaction_hash", "log_index"], keep=False)
    if duplicates.any():
        raise ValueError(f"Duplicate transfer events: {int(duplicates.sum())} rows")
    return df


def activity_table(df: pd.DataFrame, whale_threshold: float) -> pd.DataFrame:
    outgoing = (df.groupby("from_address", as_index=False)
                  .agg(outgoing_transfers=("amount", "size"),
                       outgoing_usdt=("amount", "sum"),
                       unique_recipients=("to_address", "nunique"))
                  .rename(columns={"from_address": "address"}))
    incoming = (df.groupby("to_address", as_index=False)
                  .agg(incoming_transfers=("amount", "size"),
                       incoming_usdt=("amount", "sum"),
                       unique_senders=("from_address", "nunique"))
                  .rename(columns={"to_address": "address"}))
    wallets = outgoing.merge(incoming, on="address", how="outer")
    metrics = ("outgoing_transfers", "outgoing_usdt", "unique_recipients",
               "incoming_transfers", "incoming_usdt", "unique_senders")
    wallets[list(metrics)] = wallets[list(metrics)].fillna(0)
    counts = ("outgoing_transfers", "unique_recipients", "incoming_transfers", "unique_senders")
    wallets[list(counts)] = wallets[list(counts)].astype("int64")
    wallets["total_transfers_involvement"] = wallets["outgoing_transfers"] + wallets["incoming_transfers"]
    wallets["gross_flow_usdt"] = wallets["outgoing_usdt"] + wallets["incoming_usdt"]
    wallets["net_inflow_usdt"] = wallets["incoming_usdt"] - wallets["outgoing_usdt"]
    whales = df.loc[df["amount"] >= whale_threshold]
    whale_out = whales.groupby("from_address").size().rename("whale_outgoing_events")
    whale_in = whales.groupby("to_address").size().rename("whale_incoming_events")
    wallets = wallets.join(whale_out, on="address").join(whale_in, on="address")
    wallets[["whale_outgoing_events", "whale_incoming_events"]] = (
        wallets[["whale_outgoing_events", "whale_incoming_events"]].fillna(0).astype("int64")
    )
    wallets["whale_activity"] = np.where(
        wallets["whale_outgoing_events"] + wallets["whale_incoming_events"] > 0,
        "large_transfer_participant", "no_large_transfer_observed"
    )
    wallets["is_zero_address"] = wallets["address"].eq(ZERO)
    # Distinguish raw event count (each event counts once) from address involvements.
    wallets = wallets.sort_values(["gross_flow_usdt", "address"], ascending=[False, True]).reset_index(drop=True)
    return wallets


def apply_verified_labels(wallets: pd.DataFrame, labels_path: Path) -> tuple[pd.DataFrame, dict]:
    for col, default in (("entity_name", "Unknown"), ("entity_type", "Unknown"),
                         ("label_source_url", ""), ("label_confidence", "Unverified")):
        wallets[col] = default
    stats = {"label_file_present": labels_path.is_file(), "verified_matches": 0}
    if not labels_path.is_file():
        return wallets, stats
    labels = (pd.read_parquet(labels_path).astype('string') if labels_path.suffix == '.parquet'
              else pd.read_csv(labels_path, dtype="string")).fillna("")
    required = {"address", "entity_name", "entity_type", "source_url", "confidence"}
    if not required.issubset(labels.columns):
        raise ValueError(f"Verified labels CSV requires: {sorted(required)}")
    labels["address"] = labels["address"].str.strip().str.lower()
    labels["entity_type"] = labels["entity_type"].str.strip()
    labels["confidence"] = labels["confidence"].str.strip()
    if (~labels["address"].str.fullmatch(ADDRESS_RE.pattern)).any():
        raise ValueError("Verified labels have invalid Ethereum address")
    if labels["address"].duplicated().any():
        raise ValueError("Verified labels have duplicate address")
    invalid_type = ~labels["entity_type"].isin(ENTITY_TYPES)
    if invalid_type.any():
        raise ValueError(f"Unknown entity_type: {labels.loc[invalid_type, 'entity_type'].unique().tolist()}")
    # All attributed labels require a named identity and evidence URL.
    has_identity = labels["entity_type"].ne("Unknown")
    bad = has_identity & (labels["entity_name"].str.strip().eq("") | ~labels["source_url"].str.match(r"^https?://"))
    if bad.any():
        raise ValueError("Every non-Unknown label requires entity_name and http(s) source_url")
    mapped = labels.set_index("address")
    matching = wallets["address"].isin(mapped.index)
    for output_col, source_col in (("entity_name", "entity_name"), ("entity_type", "entity_type"),
                                   ("label_source_url", "source_url"), ("label_confidence", "confidence")):
        wallets.loc[matching, output_col] = wallets.loc[matching, "address"].map(mapped[source_col]).to_numpy()
    stats["verified_matches"] = int((matching & wallets["entity_type"].ne("Unknown")).sum())
    return wallets, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="T07: sample-based Ethereum USDT wallet profiling and evidence-backed labeling")
    parser.add_argument("--input", type=Path, default=Path("data/interim/usdt_whale_transfers_interim.parquet"))
    parser.add_argument("--labels", type=Path, default=Path("data/external/t07_verified_labels.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/t07"))
    parser.add_argument("--whale-threshold", type=float, default=1_000_000,
                        help="USDT per Transfer event; behavioral label only (default 1 million)")
    args = parser.parse_args()
    if not np.isfinite(args.whale_threshold) or args.whale_threshold <= 0:
        parser.error("--whale-threshold must be positive and finite")
    df = load_transfers(args.input)
    wallets = activity_table(df, args.whale_threshold)
    wallets, label_stats = apply_verified_labels(wallets, args.labels)
    args.output.mkdir(parents=True, exist_ok=True)
    pq_path = args.output / "wallet_labels.parquet"
    wallets.to_parquet(pq_path, index=False)
    # Empty editable evidence template: no unsupported identity claims.
    template_path = args.output / "verified_labels_template.parquet"
    if not template_path.exists():
        pd.DataFrame(columns=["address", "entity_name", "entity_type", "source_url", "confidence"]).to_parquet(template_path, index=False)
    summary = {
        "input_file": str(args.input),
        "input_transfer_events": int(len(df)),
        "unique_wallet_addresses": int(len(wallets)),
        "unique_directed_pairs": int(df.groupby(["from_address", "to_address"]).ngroups),
        "duplicate_events": 0,
        "start_utc": df["block_timestamp"].min().isoformat() if len(df) else None,
        "end_utc": df["block_timestamp"].max().isoformat() if len(df) else None,
        "whale_transfer_threshold_usdt": args.whale_threshold,
        "whale_events_in_sample": int((df["amount"] >= args.whale_threshold).sum()),
        "labeled_addresses": int((wallets["entity_type"] != "Unknown").sum()),
        "unverified_addresses": int((wallets["entity_type"] == "Unknown").sum()),
        **label_stats,
        "limitations": [
            "Input is a sampled/filtered transfer dataset, not a complete ledger.",
            "Activity labels do not establish identity, current balance, or whale ownership.",
            "A transfer is an ERC-20 event and need not represent an independent economic movement.",
        ],
    }
    summary_path = args.output / "t07_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("===== T07 COMPLETE =====")
    for k, v in summary.items():
        if k != "limitations":
            print(f"{k}: {v}")
    print("Outputs:", pq_path, summary_path, template_path, sep="\n  ")


if __name__ == "__main__":
    main()
