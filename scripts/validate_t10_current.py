"""Release validator for T10: verify stored outputs against current T08 inputs."""
import json
import argparse
import random
import sys
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.graph_config import read_config, project_path
from src.node_centrality import sha256, write_json, verified_t08_inputs, calendar_metadata


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--wait-for-reproducibility', action='store_true',
        help='Validate tables while the second run is computing, then wait for its proof.')
    args=parser.parse_args()
    cfg=read_config(); settings=read_config(ROOT/'config/t10.yaml')
    folder=project_path(settings['output_dir'])
    summary=json.loads((folder/'t10_summary.json').read_text(encoding='utf-8'))
    passed=(summary['inputs']==verified_t08_inputs(cfg) and
        summary['config_sha256']==sha256(ROOT/'config/config.yaml') and
        summary['settings_sha256']==sha256(ROOT/'config/t10.yaml') and
        summary['code_sha256']==sha256(ROOT/'src/heavy_graph_metrics.py'))
    rows=[]
    for window in ['daily','weekly']:
        edges=pd.read_parquet(project_path(cfg['data'][f'{window}_edges_parquet']))
        nodes=pd.read_parquet(folder/f'node_metrics_{window}.parquet')
        snapshots=pd.read_parquet(folder/f'snapshot_metrics_{window}.parquet')
        calendar=calendar_metadata(window,cfg)
        if snapshots.time_window.tolist()!=calendar.time_window.tolist() or nodes.duplicated(['time_window','address']).any():
            passed=False
        for column in ['days_in_window','is_partial_week','eligible_for_regression']:
            if snapshots[column].tolist()!=calendar[column].tolist():
                passed=False
        groups={str(k):v for k,v in edges.groupby('time_window')}
        nodegroups={str(k):v for k,v in nodes.groupby('time_window')}
        for i,snapshot in enumerate(snapshots.to_dict('records')):
            key=snapshot['time_window']; sub=groups.get(key,edges.iloc[:0])
            observed=nodegroups.get(key,nodes.iloc[:0]).sort_values('address')
            graph=nx.DiGraph()
            graph.add_nodes_from(sorted(set(sub.from_address)|set(sub.to_address)))
            graph.add_weighted_edges_from(sub.sort_values(['from_address','to_address'])[
                ['from_address','to_address','total_value']].itertuples(index=False,name=None))
            n=len(graph); k=snapshot['betweenness_pivots']
            exact=snapshot['betweenness_method']=='exact'
            sources=list(graph) if exact else random.Random(snapshot['sampling_seed']).sample(list(graph),k)
            # Independent subset API, then explicit directed/source-conditioned normalization.
            raw=nx.betweenness_centrality_subset(graph,sources,list(graph),normalized=False,weight=None)
            source_set=set(sources)
            reference=[]
            for u in graph:
                denominator=(n-1)*(n-2) if exact else ((k-1) if u in source_set else k)*(n-2)
                reference.append(raw[u]/denominator if n>2 else 0.)
            error=float(np.max(abs(observed.betweenness.to_numpy()-reference))) if n else 0.
            metadata_ok=all(observed[col].eq(snapshot[col]).all() for col in [
                'days_in_window','is_partial_week','eligible_for_regression','betweenness_method',
                'betweenness_pivots','sampling_seed','eigenvector_method'])
            ok=(observed.address.tolist()==list(graph) and error<1e-12 and metadata_ok and
                n==snapshot['num_nodes'] and len(sub)==snapshot['num_edges'])
            rows.append(dict(window_type=window,time_window=key,betweenness_max_error=error,
                status='PASS' if ok else 'FAIL'))
            if i%100==0:
                print(f'T10 independent subset review {window}: {i+1}/{len(snapshots)}',flush=True)
        if set(nodegroups)-set(calendar.time_window):
            passed=False
    deadline=time.monotonic()+1800
    while args.wait_for_reproducibility and not (folder/'t10_reproducibility.json').is_file() and time.monotonic()<deadline:
        time.sleep(2)
    summary=json.loads((folder/'t10_summary.json').read_text(encoding='utf-8'))
    repro=json.loads((folder/'t10_reproducibility.json').read_text(encoding='utf-8'))
    passed=bool(passed and summary['inputs']==verified_t08_inputs(cfg) and
        summary.get('python_hash_seed')=='0' and
        summary['config_sha256']==sha256(ROOT/'config/config.yaml') and
        summary['settings_sha256']==sha256(ROOT/'config/t10.yaml') and
        summary['code_sha256']==sha256(ROOT/'src/heavy_graph_metrics.py') and
        repro['all_match'] and len(repro['hashes'])==6 and all(
            sha256(folder/name)==proof['run1']==proof['run2'] for name,proof in repro['hashes'].items()))
    stored=pd.read_parquet(folder/'t10_validation.parquet')
    passed=bool(passed and len(stored)==len(rows) and stored.status.eq('PASS').all() and
        all(row['status']=='PASS' for row in rows))
    review=dict(all_pass=passed,windows_checked=len(rows),
        reference='NetworkX subset shortest-path API with explicit source-conditioned normalization',
        max_betweenness_error=max(row['betweenness_max_error'] for row in rows),
        independent_clustering_and_eigenvector_checks=int(stored.status.eq('PASS').sum()),
        validator_sha256=sha256(Path(__file__)),
        production_validation='Sparse directed triangle formula and weighted incoming eigen-equation, all nodes.',
        output_hashes={name:sha256(folder/name) for name in repro['hashes']})
    write_json(folder/'t10_review.json',review)
    summary['ready_for_downstream']=passed
    write_json(folder/'t10_summary.json',summary)
    print(json.dumps(review,indent=2),flush=True)
    if not passed:
        raise ValueError('T10 independent review failed.')


if __name__=='__main__':
    main()
