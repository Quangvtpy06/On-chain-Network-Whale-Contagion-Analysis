"""Gộp theo (transaction_hash, cặp ví vô hướng), tính USDT bằng đơn vị micro."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from src.graph_config import ROOT, read_config, project_path, resolve_raw

ZERO_ADDRESS = '0x' + '0' * 40
DEFAULT_RAW_INTERIM = 'data/interim/usdt_whale_transfers_interim.parquet'
DEFAULT_NETTED_OUTPUT = ROOT / 'data/interim/usdt_transfers_netted.parquet'
DEFAULT_MIN_THRESHOLD = 500_000.0


def normalize_transfers(df):
    df = df.copy()
    required = {'transaction_hash', 'from_address', 'to_address', 'amount', 'block_timestamp'}
    if required - set(df):
        raise ValueError(f'Thiếu cột: {sorted(required-set(df))}')
    for col in ['from_address', 'to_address']:
        df[col] = df[col].astype('string').str.strip().str.lower()
        if not df[col].str.fullmatch(r'0x[0-9a-f]{40}').fillna(False).all():
            raise ValueError(f'Địa chỉ không hợp lệ: {col}')
    df['transaction_hash'] = df.transaction_hash.astype('string').str.lower()
    if df.transaction_hash.isna().any():
        raise ValueError('Thiếu transaction_hash')
    df['amount'] = pd.to_numeric(df.amount, errors='raise').astype(float)
    if not np.isfinite(df.amount).all() or (df.amount < 0).any():
        raise ValueError('Amount không hợp lệ')
    df['block_timestamp'] = pd.to_datetime(df.block_timestamp, utc=True, errors='raise')
    if df.block_timestamp.isna().any():
        raise ValueError('Timestamp bị thiếu')
    if df.groupby('transaction_hash').block_timestamp.nunique().gt(1).any():
        raise ValueError('Một transaction có nhiều block_timestamp')
    # Luôn tính lại cửa sổ UTC; đối chiếu cột nguồn riêng trong validation.
    df['tx_date'] = df.block_timestamp.dt.date
    df['tx_week'] = df.block_timestamp.dt.strftime('%G-W%V')
    df['tx_hour'] = df.block_timestamp.dt.hour
    df['is_zero_address'] = df.from_address.eq(ZERO_ADDRESS) | df.to_address.eq(ZERO_ADDRESS)
    return df


def net_pairs_in_transaction(df, threshold=DEFAULT_MIN_THRESHOLD):
    """Hàm production dùng chung cho pipeline và pytest. Giữ gross của cặp còn lại.

    Cặp triệt tiêu/bị ngưỡng loại không có cạnh; gross của chúng nằm trong đối soát
    toàn kỳ, không thể gắn một cách tùy ý vào cạnh sống sót.
    """
    if threshold < 0:
        raise ValueError('Threshold phải không âm')
    df = normalize_transfers(df)
    if 'log_index' in df and df.duplicated(['transaction_hash', 'log_index']).any():
        raise ValueError('Trùng (transaction_hash, log_index)')
    df = df.loc[df.from_address.ne(df.to_address)].copy()
    forward = df.from_address.lt(df.to_address)
    df['u'] = df.from_address.where(forward, df.to_address)
    df['v'] = df.to_address.where(forward, df.from_address)
    micro = np.rint(df.amount.to_numpy() * 1_000_000)
    if (micro >= np.iinfo(np.int64).max).any():
        raise ValueError('Amount vượt giới hạn micro-USDT int64')
    units = micro.astype('int64')
    df['signed_micro'] = np.where(forward, units, -units)
    pairs = df.groupby(['transaction_hash', 'u', 'v'], as_index=False, sort=True).agg(
        net_micro=('signed_micro', 'sum'), gross_amount=('amount', 'sum'),
        event_count=('amount', 'size'), block_timestamp=('block_timestamp', 'min'))
    pairs['amount'] = pairs.net_micro.abs() / 1_000_000
    pairs = pairs.loc[(pairs.amount > 0) & (pairs.amount >= threshold)].copy()
    positive = pairs.net_micro.gt(0)
    pairs['from_address'] = pairs.u.where(positive, pairs.v)
    pairs['to_address'] = pairs.v.where(positive, pairs.u)
    pairs['tx_date'] = pairs.block_timestamp.dt.date
    pairs['tx_week'] = pairs.block_timestamp.dt.strftime('%G-W%V')
    pairs['tx_hour'] = pairs.block_timestamp.dt.hour
    pairs['is_zero_address'] = pairs.from_address.eq(ZERO_ADDRESS) | pairs.to_address.eq(ZERO_ADDRESS)
    pairs = pairs.drop(columns=['u', 'v', 'net_micro'])
    return pairs.sort_values(['block_timestamp', 'transaction_hash', 'from_address', 'to_address']).reset_index(drop=True)


def run_transfer_netting(input_path_or_rel=None, output_path=None, min_threshold=None, save_parquet=True):
    config = read_config()
    source = project_path(input_path_or_rel) if input_path_or_rel else resolve_raw(config)
    if not source.is_file():
        source = resolve_raw(config)
    output = Path(output_path) if output_path else project_path(config['data']['interim_netted_transfers'])
    threshold = min_threshold if min_threshold is not None else config['graph']['min_edge_threshold_usdt']
    raw = pd.read_parquet(source)
    result = net_pairs_in_transaction(raw, threshold)
    normalized = normalize_transfers(raw)
    loops = normalized.from_address.eq(normalized.to_address)
    stats = dict(raw_events=len(raw), raw_unique_txs=int(raw.transaction_hash.nunique()),
                 raw_volume_usdt=float(raw.amount.sum()), netted_rows=len(result),
                 netted_volume_usdt=float(result.amount.sum()),
                 self_loops_count=int(loops.sum()), self_loops_volume_usdt=float(raw.loc[loops, 'amount'].sum()),
                 zero_address_count=int(result.is_zero_address.sum()), min_threshold_usdt=threshold)
    if save_parquet:
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(output, index=False)
        output.with_suffix('.summary.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')
    print(f"Netting: {len(raw):,} -> {len(result):,} rows; volume={result.amount.sum():,.2f}", flush=True)
    return result, stats


if __name__ == '__main__':
    run_transfer_netting()
