
"""
T06 - BINANCE ETHUSDT MARKET DATA PIPELINE

Du an: On-chain Network & Whale Contagion Analysis
Nguon: Binance Vision - Spot Trades
Giai doan: 2025-01-01 den 2026-10-17 (UTC)

Chuc nang:
    status
    download
    aggregate-1m
    aggregate-higher
    validate

Du lieu lon duoc luu ngoai GitHub.
Chuong trinh khong tu tai du lieu khi khoi dong.
"""

import argparse
import json
import tempfile
import time
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests


# ============================================================
# 1. CONFIGURATION
# ============================================================

SYMBOL = "ETHUSDT"
START_DATE = "2025-01-01"
END_DATE = "2026-10-17"
CHUNK_SIZE = 100_000

BINANCE_URL = (
    "https://data.binance.vision/data/spot/daily/trades"
)

RAW_COLUMNS = [
    "trade_id",
    "price",
    "quantity",
    "quote_quantity",
    "trade_time",
    "is_buyer_maker",
    "is_best_match",
]

SUM_COLUMNS = [
    "volume_eth",
    "volume_usdt",
    "trade_count",
    "buy_volume_eth",
    "sell_volume_eth",
    "buy_volume_usdt",
    "sell_volume_usdt",
]

OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    **{col: "sum" for col in SUM_COLUMNS},
}


# ============================================================
# 2. FILE PATHS
# ============================================================

def raw_path(root, day):
    d = date.fromisoformat(day)

    return (
        root / "trades"
        / f"year={d.year}"
        / f"month={d.month:02d}"
        / f"{SYMBOL}_trades_{day}.parquet"
    )


def minute_path(root, day):
    return (
        root / "processed" / "ohlcv_1m"
        / f"{SYMBOL}_1m_{day}.parquet"
    )


def higher_path(root, interval):
    return (
        root / "processed" / f"ohlcv_{interval}"
        / f"{SYMBOL}_{interval}_2025-2026.parquet"
    )


def valid_parquet(path, expected_rows=None):
    if not path.exists():
        return False

    try:
        rows = pq.read_metadata(path).num_rows

        if expected_rows is not None:
            return rows == expected_rows

        return rows > 0

    except Exception:
        return False


def save_parquet(df, path):
    """Ghi file tam, sau do moi thay file chinh."""
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(".part")

    try:
        df.to_parquet(
            temporary,
            index=False,
            compression="zstd",
        )
        temporary.replace(path)

    finally:
        temporary.unlink(missing_ok=True)


def log_download(root, record):
    folder = root / "logs"
    folder.mkdir(parents=True, exist_ok=True)

    log_file = folder / "t06_download_manifest.jsonl"

    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ============================================================
# 3. DOWNLOAD BINANCE TRADES
# ============================================================

def download_day(root, day):
    output = raw_path(root, day)

    if valid_parquet(output):
        print(f"SKIP {day}: raw data exists")
        return "skipped"

    url = (
        f"{BINANCE_URL}/{SYMBOL}/"
        f"{SYMBOL}-trades-{day}.zip"
    )

    writer = None
    total_rows = 0
    first_time = None
    last_time = None

    # Thu muc tam cua moi truong dang chay.
    # Neu chay local, van ton dung luong tam tren laptop.
    with tempfile.TemporaryDirectory(prefix="t06_") as tmp:
        temp_dir = Path(tmp)
        zip_file = temp_dir / "trades.zip"
        parquet_file = temp_dir / "trades.parquet"

        try:
            # 3.1 Download ZIP
            with requests.get(
                url,
                stream=True,
                timeout=(20, 120),
            ) as response:

                response.raise_for_status()

                with zip_file.open("wb") as f:
                    for block in response.iter_content(
                        chunk_size=1024 * 1024
                    ):
                        if block:
                            f.write(block)

            # 3.2 Read CSV in chunks
            with zipfile.ZipFile(zip_file) as z:

                csv_name = next(
                    name for name in z.namelist()
                    if name.lower().endswith(".csv")
                )

                with z.open(csv_name) as f:
                    first_line = (
                        f.readline()
                        .decode("utf-8-sig")
                        .strip()
                        .lower()
                    )

                has_header = first_line.startswith(
                    ("id,", "trade_id,")
                )

                with z.open(csv_name) as f:

                    chunks = pd.read_csv(
                        f,
                        names=RAW_COLUMNS,
                        header=0 if has_header else None,
                        chunksize=CHUNK_SIZE,
                    )

                    for chunk in chunks:

                        for column in [
                            "trade_id",
                            "trade_time",
                        ]:
                            chunk[column] = pd.to_numeric(
                                chunk[column],
                                errors="raise",
                            ).astype("int64")

                        for column in [
                            "price",
                            "quantity",
                            "quote_quantity",
                        ]:
                            chunk[column] = pd.to_numeric(
                                chunk[column],
                                errors="raise",
                            )

                        chunk["datetime_utc"] = pd.to_datetime(
                            chunk["trade_time"],
                            unit="us",
                            utc=True,
                        )

                        chunk["symbol"] = SYMBOL

                        t_min = chunk["datetime_utc"].min()
                        t_max = chunk["datetime_utc"].max()

                        first_time = (
                            t_min if first_time is None
                            else min(first_time, t_min)
                        )

                        last_time = (
                            t_max if last_time is None
                            else max(last_time, t_max)
                        )

                        table = pa.Table.from_pandas(
                            chunk,
                            preserve_index=False,
                        )

                        if writer is None:
                            writer = pq.ParquetWriter(
                                parquet_file,
                                table.schema,
                                compression="zstd",
                            )

                        writer.write_table(table)
                        total_rows += len(chunk)

            if writer is not None:
                writer.close()
                writer = None

            # 3.3 Basic validation
            if total_rows == 0:
                raise ValueError("Empty trade data")

            expected_day = date.fromisoformat(day)

            if (
                first_time.date() != expected_day
                or last_time.date() != expected_day
            ):
                raise ValueError("Incorrect UTC date")

            if pq.read_metadata(parquet_file).num_rows != total_rows:
                raise ValueError("Parquet row count mismatch")

            # 3.4 Save completed Parquet
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary_output = output.with_suffix(".part")

            import shutil

            try:
                shutil.copyfile(parquet_file, temporary_output)
                temporary_output.replace(output)
            finally:
                temporary_output.unlink(missing_ok=True)

            log_download(root, {
                "date": day,
                "status": "success",
                "rows": total_rows,
                "source": url,
            })

            print(f"OK {day} | {total_rows:,} trades")
            return "success"

        except Exception as exc:
            log_download(root, {
                "date": day,
                "status": "failed",
                "error": str(exc),
            })
            raise

        finally:
            if writer is not None:
                writer.close()


# ============================================================
# 4. MARKET INDICATORS
# ============================================================

def add_indicators(df):
    volume = df["volume_eth"].replace(0, np.nan)

    # Volume Weighted Average Price
    df["vwap"] = df["volume_usdt"] / volume

    # Taker Buy - Taker Sell
    df["imbalance_eth"] = (
        df["buy_volume_eth"] - df["sell_volume_eth"]
    ) / volume

    return df


# ============================================================
# 5. AGGREGATE RAW TRADES TO 1 MINUTE
# ============================================================

def aggregate_day(root, day):
    source = raw_path(root, day)
    output = minute_path(root, day)

    if valid_parquet(output, expected_rows=1440):
        print(f"SKIP {day}: 1m data exists")
        return "skipped"

    if not source.exists():
        raise FileNotFoundError(source)

    parquet = pq.ParquetFile(source)
    partials = []

    columns = [
        "price",
        "quantity",
        "quote_quantity",
        "datetime_utc",
        "is_buyer_maker",
    ]

    for batch in parquet.iter_batches(
        batch_size=CHUNK_SIZE,
        columns=columns,
    ):
        df = batch.to_pandas()

        df["minute"] = pd.to_datetime(
            df["datetime_utc"],
            utc=True,
        ).dt.floor("min")

        # False: buyer is taker -> aggressive buy
        # True: buyer is maker -> aggressive sell
        buy_mask = ~df["is_buyer_maker"].astype(bool)

        df["buy_eth"] = np.where(
            buy_mask, df["quantity"], 0.0
        )
        df["sell_eth"] = np.where(
            ~buy_mask, df["quantity"], 0.0
        )

        df["buy_usdt"] = np.where(
            buy_mask, df["quote_quantity"], 0.0
        )
        df["sell_usdt"] = np.where(
            ~buy_mask, df["quote_quantity"], 0.0
        )

        part = df.groupby("minute", sort=True).agg(
            open=("price", "first"),
            high=("price", "max"),
            low=("price", "min"),
            close=("price", "last"),
            volume_eth=("quantity", "sum"),
            volume_usdt=("quote_quantity", "sum"),
            trade_count=("price", "size"),
            buy_volume_eth=("buy_eth", "sum"),
            sell_volume_eth=("sell_eth", "sum"),
            buy_volume_usdt=("buy_usdt", "sum"),
            sell_volume_usdt=("sell_usdt", "sum"),
        )

        partials.append(part)

    if not partials:
        raise ValueError(f"No trades for {day}")

    # Merge minutes across chunk boundaries
    combined = pd.concat(partials)

    minute = (
        combined.groupby(level=0, sort=True)
        .agg(OHLCV_AGG)
        .reset_index()
    )

    minute = add_indicators(minute)

    # Validate source trade count
    total_trades = int(minute["trade_count"].sum())

    if total_trades != parquet.metadata.num_rows:
        raise ValueError("Trade count mismatch")

    if len(minute) != 1440:
        raise ValueError(
            f"Expected 1440 minutes, got {len(minute)}"
        )

    save_parquet(minute, output)

    print(
        f"OK {day} | 1440 minutes | "
        f"{total_trades:,} trades"
    )

    return "success"


# ============================================================
# 6. AGGREGATE 1 MINUTE TO 1 HOUR / 1 DAY
# ============================================================

def aggregate_higher(root):
    minute_dir = root / "processed" / "ohlcv_1m"

    days = pd.date_range(START_DATE, END_DATE)

    files = [
        minute_path(root, d.strftime("%Y-%m-%d"))
        for d in days
    ]

    missing = [p for p in files if not p.exists()]

    if missing:
        raise ValueError(
            f"Missing {len(missing)} minute files. "
            f"Example: {missing[0].name}"
        )

    # ~943,200 minute rows: smaller than raw trades
    df = pd.concat(
        [pd.read_parquet(p) for p in files],
        ignore_index=True,
    )

    df["minute"] = pd.to_datetime(
        df["minute"], utc=True
    )

    df = df.sort_values("minute").set_index("minute")

    if len(df) != len(days) * 1440:
        raise ValueError("Unexpected number of minute rows")

    input_count = int(df["trade_count"].sum())

    for freq, expected_rows in [
        ("1h", len(days) * 24),
        ("1d", len(days)),
    ]:
        rule = "1h" if freq == "1h" else "1D"

        result = df.resample(
            rule,
            label="left",
            closed="left",
        ).agg(OHLCV_AGG)

        result = result.dropna(
            subset=["open", "close"]
        )

        result = add_indicators(result)

        result = result.reset_index().rename(
            columns={"minute": "datetime_utc"}
        )

        result["symbol"] = SYMBOL

        if len(result) != expected_rows:
            raise ValueError(
                f"{freq}: expected {expected_rows} rows, "
                f"got {len(result)}"
            )

        if int(result["trade_count"].sum()) != input_count:
            raise ValueError(
                f"{freq}: trade count mismatch"
            )

        output = higher_path(root, freq)
        save_parquet(result, output)

        print(
            f"OK {freq} | {len(result):,} rows | "
            f"{input_count:,} trades"
        )


# ============================================================
# 7. DATA VALIDATION
# ============================================================

def validate_market(root):
    days = pd.date_range(START_DATE, END_DATE)

    missing_raw = []
    missing_1m = []
    invalid = []

    raw_count = 0
    minute_count = 0
    minute_rows = 0

    for d in days:
        day = d.strftime("%Y-%m-%d")

        raw = raw_path(root, day)
        minute = minute_path(root, day)

        raw_meta = None
        minute_meta = None

        if not valid_parquet(raw):
            missing_raw.append(day)
        else:
            raw_meta = pq.read_metadata(raw)
            raw_count += raw_meta.num_rows

        if not valid_parquet(minute, expected_rows=1440):
            missing_1m.append(day)
        else:
            minute_meta = pq.read_metadata(minute)
            minute_rows += minute_meta.num_rows

            table = pq.read_table(
                minute, columns=["trade_count"]
            )

            count = int(
                table.column("trade_count")
                .to_numpy()
                .sum()
            )

            minute_count += count

            if (
                raw_meta is not None
                and count != raw_meta.num_rows
            ):
                invalid.append(day)

    # Validate aggregated 1h and 1d files
    higher_counts = {}

    for freq, expected in [
        ("1h", len(days) * 24),
        ("1d", len(days)),
    ]:
        path = higher_path(root, freq)

        if not valid_parquet(path, expected_rows=expected):
            invalid.append(f"{freq}_file")
            continue

        table = pq.read_table(
            path, columns=["trade_count"]
        )

        higher_counts[freq] = int(
            table.column("trade_count").to_numpy().sum()
        )

    passed = (
        len(missing_raw) == 0
        and len(missing_1m) == 0
        and len(invalid) == 0
        and raw_count == minute_count
        and higher_counts.get("1h") == raw_count
        and higher_counts.get("1d") == raw_count
    )

    print("\n===== T06 VALIDATION =====")
    print("Days:", len(days))
    print("Missing raw:", len(missing_raw))
    print("Missing 1m:", len(missing_1m))
    print("Invalid:", len(invalid))
    print("Raw trades:", f"{raw_count:,}")
    print("1m trades:", f"{minute_count:,}")
    print("1m rows:", f"{minute_rows:,}")
    print("Higher counts:", higher_counts)
    print("RESULT:", "PASS" if passed else "FAIL")

    if invalid:
        print("Invalid examples:", invalid[:10])

    if missing_raw:
        print("Missing raw examples:", missing_raw[:10])

    if missing_1m:
        print("Missing 1m examples:", missing_1m[:10])

    return passed


# ============================================================
# 8. PIPELINE STATUS
# ============================================================

def show_status(root):
    days = pd.date_range(START_DATE, END_DATE)

    raw_done = 0
    minute_done = 0

    for d in days:
        day = d.strftime("%Y-%m-%d")

        raw_done += int(
            valid_parquet(raw_path(root, day))
        )

        minute_done += int(
            valid_parquet(
                minute_path(root, day),
                expected_rows=1440,
            )
        )

    print("\n===== T06 STATUS =====")
    print("Symbol:", SYMBOL)
    print("Period:", START_DATE, "to", END_DATE)
    print("Expected days:", len(days))
    print("Raw completed:", raw_done)
    print("1m completed:", minute_done)

    for freq in ["1h", "1d"]:
        path = higher_path(root, freq)
        print(
            f"{freq} available:",
            valid_parquet(path)
        )


# ============================================================
# 9. MAIN - SINGLE ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="T06 - Binance ETHUSDT Market Data"
    )

    parser.add_argument(
        "command",
        choices=[
            "status",
            "download",
            "aggregate-1m",
            "aggregate-higher",
            "validate",
        ],
        help="Pipeline action",
    )

    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Existing market data root directory",
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
        "--max-days",
        type=int,
        default=15,
        help="Maximum days per run",
    )

    args = parser.parse_args()

    root = args.root.expanduser()

    if not root.is_dir():
        parser.error(
            f"Data root does not exist: {root}"
        )

    if args.command == "status":
        show_status(root)
        return

    if args.command == "validate":
        if not validate_market(root):
            raise SystemExit(1)
        return

    if args.command == "aggregate-higher":
        aggregate_higher(root)
        return

    if args.max_days < 1:
        parser.error("--max-days must be >= 1")

    if args.start > args.end:
        parser.error("--start must be <= --end")

    if (
        args.start < START_DATE
        or args.end > END_DATE
    ):
        parser.error("Date range outside research period")

    days = pd.date_range(args.start, args.end)

    if args.command == "download":
        pending = [
            d for d in days
            if not valid_parquet(
                raw_path(root, d.strftime("%Y-%m-%d"))
            )
        ]

    else:
        pending = [
            d for d in days
            if not valid_parquet(
                minute_path(root, d.strftime("%Y-%m-%d")),
                expected_rows=1440,
            )
        ]

    print("\n===== T06 MARKET PIPELINE =====")
    print("Command:", args.command)
    print("Market root:", root)
    print("Pending days:", len(pending))

    summary = {
        "success": 0,
        "skipped": 0,
        "failed": 0,
    }

    for d in pending[:args.max_days]:
        day = d.strftime("%Y-%m-%d")

        try:
            if args.command == "download":
                status = download_day(root, day)
            else:
                status = aggregate_day(root, day)

            summary[status] += 1

        except Exception as exc:
            summary["failed"] += 1
            print(f"ERROR {day}: {exc}")

        time.sleep(0.2)

    print("\n===== T06 SUMMARY =====")
    print(summary)

    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
