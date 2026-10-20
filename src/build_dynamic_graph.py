"""Đồ thị cá voi USDT trên dòng tiền đã net theo giao dịch và cặp ví.

Cửa sổ ngày và tuần ISO bắt đầu thứ Hai theo UTC, bao gồm snapshot rỗng.
"""
from datetime import date, timedelta
from pathlib import Path
import webbrowser
import numpy as np
import pandas as pd
import networkx as nx
from src.graph_config import ROOT, read_config, project_path
from src.net_transfers import normalize_transfers, ZERO_ADDRESS

PROJECT_ROOT = ROOT
CONFIG = read_config()
DEFAULT_INPUT_PARQUET = project_path(CONFIG['data']['interim_netted_transfers'])
DEFAULT_OUTPUT_DIR = project_path(CONFIG['data']['processed_graphs_dir'])
DEFAULT_LABELS_PARQUET = project_path(CONFIG['data']['processed_labels_parquet'])


def load_netted_transfers(path):
    data = normalize_transfers(pd.read_parquet(path))
    for col in ['gross_amount', 'event_count']:
        if col not in data:
            raise ValueError(f'Thiếu provenance netting: {col}')
    if data.duplicated(['transaction_hash', 'from_address', 'to_address']).any():
        raise ValueError('Netted transfers trùng khóa transaction/cặp có hướng')
    if data.from_address.eq(data.to_address).any():
        raise ValueError('Netted transfers vẫn còn self-loop')
    return data


def calculate_iso_week_metadata(start_date, end_date):
    weeks = {}
    for d in pd.date_range(start_date, end_date):
        weeks.setdefault(d.strftime('%G-W%V'), []).append(d.date())
    return {w: dict(days_in_window=len(days), is_partial_week=len(days) < 7,
                    start_date=str(days[0]), end_date=str(days[-1])) for w, days in weeks.items()}


def build_dynamic_edges(df, window='daily', start_date=None, end_date=None):
    if window not in ('daily', 'weekly'):
        raise ValueError('window phải là daily hoặc weekly')
    start_date = start_date or date.fromisoformat(CONFIG['project']['start_date'])
    end_date = end_date or date.fromisoformat(CONFIG['project']['end_date'])
    time_col = 'tx_date' if window == 'daily' else 'tx_week'
    edges = df.groupby([time_col, 'from_address', 'to_address'], as_index=False, sort=True).agg(
        total_value=('amount', 'sum'), transaction_count=('transaction_hash', 'nunique'),
        min_value=('amount', 'min'), max_value=('amount', 'max'),
        gross_value=('gross_amount', 'sum'), event_count=('event_count', 'sum'),
        first_timestamp=('block_timestamp', 'min'), last_timestamp=('block_timestamp', 'max'),
        is_zero_address=('is_zero_address', 'any'))
    edges['mean_value'] = edges.total_value / edges.transaction_count
    edges = edges.rename(columns={time_col: 'time_window'})
    edges['time_window'] = edges.time_window.astype(str)
    edges['window_type'] = window
    meta = calculate_iso_week_metadata(start_date, end_date)
    edges['days_in_window'] = edges.time_window.map({w: m['days_in_window'] for w, m in meta.items()}) if window == 'weekly' else 1
    edges['is_partial_week'] = edges.days_in_window.lt(7) if window == 'weekly' else False
    edges['eligible_for_regression'] = ~edges.is_partial_week
    return edges.sort_values(['time_window', 'from_address', 'to_address']).reset_index(drop=True)


def compute_gini(values):
    values = np.sort(np.asarray(values, dtype=float))
    n = len(values)
    if n < 2 or values.sum() <= 0:
        return 0.0
    return float(2 * np.dot(np.arange(1, n+1), values) / (n * values.sum()) - (n+1)/n)


def compute_graph_metrics(edges_df, window_type, all_time_windows=None, week_meta=None):
    windows = all_time_windows if all_time_windows is not None else sorted(edges_df.time_window.unique())
    groups = dict(tuple(edges_df.groupby('time_window', sort=True)))
    rows = []
    for i, w in enumerate(windows, 1):
        sub = groups.get(w, edges_df.iloc[:0])
        graph = nx.DiGraph()
        graph.add_edges_from(sub[['from_address', 'to_address']].itertuples(index=False, name=None))
        node_vol = sub.groupby('from_address').total_value.sum().add(sub.groupby('to_address').total_value.sum(), fill_value=0)
        shares = node_vol / node_vol.sum() if node_vol.sum() else node_vol
        ins, outs = dict(graph.in_degree()), dict(graph.out_degree())
        max_in = min(ins, key=lambda n: (-ins[n], n)) if ins else None
        max_out = min(outs, key=lambda n: (-outs[n], n)) if outs else None
        metadata = week_meta.get(w, {}) if week_meta else {}
        partial = metadata.get('is_partial_week', False)
        rows.append(dict(time_window=str(w), num_nodes=len(graph), num_edges=graph.number_of_edges(),
            total_volume_usdt=float(sub.total_value.sum()), total_transactions=int(sub.transaction_count.sum()),
            gross_volume_usdt=float(sub.gross_value.sum()), total_events=int(sub.event_count.sum()),
            density=nx.density(graph), reciprocity=float(nx.reciprocity(graph) or 0) if graph.number_of_edges() else 0.0,
            num_weakly_connected_components=nx.number_weakly_connected_components(graph),
            num_strongly_connected_components=nx.number_strongly_connected_components(graph),
            max_in_degree=ins.get(max_in, 0), max_in_address=max_in,
            max_out_degree=outs.get(max_out, 0), max_out_address=max_out,
            top10_volume_share=float(shares.nlargest(10).sum()), gini_volume=compute_gini(node_vol.to_numpy()),
            hhi_volume=float((shares**2).sum()), is_partial_week=partial,
            days_in_window=metadata.get('days_in_window', 1), eligible_for_regression=not partial))
        if i % 100 == 0 or i == len(windows):
            print(f'{window_type}: {i}/{len(windows)} snapshots', flush=True)
    return pd.DataFrame(rows)


def generate_validation_table(df_netted, df_edges_daily, metrics_daily, self_loops_by_date, all_dates):
    incoming = df_netted.groupby('tx_date').agg(n_events_in=('event_count', 'sum'),
        n_netted_rows=('amount', 'size'), n_tx_in=('transaction_hash', 'nunique'),
        value_in=('amount', 'sum'), zero_addr=('is_zero_address', 'sum'))
    edges = df_edges_daily.groupby('time_window').agg(n_edges=('total_value', 'size'),
        value_edges=('total_value', 'sum'), edge_transaction_count=('transaction_count', 'sum'))
    incoming.index = incoming.index.astype(str)
    incoming = incoming.reindex([str(d) for d in all_dates], fill_value=0)
    result = incoming.join(edges).fillna(0)
    result['n_nodes'] = metrics_daily.set_index('time_window').num_nodes
    result['diff_value'] = result.value_edges - result.value_in
    result['self_loops'] = [self_loops_by_date.get(d, 0) for d in all_dates]
    result['status'] = np.where(np.isclose(result.value_in, result.value_edges, rtol=1e-12, atol=1e-4), 'PASS', 'FAIL')
    result.index.name = 'date'
    return result.reset_index()


class DynamicGraphLoader:
    def __init__(self, edges_parquet_path, labels_parquet_path=DEFAULT_LABELS_PARQUET):
        self.edges_path = Path(edges_parquet_path)
        self.df_edges = pd.read_parquet(self.edges_path)
        self.labels = {}
        if labels_parquet_path:
            path = Path(labels_parquet_path)
            labels = pd.read_parquet(path) if path.suffix == '.parquet' else pd.read_csv(path)
            if labels.address.duplicated().any():
                raise ValueError('Trùng địa chỉ trong T07')
            if 'is_contract' not in labels:
                raise ValueError('Cần bảng T07 hoàn chỉnh có is_contract')
            self.labels = labels.set_index('address').to_dict('index')
        self.window = self.df_edges.window_type.iloc[0] if not self.df_edges.empty else ('weekly' if 'weekly' in self.edges_path.name else 'daily')
        config = read_config()
        self.week_meta = calculate_iso_week_metadata(date.fromisoformat(config['project']['start_date']), date.fromisoformat(config['project']['end_date']))
        self.dates = pd.date_range(config['project']['start_date'], config['project']['end_date']).strftime('%Y-%m-%d').tolist()

    def get_time_windows(self):
        return sorted(self.week_meta) if self.window == 'weekly' else self.dates

    def build_snapshot_graph(self, time_window):
        key = str(time_window)
        if key not in self.get_time_windows():
            raise ValueError(f'Cửa sổ ngoài phạm vi nghiên cứu: {key}')
        metadata = self.week_meta[key] if self.window == 'weekly' else dict(is_partial_week=False, days_in_window=1)
        graph = nx.DiGraph(time_window=key, window_type=self.window, **metadata)
        graph.graph['eligible_for_regression'] = not metadata['is_partial_week']
        sub = self.df_edges.loc[self.df_edges.time_window.eq(key)]
        for row in sub.to_dict('records'):
            u, v = row.pop('from_address'), row.pop('to_address')
            graph.add_edge(u, v, weight=row['total_value'], **row)
        for node in graph:
            label = self.labels.get(node, {})
            value = label.get('is_contract')
            graph.nodes[node].update(entity_name=label.get('entity_name', 'Unknown'),
                entity_type=label.get('entity_type', 'Unknown'),
                **{'class': label.get('class', '')},
                is_contract=None if pd.isna(value) else bool(value),
                contract_status_source=label.get('contract_status_source', 'Not verified'),
                is_zero_address=node == ZERO_ADDRESS,
                in_degree=graph.in_degree(node), out_degree=graph.out_degree(node),
                in_volume=graph.in_degree(node, weight='weight'), out_volume=graph.out_degree(node, weight='weight'))
        return graph


def show_dynamic_graph_snapshot(edges_parquet_path, time_window, top_k_edges=0, output_dir=DEFAULT_OUTPUT_DIR, auto_open=True, labels_parquet_path=DEFAULT_LABELS_PARQUET):
    """Xuất biểu đồ HTML có zoom con lăn; chọn top-k chỉ ảnh hưởng hiển thị."""
    from src.graph_visualization import write_graph_html
    loader = DynamicGraphLoader(edges_parquet_path, labels_parquet_path)
    graph = loader.build_snapshot_graph(time_window)
    total_edges = graph.number_of_edges()
    total_volume = sum(d['weight'] for _, _, d in graph.edges(data=True))
    if top_k_edges < 0:
        raise ValueError('top_k_edges phải không âm')
    if top_k_edges > 0:
        selected = sorted(graph.edges(data=True), key=lambda edge: (-edge[2]['weight'], edge[0], edge[1]))[:top_k_edges]
        graph = graph.edge_subgraph([(u, v) for u, v, _ in selected]).copy()
    path = Path(output_dir) / f'graph_{time_window}.html'
    path.parent.mkdir(parents=True, exist_ok=True)
    write_graph_html(graph, path, time_window, total_edges, total_volume)
    if auto_open:
        webbrowser.open(path.resolve().as_uri())
    return path


def execute_t08_pipeline(input_parquet=DEFAULT_INPUT_PARQUET, output_dir=DEFAULT_OUTPUT_DIR, labels_path=DEFAULT_LABELS_PARQUET, **kwargs):
    from src.t08_pipeline import run_pipeline
    return run_pipeline(input_parquet=input_parquet, output_dir=output_dir, labels_path=labels_path, **kwargs)


if __name__ == '__main__':
    execute_t08_pipeline()
