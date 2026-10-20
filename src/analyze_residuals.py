"""B.7: phần dư, ngày đột biến và bằng chứng chu trình nội giao dịch."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
from src.graph_config import read_config, project_path, resolve_raw


def cycle_diagnostic(netted, output_dir):
    """Loại tuần hoàn trên bản ứng viên riêng; không tự thay đầu vào chính.

    Trừ bottleneck micro-USDT của từng chu trình có hướng theo thứ tự địa chỉ
    xác định. Bảo toàn net balance mỗi nút trong mỗi transaction. Số dư dưới
    ngưỡng cần được báo cáo riêng khi tạo đồ thị ứng viên.
    """
    sizes = netted.groupby('transaction_hash').size()
    candidates = set(sizes[sizes >= 3].index)
    subset = netted.loc[netted.transaction_hash.isin(candidates)]
    amounts = np.rint(netted.amount.to_numpy() * 1_000_000).astype('int64')
    removed = np.zeros(len(netted), dtype='int64')
    cycle_txs = 0
    for tx, sub in subset.groupby('transaction_hash', sort=True):
        # Một chu trình cần mọi đỉnh trên đường đi có cả in và out.
        shared = set(sub.from_address) & set(sub.to_address)
        if len(shared) < 3:
            continue
        graph = nx.DiGraph()
        indices = {}
        for row in sub.sort_values(['from_address', 'to_address']).itertuples():
            graph.add_edge(row.from_address, row.to_address, capacity=int(amounts[row.Index]))
            indices[(row.from_address, row.to_address)] = row.Index
        had_cycle = False
        while True:
            try:
                cycle = nx.find_cycle(graph)
            except nx.NetworkXNoCycle:
                break
            had_cycle = True
            delta = min(graph[u][v]['capacity'] for u, v in cycle)
            for u, v in cycle:
                idx = indices[u, v]
                removed[idx] += delta
                graph[u][v]['capacity'] -= delta
                if graph[u][v]['capacity'] == 0:
                    graph.remove_edge(u, v)
        cycle_txs += int(had_cycle)
    audit = netted[['transaction_hash', 'from_address', 'to_address', 'amount']].copy()
    audit['cycle_removed_usdt'] = removed / 1_000_000
    audit['residual_amount'] = (amounts - removed) / 1_000_000
    audit = audit.loc[removed > 0]
    audit.to_parquet(Path(output_dir) / 't08_multistep_cycle_audit.parquet', index=False)
    # Mỗi transaction phải giữ nguyên net balance trước khi áp lại ngưỡng.
    rem = audit.groupby(['transaction_hash', 'from_address']).cycle_removed_usdt.sum()
    inc = audit.groupby(['transaction_hash', 'to_address']).cycle_removed_usdt.sum()
    imbalance = rem.subtract(inc, fill_value=0)
    max_diff = float(imbalance.abs().max()) if len(imbalance) else 0.0
    return dict(candidate_transactions=len(candidates), transactions_with_cycles=cycle_txs,
                cycle_edge_volume_removed_usdt=float(audit.cycle_removed_usdt.sum()),
                balance_max_abs_diff=max_diff, balance_preserved=bool(max_diff <= 1e-4),
                policy='Diagnostic only; deterministic cycle decomposition is not proof of economic intent.',
                audit_file='t08_multistep_cycle_audit.parquet')


def run_b7_analysis(netted=None, raw=None, labels=None, config=None, output_dir=None):
    config = config or read_config()
    netted = netted if netted is not None else pd.read_parquet(project_path(config['data']['interim_netted_transfers']))
    raw = raw if raw is not None else pd.read_parquet(resolve_raw(config))
    labels = labels if labels is not None else pd.read_parquet(project_path(config['data']['processed_labels_parquet']))
    output_dir = Path(output_dir or project_path(config['data']['processed_graphs_dir']))
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_month = pd.to_datetime(raw.block_timestamp, utc=True).dt.strftime('%Y-%m')
    net_month = pd.to_datetime(netted.block_timestamp, utc=True).dt.strftime('%Y-%m')
    months = pd.period_range(config['project']['start_date'], config['project']['end_date'], freq='M').astype(str)
    monthly = pd.DataFrame({'raw_volume_usdt': raw.groupby(raw_month).amount.sum(),
                            'netted_volume_usdt': netted.groupby(net_month).amount.sum()}).reindex(months).fillna(0)
    monthly['retention_ratio'] = monthly.netted_volume_usdt.div(monthly.raw_volume_usdt.replace(0, np.nan))
    monthly.index.name = 'month'
    monthly.reset_index().to_parquet(output_dir / 't08_monthly_retention.parquet', index=False)
    node_vol = netted.groupby('from_address').amount.sum().add(netted.groupby('to_address').amount.sum(), fill_value=0)
    node_vol = node_vol.rename_axis('address').reset_index(name='volume_usdt').sort_values(['volume_usdt', 'address'], ascending=[False, True])
    total_node = float(node_vol.volume_usdt.sum())
    node_vol['share'] = node_vol.volume_usdt / total_node if total_node else 0.0
    label_cols = ['address', 'entity_name', 'entity_type', 'is_contract', 'contract_status_source']
    top20 = node_vol.head(20).merge(labels[label_cols], on='address', how='left', validate='one_to_one')
    top20['unattributed_entity'] = top20.entity_type.fillna('Unknown').isin(['Unknown', 'Contract'])
    top20.to_parquet(output_dir / 't08_top20_nodes.parquet', index=False)
    daily = netted.groupby('tx_date').amount.sum().sort_values(ascending=False, kind='stable').head(10)
    day_records = []
    for d, volume in daily.items():
        sub = netted.loc[netted.tx_date.eq(d)]
        txs = sub.groupby('transaction_hash').amount.sum().sort_values(ascending=False)
        nodes = sub.groupby('from_address').amount.sum().add(sub.groupby('to_address').amount.sum(), fill_value=0).sort_values(ascending=False)
        top_node = str(nodes.index[0])
        lookup = labels.set_index('address')
        label = str(lookup.loc[top_node, 'entity_type']) if top_node in lookup.index else 'Unknown'
        day_records.append(dict(date=str(d), volume_usdt=float(volume), n_txs=int(sub.transaction_hash.nunique()),
            top_transaction=str(txs.index[0]), top_transaction_volume_usdt=float(txs.iloc[0]),
            top_transaction_share=float(txs.iloc[0] / volume), top_node=top_node,
            top_node_incident_share=float(nodes.iloc[0] / (2*volume)), top_node_type=label,
            explanation=f'Observed concentration: top transaction contributes {txs.iloc[0]/volume:.2%} of edge volume; '
                        f'top node {top_node} ({label}) accounts for {nodes.iloc[0]/(2*volume):.2%} of incident node volume. '
                        'These are measured drivers, not a verified economic cause.'))
    pd.DataFrame(day_records).to_parquet(output_dir / 't08_top10_days.parquet', index=False)
    cycles = cycle_diagnostic(netted, output_dir)
    top10_share = float(node_vol.head(10).share.sum())
    threshold = config['graph']['residual_top10_review_threshold']
    # Cần nhóm quyết định khi concentration vượt ngưỡng, không tự hợp thức hóa dữ liệu.
    review = top10_share >= threshold
    records = json.loads(top20.to_json(orient='records'))
    return dict(monthly_retention=json.loads(monthly.to_json(orient='index')),
                top10_days=day_records, top10_nodes_volume_share=top10_share,
                total_node_volume_usdt=total_node, top20_nodes=records,
                concentration_review_threshold=threshold, multistep_cycles=cycles,
                decision_required=review,
                status='REVIEW_REQUIRED' if review else 'PASS',
                note='Node volume is incoming + outgoing; denominator is twice edge volume. Contract is not entity attribution.')


if __name__ == '__main__':
    print(json.dumps(run_b7_analysis(), ensure_ascii=False, indent=2))
