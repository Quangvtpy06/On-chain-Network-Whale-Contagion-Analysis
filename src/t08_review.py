"""Review độc lập: không import thuật toán production của T07/T08.

Chạy thành tiến trình riêng, dựng kết quả tham chiếu bằng tổng có hướng rồi
trừ bảng đảo chiều (khác phép canonical signed group của production).
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def review(output, input_path, labels_path):
    cfg = yaml.safe_load((ROOT/'config/config.yaml').read_text(encoding='utf-8'))
    local = ROOT/cfg['data']['interim_raw_transfers']
    candidates = [local]
    repo = cfg['huggingface']['repo_id'].replace('/', '--')
    candidates += sorted((Path.home()/f'.cache/huggingface/hub/datasets--{repo}/snapshots').glob('*/'+cfg['data']['interim_raw_transfers']+'*'))
    source = next(p for p in candidates if p.is_file() and p.stat().st_size > 2048)
    raw = pd.read_parquet(source, columns=['transaction_hash', 'log_index', 'from_address', 'to_address', 'amount', 'block_timestamp'])
    for col in ['transaction_hash', 'from_address', 'to_address']:
        raw[col] = raw[col].astype('string')
    assert not raw.duplicated(['transaction_hash', 'log_index']).any()
    for col in ['from_address', 'to_address']:
        assert raw[col].str.fullmatch(r'0x[0-9a-f]{40}').all()
    raw = raw.loc[raw.from_address.ne(raw.to_address)].copy()
    raw['micro'] = np.rint(raw.amount*1_000_000).astype('int64')
    keys = ['transaction_hash', 'from_address', 'to_address']
    directed = raw.groupby(keys, as_index=False).micro.sum()
    reverse = directed.rename(columns={'from_address':'to_address', 'to_address':'from_address', 'micro':'reverse_micro'})
    reverse['reverse_micro'] = reverse.reverse_micro.astype('Int64')
    expected = directed.merge(reverse, on=keys, how='left').fillna({'reverse_micro':0})
    expected['net'] = expected.micro - expected.reverse_micro
    expected = expected.loc[expected.net.ge(cfg['graph']['min_edge_threshold_usdt']*1_000_000) & expected.net.gt(0)]
    netted = pd.read_parquet(input_path)
    expected_values = expected.set_index(keys).net.sort_index()/1_000_000
    actual_values = netted.set_index(keys).amount.sort_index()
    assert expected_values.index.equals(actual_values.index), 'Netting key mismatch'
    assert np.allclose(expected_values, actual_values, rtol=0, atol=1e-6), 'Netting values mismatch'
    timestamp_map = raw.groupby('transaction_hash').block_timestamp.first()
    expected_ts = netted.transaction_hash.map(timestamp_map)
    assert netted.block_timestamp.eq(expected_ts).all(), 'Netted timestamp mismatch'
    labels = pd.read_parquet(labels_path)
    assert labels.address.is_unique
    assert set(netted.from_address).union(netted.to_address) <= set(labels.address)
    contract_complete = bool(labels.is_contract.notna().all())
    netted['date'] = pd.to_datetime(netted.block_timestamp, utc=True).dt.strftime('%Y-%m-%d')
    netted['week'] = pd.to_datetime(netted.block_timestamp, utc=True).dt.strftime('%G-W%V')
    results = dict(netting_reference_rows=len(expected), netting_reference_pass=True, label_coverage_pass=True,
                   contract_status_complete=contract_complete)
    for window, col in [('daily', 'date'), ('weekly', 'week')]:
        edges = pd.read_parquet(output/f'dynamic_edges_{window}.parquet')
        group = netted.groupby([col, 'from_address', 'to_address'])
        reference = group.agg(total_value=('amount','sum'), transaction_count=('transaction_hash','nunique'),
            min_value=('amount','min'), max_value=('amount','max'), gross_value=('gross_amount','sum'), event_count=('event_count','sum')).sort_index()
        actual = edges.set_index(['time_window','from_address','to_address']).sort_index()
        assert reference.index.equals(actual.index), f'{window} edge keys'
        for metric in reference:
            assert np.allclose(reference[metric], actual[metric], rtol=1e-12, atol=1e-4), f'{window} {metric}'
        assert np.allclose(actual.mean_value, actual.total_value/actual.transaction_count), f'{window} mean_value'
        metrics = pd.read_parquet(output/f'graph_metrics_{window}.parquet')
        calendar = pd.date_range(cfg['project']['start_date'], cfg['project']['end_date'])
        windows = sorted(set(calendar.strftime('%G-W%V'))) if window == 'weekly' else calendar.strftime('%Y-%m-%d').tolist()
        assert metrics.time_window.tolist() == windows
        volumes = netted.groupby(col).amount.sum().reindex(windows, fill_value=0)
        assert np.allclose(metrics.total_volume_usdt, volumes, rtol=1e-12, atol=1e-4)
        if window == 'weekly':
            days = pd.Series(calendar.strftime('%G-W%V')).value_counts()
            assert metrics.days_in_window.eq(metrics.time_window.map(days)).all()
            assert metrics.eligible_for_regression.eq(metrics.days_in_window.eq(7)).all()
        # Tham chiếu topology độc lập bằng scipy sparse trên toàn bộ snapshots.
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        for w, sub in edges.groupby('time_window'):
            nodes = sorted(set(sub.from_address) | set(sub.to_address))
            lookup = {n:i for i,n in enumerate(nodes)}
            a = sub.from_address.map(lookup).to_numpy(); b = sub.to_address.map(lookup).to_numpy()
            matrix = coo_matrix((np.ones(len(a)),(a,b)), shape=(len(nodes),len(nodes))).tocsr()
            row = metrics.loc[metrics.time_window.eq(w)].iloc[0]
            assert row.num_nodes == len(nodes) and row.num_edges == len(sub)
            assert row.num_strongly_connected_components == connected_components(matrix, directed=True, connection='strong', return_labels=False)
            assert row.num_weakly_connected_components == connected_components(matrix, directed=True, connection='weak', return_labels=False)
            reciprocal = matrix.multiply(matrix.T).sum()/len(sub)
            assert np.isclose(row.reciprocity, reciprocal)
            assert np.isclose(row.density, len(sub)/(len(nodes)*(len(nodes)-1)))
            incident = np.zeros(len(nodes))
            np.add.at(incident, a, sub.total_value.to_numpy())
            np.add.at(incident, b, sub.total_value.to_numpy())
            shares = incident / incident.sum()
            assert np.isclose(row.top10_volume_share, np.sort(shares)[-10:].sum())
            assert np.isclose(row.hhi_volume, np.square(shares).sum())
            # Gini theo diện tích Lorenz, khác công thức chỉ số của production.
            lorenz = np.r_[0.0, np.cumsum(np.sort(shares))]
            reference_gini = 1 - (lorenz[:-1]+lorenz[1:]).sum()/len(nodes)
            assert np.isclose(row.gini_volume, reference_gini, atol=1e-12)
        results[window+'_edge_reference_pass'] = True
        results[window+'_topology_reference_pass'] = True
    manifest = json.loads((output/'t08_reproducibility.json').read_text())
    assert manifest['all_match']
    # Kiểm tra hash raw không thay đổi từ lần pipeline đầu.
    digest=hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):
            digest.update(chunk)
    summary=json.loads((output/'t08_summary.json').read_text(encoding='utf-8'))
    assert digest.hexdigest()==summary['netting_results']['raw_sha256']
    results['raw_unchanged'] = True
    results['status']='PASS'
    results['scope']='Independent computational review; contract completeness reported separately in B.5; no team sign-off implied.'
    (output/'t08_independent_review.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--labels', type=Path, required=True)
    args=parser.parse_args()
    try:
        review(args.output,args.input,args.labels)
    except Exception as exc:
        (args.output/'t08_independent_review.json').write_text(json.dumps({'status':'FAIL','error':str(exc)}),encoding='utf-8')
        raise
