
"""
T07 - Mass Wallet Labeling + Deep Entity Enrichment
Ethereum USDT Whale Analysis

INPUT:
    data/processed/t07/t07_public_enriched_wallet_labels.parquet

OUTPUT:
    data/processed/t07/t07_mass_enriched_wallet_labels.parquet
    data/processed/t07/t07_mass_enrichment_summary.json
    data/processed/t07/t07_rpc_cache.parquet
    data/processed/t07/t07_blockscout_cache.jsonl
    data/processed/t07/t07_deep_review.parquet

FEATURES:
    1. Preserve existing entity labels
    2. Reuse completed eth_getCode RPC cache
    3. Identify Contract / EOA
    4. Query Blockscout public address metadata
    5. Deep classify only when explicit category evidence exists
    6. Support curated evidence for all 10 label groups
    7. Save progress and allow resuming
    8. Never classify solely from transaction volume

No raw USDT transfers are reprocessed.
"""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parent
DIR = ROOT / "data" / "processed" / "t07"
EXTERNAL = ROOT / "data" / "external"

RPC_DEFAULT = "https://ethereum-rpc.publicnode.com"
BLOCKSCOUT_DEFAULT = "https://eth.blockscout.com/api/v2"

PATTERN = re.compile(r"^0x[0-9a-f]{40}$")

LABELS = (
    "CEX",
    "DEX",
    "DeFi",
    "Bridge",
    "Custodian",
    "Contract",
    "Protocol",
    "Issuer",
    "Other",
    "Unknown",
)

RPC_CACHE = DIR / "t07_rpc_cache.parquet"
BLOCKSCOUT_CACHE = DIR / "t07_blockscout_cache.jsonl"

OUTPUT = DIR / "t07_mass_enriched_wallet_labels.parquet"
SUMMARY = DIR / "t07_mass_enrichment_summary.json"
REVIEW = DIR / "t07_deep_review.parquet"

CURATED = EXTERNAL / "t07_curated_entity_evidence.csv"

CACHE_COLUMNS = [
    "address",
    "status",
    "rpc_url",
    "checked_at",
]

# Only explicit category tags qualify for automatic classification.
# Names such as "Uniswap", "Aave", "Tether", or "Vault" alone
# are NOT treated as sufficient proof of a category.

CATEGORY_ALIASES = {
    "CEX": {
        "cex",
        "centralized exchange",
        "centralised exchange",
        "centralized exchange wallet",
    },
    "DEX": {
        "dex",
        "decentralized exchange",
        "decentralised exchange",
    },
    "DeFi": {
        "defi",
        "decentralized finance",
        "decentralised finance",
        "defi protocol",
    },
    "Bridge": {
        "bridge",
        "cross chain bridge",
        "cross-chain bridge",
        "token bridge",
    },
    "Custodian": {
        "custodian",
        "custody provider",
        "institutional custodian",
        "digital asset custodian",
    },
    "Protocol": {
        "protocol",
        "blockchain protocol",
        "protocol infrastructure",
    },
    "Issuer": {
        "issuer",
        "token issuer",
        "stablecoin issuer",
    },
}

# Generic tags are deliberately excluded:
# "contract", "token", "exchange", "wallet", "proxy", etc.


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def normalized_address(value):
    return str(value).strip().lower()


def normalize_tag(value):
    value = str(value).strip().lower()
    value = re.sub(r"[_/]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value


def atomic_write_table(df, path):
    temp = path.with_name(path.name + ".tmp")
    df.to_parquet(temp, index=False)
    os.replace(temp, path)


def atomic_write_parquet(df, path):
    temp = path.with_name(path.name + ".tmp")
    df.to_parquet(temp, index=False)
    os.replace(temp, path)


def atomic_write_json(data, path):
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp, path)


# ============================================================
# PART 1 - EXISTING RPC IDENTIFICATION
# ============================================================

def rpc_batch(url, addresses, timeout=45):

    payload = [
        {
            "jsonrpc": "2.0",
            "id": i,
            "method": "eth_getCode",
            "params": [address, "latest"],
        }
        for i, address in enumerate(addresses)
    ]

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "T07-research/2.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request, timeout=timeout
    ) as response:
        data = json.loads(response.read())

    if not isinstance(data, list):
        raise RuntimeError("RPC batch unsupported")

    results = {}

    for item in data:

        index = item.get("id")

        if not isinstance(index, int):
            continue

        if index < 0 or index >= len(addresses):
            continue

        value = item.get("result")

        if isinstance(value, str) and value.startswith("0x"):
            results[addresses[index]] = (
                "Contract" if value != "0x" else "EOA"
            )

    if len(results) != len(addresses):
        raise RuntimeError(
            f"RPC resolved {len(results)}/{len(addresses)}"
        )

    return results


def load_rpc_cache():

    if not RPC_CACHE.exists():
        return pd.DataFrame(columns=CACHE_COLUMNS)

    cache = pd.read_parquet(RPC_CACHE).fillna("")

    if not set(CACHE_COLUMNS).issubset(cache.columns):
        raise ValueError("Invalid RPC cache columns")

    cache["address"] = cache["address"].map(normalized_address)

    cache = cache[
        cache["status"].isin(["Contract", "EOA"])
    ]

    cache = cache.drop_duplicates(
        "address", keep="last"
    )

    return cache


def identify_contracts(df, args):

    cache = load_rpc_cache()

    found = dict(zip(cache.address, cache.status))

    unknown = df[df.entity_type.eq("Unknown")].copy()

    if "gross_flow_usdt" in unknown.columns:
        unknown = unknown.sort_values(
            "gross_flow_usdt",
            ascending=False,
        )

    addresses = unknown.address.tolist()

    # Addresses with previous RPC results do not need scanning.
    pending = [
        address for address in addresses
        if address not in found
    ]

    if args.max_addresses > 0:
        pending = pending[:args.max_addresses]

    print("\n===== RPC CHECK =====")
    print("RPC cache:", f"{len(cache):,}")
    print("Pending RPC:", f"{len(pending):,}")

    new_rows = []
    errors = 0

    for start in range(0, len(pending), args.batch_size):

        batch = pending[
            start:start + args.batch_size
        ]

        result = None

        for attempt in range(4):
            try:
                result = rpc_batch(args.rpc, batch)
                break

            except Exception as exc:
                errors += 1

                if attempt == 3:
                    print("RPC failed:", str(exc)[:180])
                else:
                    time.sleep(min(30, 2 ** attempt * 2))

        if result is None:
            print("RPC stopped; progress is cached.")
            break

        checked_at = utc_now()

        for address, status in result.items():

            new_rows.append({
                "address": address,
                "status": status,
                "rpc_url": args.rpc,
                "checked_at": checked_at,
            })

        batch_no = start // args.batch_size + 1

        if (
            batch_no % args.checkpoint_every == 0
            or start + len(batch) >= len(pending)
        ):
            current = pd.concat(
                [cache, pd.DataFrame(new_rows)],
                ignore_index=True,
            )

            atomic_write_table(current, RPC_CACHE)

            print(
                "RPC checked:",
                f"{min(start + len(batch), len(pending)):,}",
                "/",
                f"{len(pending):,}",
                flush=True,
            )

        time.sleep(max(args.sleep, 0))

    if new_rows:

        cache = pd.concat(
            [cache, pd.DataFrame(new_rows)],
            ignore_index=True,
        )

        cache = cache.drop_duplicates(
            "address", keep="last"
        )

        atomic_write_table(cache, RPC_CACHE)

    code_map = dict(zip(cache.address, cache.status))

    is_unknown = df.entity_type.eq("Unknown")
    is_contract = df.address.map(code_map).eq("Contract")

    add_mask = is_unknown & is_contract

    df.loc[add_mask, "entity_type"] = "Contract"
    df.loc[add_mask, "entity_name"] = (
        "Unattributed smart contract"
    )
    df.loc[add_mask, "source"] = (
        "Ethereum JSON-RPC eth_getCode"
    )
    df.loc[add_mask, "source_url"] = args.rpc
    df.loc[add_mask, "evidence"] = (
        "Non-empty bytecode at latest block; "
        "entity identity not established"
    )
    df.loc[add_mask, "confidence"] = (
        "High (contract status only)"
    )
    df.loc[add_mask, "date_downloaded"] = (
        datetime.now(timezone.utc).date().isoformat()
    )

    df["address_kind"] = (
        df.address.map(code_map).map({
            "Contract": "Contract (latest)",
            "EOA": "EOA (latest)",
        }).fillna("Not checked")
    )

    print("New technical Contract labels:", int(add_mask.sum()))

    return df, errors, len(new_rows)


# ============================================================
# PART 2 - BLOCKSCOUT METADATA
# ============================================================

def blockscout_request(base_url, address, timeout=30):

    url = (
        base_url.rstrip("/")
        + "/addresses/"
        + address
    )

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "T07-research/2.0",
        },
    )

    with urllib.request.urlopen(
        request, timeout=timeout
    ) as response:

        data = json.loads(response.read())

    if not isinstance(data, dict):
        raise ValueError("Invalid Blockscout response")

    return data, url


def extract_metadata(payload):

    smart = payload.get("smart_contract") or {}

    if not isinstance(smart, dict):
        smart = {}

    public_tags = payload.get("public_tags") or []

    tags = []

    if isinstance(public_tags, list):

        for item in public_tags:

            if isinstance(item, dict):
                value = item.get("label") or item.get("name")
            elif isinstance(item, str):
                value = item
            else:
                value = None

            if value:
                tags.append(str(value).strip())

    # Public tag structure can vary by Blockscout version.
    # We use ONLY explicit public_tags categories.
    # Contract names are recorded for review, not classification.

    contract_name = (
        smart.get("name")
        or payload.get("name")
        or ""
    )

    return {
        "contract_name": str(contract_name),
        "is_verified": bool(
            smart.get("is_verified", False)
        ),
        "public_tags": tags,
        "is_contract": bool(payload.get("is_contract", False)),
    }


def classify_public_tags(tags):

    matched = set()

    for tag in tags:

        normalized = normalize_tag(tag)

        for category, aliases in CATEGORY_ALIASES.items():

            if normalized in aliases:
                matched.add(category)

    if len(matched) == 1:
        return next(iter(matched)), "explicit_public_tag"

    if len(matched) > 1:
        return None, "ambiguous_public_tags"

    return None, "no_explicit_category"


def load_blockscout_cache():

    cache = {}

    if not BLOCKSCOUT_CACHE.exists():
        return cache

    with BLOCKSCOUT_CACHE.open(
        "r", encoding="utf-8"
    ) as file:

        for line in file:

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            address = normalized_address(
                record.get("address", "")
            )

            if not PATTERN.fullmatch(address):
                continue

            # Only successful responses are reusable.
            if record.get("status") == "ok":
                cache[address] = record

    return cache


def append_blockscout_cache(record):

    with BLOCKSCOUT_CACHE.open(
        "a", encoding="utf-8"
    ) as file:

        file.write(
            json.dumps(record, ensure_ascii=False)
            + "\n"
        )


def enrich_contracts(df, args):

    print("\n===== DEEP CONTRACT ENRICHMENT =====")

    cache = load_blockscout_cache()

    contracts = df[
        df.entity_type.eq("Contract")
    ].copy()

    if "gross_flow_usdt" in contracts.columns:
        contracts = contracts.sort_values(
            "gross_flow_usdt",
            ascending=False,
        )

    all_contracts = contracts.address.tolist()

    pending = [
        address for address in all_contracts
        if address not in cache
    ]

    if args.deep_limit > 0:
        pending = pending[:args.deep_limit]

    print("Contract candidates:", f"{len(all_contracts):,}")
    print("Cached metadata:", f"{len(cache):,}")
    print("Pending requests:", f"{len(pending):,}")

    success = 0
    failed = 0

    for index, address in enumerate(pending, start=1):

        record = None

        for attempt in range(3):

            try:

                payload, url = blockscout_request(
                    args.blockscout,
                    address,
                )

                metadata = extract_metadata(payload)

                record = {
                    "address": address,
                    "status": "ok",
                    "url": url,
                    "checked_at": utc_now(),
                    "metadata": metadata,
                }

                break

            except (
                urllib.error.URLError,
                TimeoutError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:

                if attempt == 2:
                    print(
                        "Blockscout failed:",
                        address,
                        str(exc)[:120],
                    )
                else:
                    time.sleep(2 ** attempt * 2)

        if record is not None:

            append_blockscout_cache(record)

            cache[address] = record

            success += 1

        else:
            failed += 1

        if index % 100 == 0 or index == len(pending):

            print(
                f"Deep requests: {index:,}/{len(pending):,}",
                f"success={success:,}",
                f"failed={failed:,}",
                flush=True,
            )

        time.sleep(max(args.deep_sleep, 0))

    # Apply cached metadata to all Contract candidates.
    # Preserve labels if classification is not explicit.

    reviews = []
    upgrades = 0

    index_by_address = {
        address: idx
        for idx, address in enumerate(df.address)
    }

    for address in all_contracts:

        record = cache.get(address)

        if not record:
            continue

        metadata = record.get("metadata", {})

        tags = metadata.get("public_tags", [])

        new_category, decision = classify_public_tags(tags)

        idx = index_by_address[address]

        contract_name = metadata.get("contract_name", "")
        source_url = record.get("url", "")

        if new_category:

            # Only upgrade generic Contract.
            # Existing named entities are never overwritten.
            if df.at[idx, "entity_type"] == "Contract":

                df.at[idx, "entity_type"] = new_category

                if contract_name:
                    df.at[idx, "entity_name"] = contract_name

                df.at[idx, "source"] = (
                    "Blockscout public address tag"
                )

                df.at[idx, "source_url"] = source_url

                df.at[idx, "evidence"] = (
                    "Explicit public category tag: "
                    + ", ".join(tags)
                )

                df.at[idx, "confidence"] = (
                    "Medium (external public tag)"
                )

                df.at[idx, "date_downloaded"] = (
                    datetime.now(timezone.utc)
                    .date()
                    .isoformat()
                )

                upgrades += 1

        else:

            if decision == "ambiguous_public_tags":

                reviews.append({
                    "address": address,
                    "contract_name": contract_name,
                    "public_tags": json.dumps(tags),
                    "reason": "Conflicting category tags",
                    "source_url": source_url,
                })

    print("Deep category upgrades:", upgrades)

    return df, reviews, {
        "deep_contract_candidates": len(all_contracts),
        "deep_success_this_run": success,
        "deep_failed_this_run": failed,
        "deep_upgraded_this_run": upgrades,
        "blockscout_cached": len(cache),
    }


# ============================================================
# PART 3 - CURATED VERIFIED ENTITY EVIDENCE
# ============================================================

def apply_curated_evidence(df, reviews):

    """
    Optional CSV:
    data/external/t07_curated_entity_evidence.csv

    Required:
        address,entity_name,entity_type,source_url,evidence

    Optional:
        confidence,date_downloaded

    Only explicitly verified, non-conflicting records
    should be placed in this file.
    """

    if not CURATED.exists():
        print("No curated entity evidence CSV found.")
        return df, reviews, 0

    curated = pd.read_csv(
        CURATED, dtype=str
    ).fillna("")

    required = {
        "address",
        "entity_name",
        "entity_type",
        "source_url",
        "evidence",
    }

    if not required.issubset(curated.columns):
        raise ValueError(
            "Curated CSV missing columns: "
            + str(required - set(curated.columns))
        )

    curated["address"] = (
        curated.address.map(normalized_address)
    )

    curated["entity_type"] = (
        curated.entity_type.str.strip()
    )

    bad = curated[
        ~curated.address.map(
            lambda x: bool(PATTERN.fullmatch(x))
        )
        | ~curated.entity_type.isin(LABELS)
        | curated.entity_type.eq("Unknown")
        | curated.entity_name.str.strip().eq("")
        | ~curated.source_url.str.startswith(
            ("http://", "https://")
        )
        | curated.evidence.str.strip().eq("")
    ]

    if not bad.empty:
        raise ValueError(
            f"{len(bad)} curated rows have invalid evidence"
        )

    # Resolve duplicate inputs conservatively:
    # never choose arbitrarily between conflicting labels.
    duplicates = curated[
        curated.duplicated("address", keep=False)
    ]

    ambiguous = set()

    for address, group in duplicates.groupby("address"):

        if (
            group["entity_type"].nunique() > 1
            or group["entity_name"].nunique() > 1
        ):
            ambiguous.add(address)

            reviews.append({
                "address": address,
                "contract_name": "",
                "public_tags": "",
                "reason": "Conflicting curated evidence",
                "source_url": "; ".join(
                    group.source_url.tolist()
                ),
            })

    curated = curated[
        ~curated.address.isin(ambiguous)
    ].drop_duplicates("address")

    lookup = df.set_index("address").index
    curated = curated[
        curated.address.isin(lookup)
    ]

    index_by_address = {
        address: idx
        for idx, address in enumerate(df.address)
    }

    added = 0

    for row in curated.itertuples(index=False):

        idx = index_by_address[row.address]

        current = df.at[idx, "entity_type"]

        # Protect existing specific entity classifications.
        if current not in ("Unknown", "Contract"):

            if current != row.entity_type:

                reviews.append({
                    "address": row.address,
                    "contract_name": row.entity_name,
                    "public_tags": row.entity_type,
                    "reason": (
                        "Curated label conflicts with "
                        "existing specific category"
                    ),
                    "source_url": row.source_url,
                })

            continue

        # Source URL and evidence are required above,
        # but their truth is not independently verified by code.

        df.at[idx, "entity_type"] = row.entity_type
        df.at[idx, "entity_name"] = row.entity_name
        df.at[idx, "source"] = "Curated external evidence"
        df.at[idx, "source_url"] = row.source_url
        df.at[idx, "evidence"] = row.evidence

        confidence = getattr(row, "confidence", "")
        df.at[idx, "confidence"] = (
            confidence or "Requires source review"
        )

        downloaded = getattr(row, "date_downloaded", "")
        df.at[idx, "date_downloaded"] = downloaded

        added += 1

    print("Curated entity labels applied:", added)

    return df, reviews, added


# ============================================================
# PART 4 - REPORT
# ============================================================

def generate_report(df, reviews, rpc_errors, rpc_new, deep_stats,
                    curated_added, input_path):

    counts = {
        label: int(df.entity_type.eq(label).sum())
        for label in LABELS
    }

    known = len(df) - counts["Unknown"]

    summary = {
        "input": str(input_path),
        "total_addresses": len(df),
        "classified_non_unknown": known,
        "unknown_addresses": counts["Unknown"],
        "classification_coverage_pct": round(
            known / len(df) * 100, 4
        ),
        "rpc_new_address_checks": rpc_new,
        "rpc_failure_attempts": rpc_errors,
        "deep": deep_stats,
        "curated_labels_applied": curated_added,
        "review_cases": len(reviews),
        "label_counts": counts,
        "limitations": [
            "Contract is a technical label, not verified ownership.",
            "EOA identity cannot be inferred from eth_getCode.",
            "Blockscout public tags are external attributions.",
            "Curated evidence requires independent source review.",
            "No classification is inferred from USDT transaction volume.",
        ],
        "completed_at": utc_now(),
    }

    atomic_write_parquet(df, OUTPUT)

    atomic_write_json(summary, SUMMARY)

    review_columns = [
        "address",
        "contract_name",
        "public_tags",
        "reason",
        "source_url",
    ]

    review_df = pd.DataFrame(
        reviews, columns=review_columns
    )

    atomic_write_table(review_df, REVIEW)

    print("\n===== T07 MASS + DEEP RESULTS =====")

    print("Total addresses:", f"{len(df):,}")
    print("Non-Unknown:", f"{known:,}")
    print("Unknown:", f"{counts['Unknown']:,}")
    print(
        "Coverage:",
        f"{summary['classification_coverage_pct']:.4f}%"
    )

    print("\n===== 10 ENTITY TYPES =====")

    for label, count in counts.items():
        print(f"{label}: {count:,}")

    print("\n===== DEEP STATS =====")

    for key, value in deep_stats.items():
        print(f"{key}: {value}")

    print("Curated applied:", curated_added)
    print("Review cases:", len(reviews))

    print("\nSaved:", OUTPUT)
    print("Summary:", SUMMARY)
    print("Review:", REVIEW)


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--rpc",
        default=os.environ.get(
            "ETH_RPC_URL", RPC_DEFAULT
        ),
    )

    parser.add_argument(
        "--batch-size", type=int, default=30
    )

    parser.add_argument(
        "--sleep", type=float, default=0.5
    )

    parser.add_argument(
        "--max-addresses", type=int, default=0
    )

    parser.add_argument(
        "--checkpoint-every", type=int, default=20
    )

    parser.add_argument(
        "--deep",
        action="store_true",
        help="Enable Blockscout deep enrichment",
    )

    parser.add_argument(
        "--deep-limit",
        type=int,
        default=0,
        help="0 = all pending contracts",
    )

    parser.add_argument(
        "--deep-sleep",
        type=float,
        default=0.5,
    )

    parser.add_argument(
        "--blockscout",
        default=BLOCKSCOUT_DEFAULT,
    )

    args = parser.parse_args()

    if args.batch_size < 1 or args.batch_size > 100:
        parser.error("batch-size must be 1..100")

    if args.deep_limit < 0 or args.max_addresses < 0:
        parser.error("limits must be non-negative")

    if args.checkpoint_every < 1:
        parser.error("checkpoint-every must be >= 1")

    DIR.mkdir(parents=True, exist_ok=True)

    candidates = [
        DIR / "t07_public_enriched_wallet_labels.parquet",
        DIR / "t07_all_wallet_labels.parquet",
    ]

    source = next(
        (p for p in candidates if p.exists()),
        None,
    )

    if source is None:
        raise FileNotFoundError(
            "Missing T07 wallet label input"
        )

    df = pd.read_parquet(source)

    if "address" not in df or "entity_type" not in df:
        raise ValueError(
            "Input must contain address and entity_type"
        )

    df["address"] = (
        df.address.map(normalized_address)
    )

    if len(df) != 115167:
        raise ValueError(
            "Expected 115,167 addresses; got "
            + str(len(df))
        )

    if df.address.duplicated().any():
        raise ValueError("Duplicate address detected")

    if not df.address.map(
        lambda x: bool(PATTERN.fullmatch(x))
    ).all():
        raise ValueError("Invalid Ethereum address")

    df["entity_type"] = (
        df.entity_type.fillna("Unknown").astype(str)
    )

    invalid = set(df.entity_type) - set(LABELS)

    if invalid:
        raise ValueError(
            f"Unexpected entity types: {invalid}"
        )

    for col in [
        "entity_name",
        "source",
        "source_url",
        "evidence",
        "confidence",
        "date_downloaded",
    ]:
        if col not in df:
            df[col] = ""

    print("===== T07 INTEGRATED PIPELINE =====")
    print("Input:", source)
    print("Addresses:", f"{len(df):,}")

    # Reuse existing RPC cache.
    df, rpc_errors, rpc_new = identify_contracts(
        df, args
    )

    reviews = []

    deep_stats = {
        "deep_contract_candidates": 0,
        "deep_success_this_run": 0,
        "deep_failed_this_run": 0,
        "deep_upgraded_this_run": 0,
        "blockscout_cached": 0,
    }

    if args.deep:
        df, reviews, deep_stats = enrich_contracts(
            df, args
        )

    df, reviews, curated_added = apply_curated_evidence(
        df, reviews
    )

    generate_report(
        df=df,
        reviews=reviews,
        rpc_errors=rpc_errors,
        rpc_new=rpc_new,
        deep_stats=deep_stats,
        curated_added=curated_added,
        input_path=source,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
