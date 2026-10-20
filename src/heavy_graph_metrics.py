"""Chỉ số T10, sampling xác định và kiểm tra nghiệm thu trên dữ liệu thật."""
import argparse
import hashlib
import json
import os
import shutil
import uuid
from importlib.metadata import version

import networkx as nx
import numpy as np
import pandas as pd
from scipy.sparse.linalg import eigs

from src.graph_config import ROOT, read_config, project_path, relative_path
from src.node_centrality import calendar_metadata, verified_t08_inputs, validate_edge_table, sha256, write_json

SETTINGS_PATH = ROOT / 'config/t10.yaml'
METRICS = ['betweenness', 'eigenvector', 'clustering', 'clustering_weighted']


def make_graph(sub):
    graph = nx.DiGraph()
    graph.add_nodes_from(sorted(set(sub.from_address) | set(sub.to_address)))
    graph.add_weighted_edges_from(sub[['from_address', 'to_address', 'total_value']].itertuples(index=False, name=None))
    return graph


def incoming_eigenvector(graph, settings):
    """Perron trái; DAG dùng vector đều trên sink (không có thứ hạng duy nhất)."""
    n = len(graph)
    matrix = nx.to_scipy_sparse_array(graph, nodelist=list(graph), weight='weight', dtype=float, format='csr')
    scale = max(float(np.asarray(matrix.sum(axis=1)).max()), 1.)
    operator = matrix.T / scale
    if nx.is_directed_acyclic_graph(graph):
        x = np.array([graph.out_degree(u) == 0 for u in graph], dtype=float)
        method = 'dag_equal_sinks'
    elif n <= 64:
        values, vectors = np.linalg.eig(operator.toarray())
        x = np.abs(vectors[:, np.argmax(values.real)].real)
        method = 'dense_perron'
    else:
        values, vectors = eigs(operator, k=1, which='LR', v0=np.ones(n)/np.sqrt(n),
            tol=settings['eigenvector_tolerance']/100, maxiter=settings['eigenvector_max_iter'])
        if abs(values[0].imag) > 1e-8:
            raise ValueError('Eigenvector có trị riêng phức ngoài tolerance.')
        x = np.abs(vectors[:, 0].real)
        method = 'arpack_perron'
    x /= np.linalg.norm(x)
    y = operator @ x
    eigenvalue = float(x @ y)
    residual = float(np.linalg.norm(y-eigenvalue*x) / max(np.linalg.norm(y), abs(eigenvalue), 1e-15))
    if not np.isfinite(x).all() or residual > settings['eigenvector_tolerance']:
        raise ValueError(f'Eigenvector không hội tụ: residual={residual}')
    return x, dict(eigenvector_method=method, eigenvalue_usdt=eigenvalue*scale,
        eigenvector_residual=residual, eigenvector_may_be_nonunique=not nx.is_strongly_connected(graph),
        eigenvector_ranking_degenerate=method == 'dag_equal_sinks')


def calculate(graph, window, key, settings):
    n = len(graph)
    seed = int(hashlib.sha256(f'{settings["seed"]}|{window}|{key}'.encode()).hexdigest()[:8], 16)
    exact = n <= settings['betweenness_exact_max_nodes']
    pivots = n if exact else min(n, settings['betweenness_pivots'])
    stats = dict(betweenness_method='exact' if exact else 'sampled_sources',
        betweenness_pivots=pivots, sampling_seed=seed)
    if not n:
        return pd.DataFrame({'address': pd.Series(dtype=str), **{m: pd.Series(dtype=float) for m in METRICS}}), dict(
            **stats, eigenvector_method='empty', eigenvalue_usdt=0., eigenvector_residual=0.,
            eigenvector_may_be_nonunique=False, eigenvector_ranking_degenerate=False)
    b = nx.betweenness_centrality(graph, k=None if exact else pivots, normalized=True, weight=None, seed=seed)
    x, eigenstats = incoming_eigenvector(graph, settings)
    c = nx.clustering(graph)
    cw = nx.clustering(graph, weight='weight')
    nodes = pd.DataFrame(dict(address=list(graph), betweenness=[b[u] for u in graph], eigenvector=x,
        clustering=[c[u] for u in graph], clustering_weighted=[cw[u] for u in graph]))
    return nodes, dict(**stats, **eigenstats)


def independent_checks(graph, nodes, stats, settings):
    """Clustering: biểu thức ma trận độc lập; eigenvector: phương trình riêng."""
    n = len(graph)
    if not n:
        return dict(status='PASS', clustering_max_error=0., eigenvector_residual=0.)
    a = nx.to_scipy_sparse_array(graph, nodelist=list(graph), weight='weight', dtype=float, format='csr')
    binary = a.copy(); binary.data[:] = 1
    degree = np.asarray(binary.sum(axis=0)).ravel()+np.asarray(binary.sum(axis=1)).ravel()
    reciprocal = np.asarray(binary.multiply(binary.T).sum(axis=1)).ravel()
    denominator = 2*(degree*(degree-1)-2*reciprocal)
    refs = []
    for matrix in [binary, a / float(a.max())]:
        matrix = matrix.copy(); matrix.data = np.cbrt(matrix.data)
        symmetric = matrix + matrix.T
        triangles = np.asarray((symmetric @ symmetric).multiply(symmetric.T).sum(axis=1)).ravel()
        refs.append(np.divide(triangles, denominator, out=np.zeros(n), where=denominator != 0))
    error = max(float(np.max(np.abs(nodes[column].to_numpy()-ref)))
        for column, ref in zip(['clustering', 'clustering_weighted'], refs))
    x = nodes.eigenvector.to_numpy()
    y = a.T @ x
    value = stats['eigenvalue_usdt']
    residual = float(np.linalg.norm(y-value*x)/max(np.linalg.norm(y), abs(value), 1e-15))
    numeric = nodes[METRICS].to_numpy()
    ok = (np.isfinite(numeric).all() and (numeric >= 0).all() and
        nodes.address.tolist() == list(graph) and not nodes.address.duplicated().any() and
        nodes[['betweenness', 'clustering', 'clustering_weighted']].le(1+1e-10).all().all() and
        np.isclose(np.linalg.norm(x), 1, atol=1e-10) and error < 1e-10 and
        residual <= settings['eigenvector_tolerance'])
    return dict(status='PASS' if ok else 'FAIL', clustering_max_error=error, eigenvector_residual=residual)


def run(folder, cfg, settings):
    folder.mkdir(parents=True, exist_ok=True)
    validation = []; quality = []; shapes = {}
    for window in ['daily', 'weekly']:
        edges = pd.read_parquet(project_path(cfg['data'][f'{window}_edges_parquet']))
        validate_edge_table(edges)
        edges = edges.sort_values(['time_window', 'from_address', 'to_address'])
        groups = {str(k): v for k, v in edges.groupby('time_window', sort=True)}
        calendar = calendar_metadata(window, cfg)
        t08 = pd.read_parquet(project_path(cfg['data'][f'{window}_metrics_parquet']))
        if t08.time_window.astype(str).tolist() != calendar.time_window.tolist():
            raise ValueError('Lịch T08 không khớp config.')
        if set(groups)-set(calendar.time_window):
            raise ValueError('Cạnh ngoài lịch.')
        # Chọn cửa sổ nhỏ/trung vị/lớn theo số node; công bố sai số, không đặt ngưỡng giả.
        sizes = [(len(set(s.from_address)|set(s.to_address)), k) for k,s in groups.items()]
        ordered = [k for _,k in sorted(sizes)]
        selected = {ordered[i] for i in np.linspace(0, len(ordered)-1, settings['quality_windows_per_scale'], dtype=int)} if ordered else set()
        node_frames = []; snapshots = []
        for i, meta in enumerate(calendar.to_dict('records')):
            key = meta['time_window']; sub = groups.get(key, edges.iloc[:0]); graph = make_graph(sub)
            nodes, stats = calculate(graph, window, key, settings)
            checks = independent_checks(graph, nodes, stats, settings)
            if checks['status'] != 'PASS':
                raise ValueError(f'{window}/{key}: {checks}')
            row = dict(window_type=window, **meta, num_nodes=len(graph), num_edges=len(sub), **stats)
            for m in METRICS:
                row[f'mean_{m}'] = float(nodes[m].mean()) if len(nodes) else 0.
            snapshots.append(row)
            validation.append(dict(window_type=window, **meta, n_nodes=len(nodes), n_edges=len(sub), **checks))
            if key in selected and len(graph):
                exact = np.array(list(nx.betweenness_centrality(graph, normalized=True, weight=None).values()))
                observed = nodes.betweenness.to_numpy(); top = min(20,len(nodes))
                reference_top = set(np.argsort(-exact, kind='stable')[:top])
                sample_top = set(np.argsort(-observed, kind='stable')[:top])
                quality.append(dict(window_type=window,time_window=key,n_nodes=len(nodes),
                    method=stats['betweenness_method'], pivots=stats['betweenness_pivots'],
                    mae=float(np.mean(abs(observed-exact))), rmse=float(np.sqrt(np.mean((observed-exact)**2))),
                    max_absolute_error=float(max(abs(observed-exact))), top20_overlap=len(reference_top & sample_top)/top))
            for name, value in dict(window_type=window, **meta, **stats).items():
                nodes[name] = value
            node_frames.append(nodes)
            if i % 25 == 0:
                print(f'T10 {window}: {i+1}/{len(calendar)} {key}', flush=True)
        combined = pd.concat(node_frames, ignore_index=True)
        combined.to_parquet(folder/f'node_metrics_{window}.parquet', index=False)
        pd.DataFrame(snapshots).to_parquet(folder/f'snapshot_metrics_{window}.parquet', index=False)
        shapes[window] = dict(rows=len(combined), snapshots=len(snapshots))
    pd.DataFrame(validation).to_parquet(folder/'t10_validation.parquet', index=False)
    pd.DataFrame(quality).to_parquet(folder/'t10_sampling_quality.parquet', index=False)
    return shapes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-reproducibility', action='store_true', help='Exploration only; never marks ready.')
    args = parser.parse_args()
    cfg = read_config(); settings = read_config(SETTINGS_PATH)
    if settings['betweenness_pivots'] < 2 or settings['betweenness_exact_max_nodes'] < 0:
        raise ValueError('Sampling cần ít nhất 2 pivot.')
    sources = verified_t08_inputs(cfg)
    folder = project_path(settings['output_dir'])
    code_path = ROOT/'src/heavy_graph_metrics.py'
    provenance = dict(inputs=sources, config_sha256=sha256(ROOT/'config/config.yaml'),
        settings_sha256=sha256(SETTINGS_PATH), code_sha256=sha256(code_path))
    write_json(folder/'t10_summary.json', dict(ready_for_downstream=False, settings=settings, **provenance))
    shapes = run(folder, cfg, settings)
    names = sorted(p.name for p in folder.glob('*.parquet'))
    hashes = {name: dict(run1=sha256(folder/name)) for name in names}
    same = False
    if not args.skip_reproducibility:
        cache = ROOT/'.cache'; cache.mkdir(exist_ok=True)
        temporary = cache / f't10_repro_{uuid.uuid4().hex}'
        temporary.mkdir()
        try:
            probe = temporary / 'write_probe'
            probe.write_bytes(b'ok'); probe.unlink()
            run(temporary, cfg, settings)
            for name in names:
                hashes[name]['run2'] = sha256(temporary/name)
            same = all(v['run1'] == v['run2'] for v in hashes.values())
        finally:
            if not temporary.resolve().is_relative_to(cache.resolve()):
                raise ValueError('Refusing cleanup outside project cache.')
            shutil.rmtree(temporary)
    if verified_t08_inputs(cfg) != sources or sha256(code_path) != provenance['code_sha256'] or sha256(SETTINGS_PATH) != provenance['settings_sha256'] or sha256(ROOT/'config/config.yaml') != provenance['config_sha256']:
        raise ValueError('Input/code/config đã thay đổi trong khi chạy.')
    write_json(folder/'t10_reproducibility.json',dict(all_match=same, hashes=hashes))
    checks = pd.read_parquet(folder/'t10_validation.parquet')
    ready = bool(same and checks.status.eq('PASS').all())
    summary = dict(task='T10', ready_for_downstream=ready, settings=settings, **provenance,
        python_hash_seed=os.environ.get('PYTHONHASHSEED'),
        shapes=shapes, validation_pass=int(checks.status.eq('PASS').sum()),
        versions={p: version(p) for p in ['networkx','numpy','scipy','pandas','pyarrow']},
        limitations=['Betweenness samples are estimates, not exact rankings; see measured errors.',
            'Eigenvectors on reducible graphs can be nonunique and vanish outside dominant components.',
            'DAG eigenvectors use equal sink support and are flagged as degenerate.',
            'Metrics describe the thresholded whale transfer subnetwork only.'])
    write_json(folder/'t10_summary.json', summary)
    print(json.dumps(summary, indent=2), flush=True)
    if not ready and not args.skip_reproducibility:
        raise ValueError('T10 không đạt tái lập.')
