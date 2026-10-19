import os
import sys
from google.cloud import bigquery
from google.auth.exceptions import DefaultCredentialsError

# 1. Config
# Lấy Project ID từ biến môi trường hoặc mặc định 'whale-network'
PROJECT_ID = os.getenv("GCP_PROJECT_ID") or "whale-network"
CREDENTIALS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "whale-network-4a41a91fd701.json")

def get_bigquery_client(project_id: str = PROJECT_ID):
    if CREDENTIALS_FILE and os.path.exists(CREDENTIALS_FILE):
        print(f"[*] Using service account file: {CREDENTIALS_FILE}")
        return bigquery.Client.from_service_account_json(CREDENTIALS_FILE, project=project_id)
    
    try:
        print("[*] Using Application Default Credentials...")
        return bigquery.Client(project=project_id)
    except DefaultCredentialsError:
        print("\n[!] AUTH ERROR: Application Default Credentials not found.")
        print("    Vui lòng chạy: gcloud auth application-default login")
        print("    Hoặc đặt biến môi trường GCP_PROJECT_ID trong file .env")
        sys.exit(1)

# 2. Time range: from 2025-01-01 to 2026-10-17 (Chốt dữ liệu nghiên cứu)
START_DATE = "2025-01-01"
END_DATE = "2026-10-17"

# 3. Query daily transactions aggregation (Partition optimized)
# Note: In BigQuery SQL, `hash` is a reserved keyword, so it should be backticked: `hash`
QUERY_AGGREGATED = f"""
    SELECT
        DATE(block_timestamp) AS tx_date,
        COUNT(`hash`) AS total_transactions,
        ROUND(SUM(value / 1e18), 4) AS total_eth_volume,
        ROUND(AVG(gas_price / 1e9), 2) AS avg_gas_gwei
    FROM
        `bigquery-public-data.crypto_ethereum.transactions`
    WHERE
        block_timestamp >= TIMESTAMP('2025-01-01')
        AND block_timestamp <= TIMESTAMP("2026-10-18")
        AND receipt_status = 1
    GROUP BY
        tx_date
    ORDER BY
        tx_date DESC
"""

def estimate_query_cost(client: bigquery.Client, query: str):
    """Dry run to check scan size before running."""
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    query_job = client.query(query, job_config=job_config)
    gb_scanned = query_job.total_bytes_processed / (1024**3)
    print(f"[*] Estimated bytes scanned: {gb_scanned:.2f} GB")
    return gb_scanned

def fetch_data(client: bigquery.Client, query: str, output_csv="ethereum_data.csv"):
    gb_scanned = estimate_query_cost(client, query)

    if gb_scanned > 200:
        print(f"[!] Warning: Query scans {gb_scanned:.2f} GB.")

    print("[*] Executing query...")
    query_job = client.query(query)
    df = query_job.to_dataframe()

    print(f"[+] Successfully fetched {len(df)} rows!")
    df.to_csv(output_csv, index=False)
    print(f"[+] Saved to: {output_csv}")
    return df

if __name__ == "__main__":
    client = get_bigquery_client(PROJECT_ID)
    print(f"[*] Querying from {START_DATE} to {END_DATE}...")
    df = fetch_data(client, QUERY_AGGREGATED, output_csv="eth_stats_from_2025.csv")
    print(df.head())
