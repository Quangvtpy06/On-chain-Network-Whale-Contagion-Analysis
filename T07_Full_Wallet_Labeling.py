"""
T07 Full Wallet Labeling
========================
Aggregates wallet activity across all whale transfers and assigns
verified entity labels (CEX, DEX, DeFi, Bridge, Contract, etc.).

Integrated with central data_loader for automatic Hugging Face
selective download and local caching.
"""

from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse
import json

import pandas as pd
import pyarrow.parquet as pq

from src.data_loader import get_data_path

ROOT = Path(__file__).resolve().parent

# Tự động tải từ Hugging Face Hub (hoặc dùng local cache)
INPUT = get_data_path("data/interim/usdt_whale_transfers_interim.parquet")
LABELS = get_data_path("data/external/t07_verified_labels.csv")
OUTPUT = ROOT / "data/processed/t07"

ALLOWED_TYPES = {
    "CEX", "DEX", "DeFi", "Bridge", "Custodian",
    "Contract", "Protocol", "Issuer", "Other", "Unknown"
}

OUTPUT.mkdir(parents=True, exist_ok=True)

if not INPUT.exists():
    raise FileNotFoundError(f"Khong tim thay: {INPUT}")

# 1. Load verified label data
labels = pd.read_csv(LABELS, dtype=str).fillna("")

required_labels = {
    "address", "entity_name", "entity_type",
    "source_url", "confidence"
}
missing = required_labels - set(labels.columns)
if missing:
    raise ValueError(f"Missing label columns: {missing}")

labels["address"] = labels["address"].str.strip().str.lower()

invalid_types = set(labels["entity_type"]) - ALLOWED_TYPES
if invalid_types:
    raise ValueError(f"Invalid entity types: {invalid_types}")

labels = labels.drop_duplicates("address", keep="last")
labels_map = labels.set_index("address").to_dict("index")

# 2. Aggregate wallet activity across all transfers
wallets = defaultdict(lambda: {
    "incoming_usdt": 0.0,
    "outgoing_usdt": 0.0,
    "incoming_transfers": 0,
    "outgoing_transfers": 0
})

pf = pq.ParquetFile(INPUT)

print("===== T07 FULL WALLET LABELING =====")
print("Input file:", INPUT)
print("Input transfer rows:", f"{pf.metadata.num_rows:,}")

columns = [
    "from_address", "to_address", "amount"
]

total_rows = 0
total_usdt = 0.0

for batch_id, batch in enumerate(
    pf.iter_batches(
        columns=columns,
        batch_size=100_000
    ),
    start=1
):
    df = batch.to_pandas()

    df["from_address"] = (
        df["from_address"].astype("string").str.lower().str.strip()
    )
    df["to_address"] = (
        df["to_address"].astype("string").str.lower().str.strip()
    )
    df["amount"] = pd.to_numeric(
        df["amount"], errors="coerce"
    )

    if df["amount"].isna().any() or (df["amount"] < 0).any():
        raise ValueError(f"Invalid amount in batch {batch_id}")

    if df[["from_address", "to_address"]].isna().any().any():
        raise ValueError(f"Missing address in batch {batch_id}")

    outgoing = df.groupby("from_address").agg(
        amount=("amount", "sum"),
        count=("amount", "size")
    )

    incoming = df.groupby("to_address").agg(
        amount=("amount", "sum"),
        count=("amount", "size")
    )

    for address, row in outgoing.iterrows():
        wallets[address]["outgoing_usdt"] += float(row["amount"])
        wallets[address]["outgoing_transfers"] += int(row["count"])

    for address, row in incoming.iterrows():
        wallets[address]["incoming_usdt"] += float(row["amount"])
        wallets[address]["incoming_transfers"] += int(row["count"])

    total_rows += len(df)
    total_usdt += float(df["amount"].sum())

    if batch_id % 5 == 0 or batch_id == 1 or total_rows >= pf.metadata.num_rows:
        print(
            f"Batch {batch_id}: "
            f"{total_rows:,} / {pf.metadata.num_rows:,} transfers processed",
            flush=True
        )

# 3. Build one row per unique address
results = []

for address, activity in wallets.items():

    verified = labels_map.get(address, {})

    entity_name = verified.get("entity_name") or "Unknown"
    entity_type = verified.get("entity_type") or "Unknown"

    incoming = activity["incoming_usdt"]
    outgoing = activity["outgoing_usdt"]

    url = verified.get("source_url", "")
    source = verified.get("source", "")
    if not source and url:
        source = urlparse(url).netloc

    results.append({
        "address": address,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "class": verified.get("class", ""),
        "source": source,
        "source_url": url,
        "evidence": verified.get("evidence", ""),
        "confidence": (
            verified.get("confidence") or "Unverified"
        ),
        "date_downloaded": verified.get("date_downloaded", ""),
        "incoming_usdt": incoming,
        "outgoing_usdt": outgoing,
        "gross_flow_usdt": incoming + outgoing,
        "net_inflow_usdt": incoming - outgoing,
        "incoming_transfers": activity["incoming_transfers"],
        "outgoing_transfers": activity["outgoing_transfers"],
        "total_transfers": (
            activity["incoming_transfers"]
            + activity["outgoing_transfers"]
        )
    })

result = pd.DataFrame(results).sort_values(
    "gross_flow_usdt", ascending=False
)

# 4. Save output
output_parquet = OUTPUT / "t07_all_wallet_labels.parquet"

result.to_parquet(
    output_parquet,
    index=False
)


# 5. Summary
counts = {
    category: int(
        (result["entity_type"] == category).sum()
    )
    for category in sorted(ALLOWED_TYPES)
}

summary = {
    "input_file": str(INPUT),
    "total_transfer_rows_processed": total_rows,
    "total_transfer_usdt": total_usdt,
    "unique_addresses": len(result),
    "labeled_addresses": int(
        (result["entity_type"] != "Unknown").sum()
    ),
    "unknown_addresses": counts["Unknown"],
    "counts_by_entity_type": counts,
    "note": (
        "These are submitted source labels, not an "
        "independent verification of all entity identities. "
        "Transfer rows are counted as supplied in the input."
    )
}

summary_json = OUTPUT / "t07_full_summary.json"
summary_json.write_text(
    json.dumps(summary, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print("\n===== T07 FULL RESULTS =====")
print("Transfers processed:", f"{total_rows:,}")
print("Total transfer USDT:", f"{total_usdt:,.2f}")
print("Unique addresses:", f"{len(result):,}")

print("\n===== ENTITY TYPE COUNTS =====")
for category, count in counts.items():
    print(f"{category}: {count:,}")

print("\nOutputs:")
print(output_parquet)
print(summary_json)
