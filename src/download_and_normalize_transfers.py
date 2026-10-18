"""
Task T05: Script tải và chuẩn hóa dữ liệu Token Transfers từ BigQuery
- Ghi dữ liệu thô vào: data/raw/
- Ghi dữ liệu đã chuẩn hóa vào: data/interim/
- Hỗ trợ chạy lại nhiều lần (idempotent / reproducible)
"""

import os
import sys
import pandas as pd
from google.cloud import bigquery
from google.auth.exceptions import DefaultCredentialsError

# Lấy Project ID từ biến môi trường GCP_PROJECT_ID, nếu không có thì để None để BigQuery tự lấy từ gcloud CLI config
PROJECT_ID = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or None
CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")

# Định nghĩa token: USDT (Tether)
TOKEN_ADDRESS = "0xdac17f958d2ee523a2206206994597c13d831ec7"
TOKEN_DECIMALS = 6
TOKEN_SYMBOL = "USDT"

# Khung thời gian: Từ tháng 01/2025
START_DATE = "2025-01-01"
END_DATE = "2026-10-18"

# Thư mục lưu trữ theo chuẩn Task T05
RAW_DIR = os.path.join("data", "raw")
INTERIM_DIR = os.path.join("data", "interim")
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(INTERIM_DIR, exist_ok=True)


def get_client(project_id: str = PROJECT_ID):
    if CREDENTIALS_FILE and os.path.exists(CREDENTIALS_FILE):
        return bigquery.Client.from_service_account_json(CREDENTIALS_FILE, project=project_id)
    try:
        # Nếu project_id là None, Client sẽ tự động phát hiện project cấu hình trong `gcloud config set project`
        return bigquery.Client(project=project_id)
    except DefaultCredentialsError:
        print("[!] Auth error: Application Default Credentials not configured.")
        print("    Vui lòng chạy: gcloud auth application-default login")
        print("    Hoặc đặt biến môi trường GCP_PROJECT_ID trong file .env")
        sys.exit(1)


def build_whale_transfers_query(
    token_address: str,
    start_date: str,
    end_date: str,
    min_amount_tokens: float = 500000.0,
    limit: int = 50000
):
    """
    Query transfers của cá voi (Whale Transfers) trực tiếp từ BigQuery.
    - Lọc theo partition block_timestamp
    - Lọc theo token contract address
    - Lọc giá trị chuyển khoản lớn (>= 500,000 token) để lấy mạng lưới cá voi
    """
    raw_min_value = int(min_amount_tokens * (10 ** TOKEN_DECIMALS))
    query = f"""
        SELECT
            token_address,
            from_address,
            to_address,
            value,
            transaction_hash,
            log_index,
            block_timestamp,
            block_number
        FROM
            `bigquery-public-data.crypto_ethereum.token_transfers`
        WHERE
            block_timestamp >= TIMESTAMP('{start_date}')
            AND block_timestamp <= TIMESTAMP('{end_date}')
            AND LOWER(token_address) = LOWER('{token_address}')
            AND SAFE_CAST(value AS NUMERIC) >= {raw_min_value}
        ORDER BY
            block_timestamp DESC
        LIMIT {limit}
    """
    return query


def dry_run_query(client: bigquery.Client, query: str):
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    query_job = client.query(query, job_config=job_config)
    gb_scanned = query_job.total_bytes_processed / (1024 ** 3)
    print(f"[*] Estimated scan size: {gb_scanned:.2f} GB")
    return gb_scanned


def fetch_raw_transfers(client: bigquery.Client, query: str, output_path: str):
    dry_run_query(client, query)
    print(f"[*] Fetching whale token transfers for {TOKEN_SYMBOL}...")
    query_job = client.query(query)
    df = query_job.to_dataframe()
    print(f"[+] Downloaded {len(df)} raw transfer records.")
    
    # Lưu vào data/raw/
    df.to_parquet(output_path.replace(".csv", ".parquet"), index=False)
    df.to_csv(output_path, index=False)
    print(f"[+] Saved raw data to: {output_path}")
    return df


def normalize_transfers(df_raw: pd.DataFrame, output_path: str):
    """
    Chuẩn hóa dữ liệu sang data/interim/:
    - Đổi kiểu datetime chuẩn UTC
    - Chuyển đổi 'value' từ raw hex/integer sang số lượng token thực tế (chia decimals)
    - Chuẩn hóa địa chỉ ví về chữ thường (lowercase)
    - Loại bỏ giao dịch trùng lặp (nếu có)
    - Trích xuất thêm các đặc trưng thời gian (tx_date, tx_hour)
    """
    print("[*] Normalizing data for data/interim/...")
    df = df_raw.copy()

    # 1. Chuẩn hóa địa chỉ ví
    df['from_address'] = df['from_address'].astype(str).str.lower().str.strip()
    df['to_address'] = df['to_address'].astype(str).str.lower().str.strip()
    df['token_address'] = df['token_address'].astype(str).str.lower().str.strip()

    # 2. Chuẩn hóa số lượng token thực tế
    df['value_raw'] = pd.to_numeric(df['value'], errors='coerce')
    df['amount'] = df['value_raw'] / (10 ** TOKEN_DECIMALS)

    # 3. Chuẩn hóa thời gian
    df['block_timestamp'] = pd.to_datetime(df['block_timestamp'], utc=True)
    df['tx_date'] = df['block_timestamp'].dt.date
    df['tx_hour'] = df['block_timestamp'].dt.hour

    # 4. Loại bỏ duplicates nếu có
    df = df.drop_duplicates(subset=['transaction_hash', 'log_index'])

    # Sắp xếp theo thứ tự thời gian tăng dần
    df = df.sort_values(by='block_timestamp', ascending=True).reset_index(drop=True)

    # 5. Lưu vào data/interim/
    parquet_path = output_path.replace(".csv", ".parquet")
    df.to_parquet(parquet_path, index=False)
    df.to_csv(output_path, index=False)
    print(f"[+] Cleaned {len(df)} records.")
    print(f"[+] Saved normalized data to: {output_path} and {parquet_path}")
    return df


def main():
    client = get_client(PROJECT_ID)
    
    raw_csv = os.path.join(RAW_DIR, f"{TOKEN_SYMBOL.lower()}_whale_transfers_raw.csv")
    interim_csv = os.path.join(INTERIM_DIR, f"{TOKEN_SYMBOL.lower()}_whale_transfers_interim.csv")

    query = build_whale_transfers_query(
        token_address=TOKEN_ADDRESS,
        start_date=START_DATE,
        end_date=END_DATE,
        min_amount_tokens=500000.0,
        limit=20000
    )

    df_raw = fetch_raw_transfers(client, query, raw_csv)
    df_interim = normalize_transfers(df_raw, interim_csv)
    
    print("\n--- Summary of Normalized Whale Data ---")
    print(f"Total Whale Transfers: {len(df_interim)}")
    print(f"Unique Senders (Whales/DEXs/CEXs): {df_interim['from_address'].nunique()}")
    print(f"Unique Receivers: {df_interim['to_address'].nunique()}")
    print(f"Total Transferred Volume: {df_interim['amount'].sum():,.2f} {TOKEN_SYMBOL}")
    print("\nSample records:")
    print(df_interim[['block_timestamp', 'from_address', 'to_address', 'amount']].head(5))


if __name__ == "__main__":
    main()

