"""Hoàn thiện bảng T07; xác minh contract độc lập với nhãn thực thể.

Chạy: python T07_Complete_Wallet_Labels.py [--refresh-contracts]
Không suy danh tính của địa chỉ từ bytecode hay volume.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

import pandas as pd

from src.graph_config import read_config, project_path, relative_path


def apply_secondary_labels(df, secondary):
    """Only the human-decision sidecar can add secondary entity identities."""
    if secondary.empty:
        return df
    if secondary.address.duplicated().any() or not secondary.verification_status.eq('human_verified').all():
        raise ValueError('Nhãn bậc hai phải có quyết định người xác minh, không dùng hàng chờ AI')
    if not secondary.source_tier.eq(2).all() or not secondary.source_url.str.startswith('https://').all():
        raise ValueError('Thiếu provenance nguồn bậc hai')
    for column in ['verified_by','confidence','verified_at','label_available_at','effective_from']:
        if not secondary[column].fillna('').astype(str).str.strip().ne('').all():
            raise ValueError('Thiếu metadata xác minh nhãn bậc hai')
    if (pd.to_datetime(secondary.label_available_at,utc=True)<pd.to_datetime(secondary.verified_at,utc=True)).any():
        raise ValueError('Không backdate ngày khả dụng nhãn')
    df=df.copy()
    for row in secondary.itertuples():
        mask=df.address.eq(row.address)
        if not mask.any():
            raise ValueError('Nhãn ngoài tập địa chỉ T07; phải mở rộng universe có kiểm soát')
        previous=df.loc[mask,'entity_type']
        if (~previous.isin(['Unknown','Contract',row.entity_type])).any():
            raise ValueError('Xung đột nhãn hiện có; cần quyết định reconciliation riêng')
        for column in ['entity_name','entity_type','source_url','confidence','verified_by','verified_at','label_available_at','effective_from','source_tier']:
            if column not in df:df[column]=None
            df.loc[mask,column]=getattr(row,column)
        category={'CEX':'exchange','DEX':'defi','Bridge':'bridge','DeFi':'defi'}.get(row.entity_type,'entity')
        df.loc[mask,'class']=category
        df.loc[mask,'public_category']=category
        df.loc[mask,'source']='Human-verified secondary source'
        df.loc[mask,'evidence']='Team member opened source and confirmed Ethereum address; see source_url/verification metadata'
    return df


def fetch_contract_status(addresses, config):
    from google.cloud import bigquery
    cfg = config['bigquery']
    credentials = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    credentials = project_path(credentials or cfg['credentials_file'])
    client = (bigquery.Client.from_service_account_json(str(credentials), project=cfg['project_id'])
              if credentials.is_file() else bigquery.Client(project=cfg['project_id']))
    table = cfg['contracts_table']
    if not all(c.isalnum() or c in '_.-' for c in table):
        raise ValueError('Tên bảng BigQuery không hợp lệ')
    sql = f'''SELECT LOWER(address) AS address, MIN(block_timestamp) AS first_contract_timestamp
              FROM `{table}`
              WHERE block_timestamp < TIMESTAMP(@end_exclusive)
                AND LOWER(address) IN UNNEST(@addresses)
              GROUP BY address'''
    end = str(pd.Timestamp(config['project']['end_date']) + pd.Timedelta(days=1))
    params = [bigquery.ArrayQueryParameter('addresses', 'STRING', sorted(addresses)),
              bigquery.ScalarQueryParameter('end_exclusive', 'STRING', end)]
    dry = client.query(sql, job_config=bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False, query_parameters=params), timeout=60)
    estimate = int(dry.total_bytes_processed or 0)
    print(f'BigQuery dry run: {estimate:,} bytes', flush=True)
    if estimate > cfg['maximum_bytes_billed']:
        raise RuntimeError('Truy vấn vượt giới hạn scan trong config; không chạy truy vấn.')
    job = client.query(sql, job_config=bigquery.QueryJobConfig(
        maximum_bytes_billed=cfg['maximum_bytes_billed'], query_parameters=params), timeout=60)
    found = pd.DataFrame([dict(row) for row in job.result(timeout=240)],
                         columns=['address', 'first_contract_timestamp'])
    result = pd.DataFrame({'address': sorted(addresses)})
    result = result.merge(found, on='address', how='left', validate='one_to_one')
    result['is_contract'] = result['first_contract_timestamp'].notna().astype('boolean')
    result['contract_status_source'] = table
    result['contract_status_checked_at'] = datetime.now(timezone.utc).isoformat()
    result['contract_status_as_of'] = config['project']['end_date']
    result['query_job_id'] = job.job_id
    result['address_set_sha256'] = hashlib.sha256('\n'.join(sorted(addresses)).encode()).hexdigest()
    return result


def complete_labels(config=None, refresh=False, offline=False):
    config = config or read_config()
    data = config['data']
    source = project_path(data['public_labels_parquet'])
    output = project_path(data['processed_labels_parquet'])
    status_path = project_path(data['contract_status_parquet'])
    df = pd.read_parquet(source)
    if not df.address.str.fullmatch(r'0x[0-9a-f]{40}').all() or df.address.duplicated().any():
        raise ValueError('Bảng T07 có địa chỉ sai định dạng hoặc trùng')
    failure = None
    status = None
    if status_path.is_file() and not refresh:
        status = pd.read_parquet(status_path)
        if set(status.address) != set(df.address) or status.address.duplicated().any():
            raise ValueError('Cache contract không khớp toàn bộ tập địa chỉ T07')
        if not status.contract_status_as_of.eq(config['project']['end_date']).all():
            raise ValueError('Cache contract không khớp ngày kết thúc')
    elif not offline:
        try:
            status = fetch_contract_status(df.address.tolist(), config)
            status.to_parquet(status_path, index=False)
        except Exception as exc:
            # Không biến lỗi mạng/quyền truy cập thành kết luận EOA.
            failure = type(exc).__name__ + ': ' + str(exc)[:600]
            print('Contract verification unavailable:', failure, flush=True)
    if status is not None:
        df = df.drop(columns=[c for c in status.columns if c != 'address' and c in df], errors='ignore')
        df = df.merge(status, on='address', how='left', validate='one_to_one')
    else:
        df['is_contract'] = pd.Series(pd.NA, index=df.index, dtype='boolean')
        df['contract_status_source'] = 'Not verified'
        df['contract_status_as_of'] = config['project']['end_date']
    # Contract là nhãn kỹ thuật dự phòng; giữ nguyên nhãn thực thể đã có.
    generic = df.entity_type.eq('Unknown') & df.is_contract.fillna(False)
    df.loc[generic, 'entity_type'] = 'Contract'
    df.loc[generic, 'entity_name'] = 'Unattributed smart contract'
    df.loc[generic, 'source'] = df.loc[generic, 'contract_status_source']
    df.loc[generic, 'evidence'] = 'Address present in BigQuery contracts before study end; identity unknown'
    secondary_path=output.parent/'t07_secondary_verified_labels.parquet'
    if secondary_path.is_file():
        df=apply_secondary_labels(df,pd.read_parquet(secondary_path))
    df['is_zero_address'] = df.address.eq('0x' + '0' * 40)
    df['is_entity_attributed'] = ~df.entity_type.isin(['Unknown', 'Contract'])
    df = df.sort_values('address').reset_index(drop=True)
    df.to_parquet(output, index=False)
    summary = dict(input_file=relative_path(source), output_file=relative_path(output),
                   total_addresses=len(df), contract_status_known=int(df.is_contract.notna().sum()),
                   contracts=int(df.is_contract.fillna(False).sum()),
                   unknown_contract_status=int(df.is_contract.isna().sum()),
                   entity_attributed=int(df.is_entity_attributed.sum()),
                   counts=df.entity_type.value_counts().to_dict(), error=failure,
                   complete=bool(df.is_contract.notna().all()),
                   limitations='Contract means creation recorded before study end, not current bytecode or economic identity.')
    (output.parent / 't07_complete_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return df


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-contracts', action='store_true')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    complete_labels(refresh=args.refresh_contracts, offline=args.offline)
