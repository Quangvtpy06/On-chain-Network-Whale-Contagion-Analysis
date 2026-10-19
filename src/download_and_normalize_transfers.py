"""
Task T05: Script tải và chuẩn hóa dữ liệu Token Transfers từ BigQuery
- Kiến trúc lưu trữ:
    + Dữ liệu thô (Raw Data): Lưu theo từng ngày (daily parquet):
      data/raw/daily/usdt_raw_YYYY-MM-DD.parquet
    + Dữ liệu chuẩn hóa (Interim Data): Tự động gộp thành 1 file parquet tổng hợp:
      data/interim/usdt_whale_transfers_interim.parquet
- Tính năng thông minh (Automation & Idempotent):
    + Tự động kiểm tra file ngày nào đã có thì BỎ QUA (Skip), không query lại giúp tiết kiệm quota BigQuery Sandbox.
    + Chỉ query tải về các ngày mới / chưa có dữ liệu.
    + END_DATE tự động lấy theo ngày hiện tại (máy chạy tới đâu update tới ngày nộp bài tới đó).
    + Đã loại bỏ hoàn toàn LIMIT để lấy đầy đủ toàn bộ giao dịch cá voi (>= 500k USDT).
"""

import os
import sys
import glob
from datetime import datetime, timedelta, date

# Fix encoding cho Windows terminal (cp1252 -> utf-8)
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Tự động load biến môi trường từ file .env (nếu có)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Nếu chưa cài python-dotenv thì bỏ qua, dùng biến môi trường hệ thống

import pandas as pd
from google.cloud import bigquery
from google.auth.exceptions import DefaultCredentialsError

# 1. Config GCP Project ID & Credentials
PROJECT_ID = os.getenv("GCP_PROJECT_ID") or "whale-network"
CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "whale-network-4a41a91fd701.json")

# Token: USDT (Tether USD ERC-20)
TOKEN_ADDRESS = "0xdac17f958d2ee523a2206206994597c13d831ec7"
TOKEN_DECIMALS = 6
TOKEN_SYMBOL = "USDT"
MIN_WHALE_AMOUNT = 500000.0  # 500k USD

# Khung thời gian cố định: Từ 01/01/2025 tới 17/10/2026 (Chốt dữ liệu nghiên cứu)
START_DATE_STR = "2025-01-01"
END_DATE_STR = "2026-10-17"

# Thư mục lưu trữ
RAW_DAILY_DIR = os.path.join("data", "raw", "daily")
INTERIM_DIR = os.path.join("data", "interim")
os.makedirs(RAW_DAILY_DIR, exist_ok=True)
os.makedirs(INTERIM_DIR, exist_ok=True)


def get_client(project_id: str = PROJECT_ID) -> bigquery.Client:
    if CREDENTIALS_FILE and os.path.exists(CREDENTIALS_FILE):
        print(f"[*] Xác thực bằng Service Account: {CREDENTIALS_FILE}")
        return bigquery.Client.from_service_account_json(CREDENTIALS_FILE, project=project_id)
    try:
        print("[*] Xác thực bằng Application Default Credentials...")
        return bigquery.Client(project=project_id)
    except DefaultCredentialsError:
        print("[!] Auth error: Application Default Credentials not configured.")
        print("    Vui lòng chạy: gcloud auth application-default login")
        print("    Hoặc đặt biến môi trường GCP_PROJECT_ID trong file .env")
        sys.exit(1)


def build_daily_query(target_date: str, token_address: str, min_amount_tokens: float = MIN_WHALE_AMOUNT) -> str:
    """
    Query toàn bộ whale transfers trong 1 ngày cụ thể (00:00:00 đến 23:59:59 UTC).
    - Tối ưu quota: Bỏ block_number và token_address khỏi SELECT (tiết kiệm dung lượng scan cột).
    - Giữ lại log_index để phân biệt chính xác các event transfer trong cùng 1 transaction hash.
    """
    raw_min_value = int(min_amount_tokens * (10 ** TOKEN_DECIMALS))
    start_ts = f"{target_date} 00:00:00"
    end_ts = f"{target_date} 23:59:59"
    
    query = f"""
        SELECT
            from_address,
            to_address,
            value,
            transaction_hash,
            log_index,
            block_timestamp
        FROM
            `bigquery-public-data.crypto_ethereum.token_transfers`
        WHERE
            block_timestamp >= TIMESTAMP('{start_ts}')
            AND block_timestamp <= TIMESTAMP('{end_ts}')
            AND LOWER(token_address) = LOWER('{token_address}')
            AND SAFE_CAST(value AS NUMERIC) >= {raw_min_value}
        ORDER BY
            block_timestamp ASC
    """
    return query


def fetch_and_save_daily_raw(client: bigquery.Client, target_date: str) -> str:
    """
    Tải dữ liệu thô 1 ngày và lưu dưới dạng raw parquet.
    """
    raw_parquet_path = os.path.join(RAW_DAILY_DIR, f"{TOKEN_SYMBOL.lower()}_raw_{target_date}.parquet")
    
    if os.path.exists(raw_parquet_path):
        return raw_parquet_path

    query = build_daily_query(target_date, TOKEN_ADDRESS, MIN_WHALE_AMOUNT)
    query_job = client.query(query)
    df = query_job.to_dataframe()

    # Lưu định dạng parquet
    df.to_parquet(raw_parquet_path, index=False)
    print(f"    [+] Ngày {target_date}: Tải thành công {len(df)} transfers cá voi -> {raw_parquet_path}")
    return raw_parquet_path


def generate_date_range(start_date_str: str, end_date_str: str):
    start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    curr = start
    while curr <= end:
        yield curr.strftime("%Y-%m-%d")
        curr += timedelta(days=1)


def normalize_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Chuẩn hóa dữ liệu thô:
    - Địa chỉ lowercase
    - Thêm token_address và token_symbol (không cần tốn quota BigQuery để scan)
    - Chia decimals ra amount
    - UTC timestamp, tx_date, tx_hour
    - Loại bỏ duplicates subset ['transaction_hash', 'log_index']
    """
    if df_raw.empty:
        return pd.DataFrame()

    df = df_raw.copy()
    df['from_address'] = df['from_address'].astype(str).str.lower().str.strip()
    df['to_address'] = df['to_address'].astype(str).str.lower().str.strip()
    df['token_address'] = TOKEN_ADDRESS.lower()
    df['token_symbol'] = TOKEN_SYMBOL

    df['value_raw'] = pd.to_numeric(df['value'], errors='coerce')
    df['amount'] = df['value_raw'] / (10 ** TOKEN_DECIMALS)

    df['block_timestamp'] = pd.to_datetime(df['block_timestamp'], utc=True)
    df['tx_date'] = df['block_timestamp'].dt.date
    df['tx_hour'] = df['block_timestamp'].dt.hour

    df = df.drop_duplicates(subset=['transaction_hash', 'log_index'])
    return df


def sync_all_and_build_interim(client: bigquery.Client, start_date_str: str = START_DATE_STR, end_date_str: str = END_DATE_STR):
    """
    Quá trình đồng bộ dữ liệu chốt cố định:
    1. Quét danh sách các ngày từ START_DATE đến END_DATE_STR (17/10/2026).
    2. Chỉ tải các ngày chưa có file parquet trong data/raw/daily/.
    3. Hợp nhất tất cả các ngày và chuẩn hóa vào duy nhất 1 file parquet trong data/interim/.
    """
    if end_date_str is None:
        end_date_str = END_DATE_STR

    print(f"=== BẮT ĐẦU ĐỒNG BỘ DỮ LIỆU TỪ {start_date_str} ĐẾN {end_date_str} ===")
    
    all_dates = list(generate_date_range(start_date_str, end_date_str))
    missing_dates = []

    for d in all_dates:
        p = os.path.join(RAW_DAILY_DIR, f"{TOKEN_SYMBOL.lower()}_raw_{d}.parquet")
        if not os.path.exists(p):
            missing_dates.append(d)

    print(f"[*] Tổng số ngày trong phạm vi: {len(all_dates)} ngày.")
    print(f"[*] Số ngày đã tải trước đó: {len(all_dates) - len(missing_dates)} ngày.")
    print(f"[*] Số ngày mới cần tải thêm: {len(missing_dates)} ngày.")

    # Tải các ngày còn thiếu
    if missing_dates:
        print(f"[*] Đang tải dữ liệu cho {len(missing_dates)} ngày mới...")
        for idx, target_date in enumerate(missing_dates, 1):
            print(f"  [{idx}/{len(missing_dates)}] Đang xử lý ngày {target_date}...")
            try:
                fetch_and_save_daily_raw(client, target_date)
            except Exception as e:
                print(f"    [!] Lỗi khi tải ngày {target_date}: {e}")
    else:
        print("[+] Toàn bộ dữ liệu raw đã đầy đủ cập nhật tới hôm nay!")

    # 4. Gộp toàn bộ các file raw daily và chuẩn hóa thành 1 file parquet duy nhất trong data/interim
    print("\n[*] Đang tổng hợp và chuẩn hóa tất cả các ngày vào 1 file interim parquet...")
    daily_files = sorted(glob.glob(os.path.join(RAW_DAILY_DIR, f"{TOKEN_SYMBOL.lower()}_raw_*.parquet")))
    
    if not daily_files:
        print("[!] Không tìm thấy file raw nào để tổng hợp.")
        return

    dfs = []
    for f in daily_files:
        try:
            df_day = pd.read_parquet(f)
            if not df_day.empty:
                dfs.append(df_day)
        except Exception as e:
            print(f"[!] Lỗi đọc file {f}: {e}")

    if dfs:
        df_combined_raw = pd.concat(dfs, ignore_index=True)
        print(f"[*] Tổng số bản ghi raw thu thập được: {len(df_combined_raw)} dòng.")
        
        df_interim = normalize_dataframe(df_combined_raw)
        df_interim = df_interim.sort_values(by='block_timestamp', ascending=True).reset_index(drop=True)
        
        interim_parquet_path = os.path.join(INTERIM_DIR, f"{TOKEN_SYMBOL.lower()}_whale_transfers_interim.parquet")
        df_interim.to_parquet(interim_parquet_path, index=False)
        
        print(f"\n[+] ĐÃ HOÀN THÀNH CHUẨN HÓA VÀO 1 FILE PARQUET DUY NHẤT!")
        print(f"    File: {interim_parquet_path}")
        print(f"    Tổng số giao dịch cá voi chuẩn hóa: {len(df_interim):,} dòng.")
        print(f"    Số ngày thực tế có dữ liệu: {df_interim['tx_date'].nunique()} ngày.")
        print(f"    Thời gian giao dịch: từ {df_interim['block_timestamp'].min()} đến {df_interim['block_timestamp'].max()}")
        print(f"    Tổng volume luân chuyển: {df_interim['amount'].sum():,.2f} {TOKEN_SYMBOL}")
        print(f"    Unique Senders: {df_interim['from_address'].nunique():,}")
        print(f"    Unique Receivers: {df_interim['to_address'].nunique():,}")


def main():
    client = get_client()
    sync_all_and_build_interim(client)


if __name__ == "__main__":
    main()
