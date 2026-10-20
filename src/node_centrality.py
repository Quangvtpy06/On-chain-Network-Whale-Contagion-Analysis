"""T09: Degree, weighted degree và weighted PageRank theo node/cửa sổ UTC.

Chỉ nhận T08 đã nghiệm thu và đúng SHA-256; không tải ngầm đồ thị cũ từ remote.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from src.graph_config import ROOT, read_config, project_path, relative_path

CONFIG=read_config()
INPUT_DIR=project_path(CONFIG['data']['processed_graphs_dir'])
OUTPUT_DIR=project_path(CONFIG['data']['processed_t09_dir'])
REQUIRED_COLUMNS={'time_window','from_address','to_address','total_value','transaction_count'}
NODE_TYPES={
    'window_type':'object','time_window':'object','address':'object',
    'in_degree':'int64','out_degree':'int64','degree':'int64',
    'in_strength_usdt':'float64','out_strength_usdt':'float64','weighted_degree_usdt':'float64',
    'in_tx_count':'int64','out_tx_count':'int64','weighted_degree_tx':'int64',
    'net_inflow_usdt':'float64','pagerank':'float64',
    'days_in_window':'int64','is_partial_week':'bool','eligible_for_regression':'bool',
}


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    temporary.replace(path)


def verified_t08_inputs(config):
    folder=project_path(config['data']['processed_graphs_dir'])
    summary=json.loads((folder/'t08_summary.json').read_text(encoding='utf-8'))
    if not summary.get('ready_for_t09_t12'):
        raise ValueError('T08 chưa được nghiệm thu cho T09–T12.')
    hashes=json.loads((folder/'t08_reproducibility.json').read_text(encoding='utf-8'))
    if not hashes.get('all_match'):
        raise ValueError('T08 chưa đạt đối chiếu tái lập.')
    sources={}
    for window in ['daily','weekly']:
        for key in [f'{window}_edges_parquet',f'{window}_metrics_parquet']:
            path=project_path(config['data'][key])
            expected=hashes['hashes'].get(path.name,{})
            actual=sha256(path)
            if actual!=expected.get('run1') or actual!=expected.get('run2'):
                raise ValueError(f'T08 khác bản đã nghiệm thu: {relative_path(path)}')
            sources[key]=dict(path=relative_path(path),sha256=actual)
    return sources


def validate_edge_table(df):
    if REQUIRED_COLUMNS-set(df):
        raise ValueError(f'Thiếu cột cạnh: {sorted(REQUIRED_COLUMNS-set(df))}')
    if df[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError('Cạnh có giá trị thiếu.')
    for column in ['from_address','to_address']:
        if not df[column].str.fullmatch(r'0x[0-9a-f]{40}').all():
            raise ValueError('Địa chỉ cạnh phải là 42 ký tự lowercase hợp lệ.')
    if df.duplicated(['time_window','from_address','to_address']).any():
        raise ValueError('Trùng cạnh T08; không cộng lại transaction_count một cách im lặng.')
    if df.from_address.eq(df.to_address).any():
        raise ValueError('T08 netted vẫn có cạnh tự trỏ.')
    values=df[['total_value','transaction_count']].to_numpy()
    if not np.isfinite(values).all() or (values<=0).any():
        raise ValueError('Trọng số cạnh phải hữu hạn và dương.')
    if not np.equal(df.transaction_count,np.floor(df.transaction_count)).all():
        raise ValueError('transaction_count phải là số nguyên.')


def load_edges(window_type,config=None):
    config=config or read_config()
    verified_t08_inputs(config)
    path=project_path(config['data'][f'{window_type}_edges_parquet'])
    df=pd.read_parquet(path)
    validate_edge_table(df)
    return df.sort_values(['time_window','from_address','to_address']).reset_index(drop=True)


def calendar_metadata(window,config):
    days=pd.date_range(config['project']['start_date'],config['project']['end_date'])
    if window=='daily':
        calendar=pd.DataFrame({'time_window':days.strftime('%Y-%m-%d'),'days_in_window':1})
    else:
        calendar=pd.Series(days.strftime('%G-W%V')).value_counts(sort=False).sort_index().rename_axis('time_window').reset_index(name='days_in_window')
    calendar['is_partial_week']=calendar.days_in_window.lt(7) if window=='weekly' else False
    calendar['eligible_for_regression']=~calendar.is_partial_week
    return calendar


def empty_nodes():
    return pd.DataFrame({name:pd.Series(dtype=kind) for name,kind in NODE_TYPES.items()})


def calculate_snapshot(sub,window_type,time_window,metadata=None,config=None):
    config=config or read_config()
    params=config['centrality']
    if metadata is None:
        matches=calendar_metadata(window_type,config).set_index('time_window')
        if str(time_window) not in matches.index:
            raise ValueError('Cửa sổ ngoài khoảng nghiên cứu.')
        metadata=matches.loc[str(time_window)].to_dict()
    validate_edge_table(sub)
    graph=nx.DiGraph()
    graph.add_nodes_from(sorted(set(sub.from_address)|set(sub.to_address)))
    graph.add_edges_from((r.from_address,r.to_address,dict(total_value=float(r.total_value),
        transaction_count=int(r.transaction_count))) for r in sub.itertuples(index=False))
    n=len(graph)
    stats=dict(window_type=window_type,time_window=str(time_window),num_nodes=n,
        num_edges=graph.number_of_edges(),total_volume_usdt=float(sub.total_value.sum()),
        total_edge_transactions=int(sub.transaction_count.sum()),pagerank_sum=0.0,
        pagerank_status='empty',pagerank_weight='total_value',pagerank_residual_l1=0.0,
        pagerank_l1_tolerance=params['pagerank_l1_tolerance'],**metadata)
    if not n:
        return empty_nodes(),stats
    incoming=dict(graph.in_degree(weight='total_value'))
    outgoing=dict(graph.out_degree(weight='total_value'))
    in_tx=dict(graph.in_degree(weight='transaction_count'))
    out_tx=dict(graph.out_degree(weight='transaction_count'))
    # NetworkX dừng ở n*tol. Chia cho n để mọi snapshot dùng cùng sai số L1.
    kwargs=dict(alpha=params['pagerank_alpha'],weight='total_value',
                tol=params['pagerank_l1_tolerance']/n)
    try:
        pagerank=nx.pagerank(graph,max_iter=params['pagerank_max_iter'],**kwargs)
        status='converged'
    except nx.PowerIterationFailedConvergence:
        pagerank=nx.pagerank(graph,max_iter=params['pagerank_retry_max_iter'],**kwargs)
        status='converged_retry'
    alpha=params['pagerank_alpha']
    dangling=sum(pagerank[node] for node in graph if outgoing[node]==0)
    predicted={node:(1-alpha)/n+alpha*dangling/n for node in graph}
    for u,v,data in graph.edges(data=True):
        predicted[v]+=alpha*pagerank[u]*data['total_value']/outgoing[u]
    residual=sum(abs(pagerank[node]-predicted[node]) for node in graph)
    if residual>params['pagerank_l1_tolerance']*2:
        raise ValueError('PageRank chưa đạt sai số L1 yêu cầu; không ghi kết quả chưa hội tụ.')
    rows=[]
    for node in graph:
        rows.append(dict(window_type=window_type,time_window=str(time_window),address=node,
            in_degree=graph.in_degree(node),out_degree=graph.out_degree(node),degree=graph.degree(node),
            in_strength_usdt=incoming[node],out_strength_usdt=outgoing[node],
            weighted_degree_usdt=incoming[node]+outgoing[node],in_tx_count=in_tx[node],
            out_tx_count=out_tx[node],weighted_degree_tx=in_tx[node]+out_tx[node],
            net_inflow_usdt=incoming[node]-outgoing[node],pagerank=pagerank[node],**metadata))
    result=pd.DataFrame(rows).astype(NODE_TYPES)
    stats.update(pagerank_sum=float(result.pagerank.sum()),pagerank_status=status,pagerank_residual_l1=residual)
    return result,stats


def process_window(window_type,max_windows,output_dir,config=None):
    config=config or read_config()
    edges=load_edges(window_type,config)
    calendar=calendar_metadata(window_type,config)
    t08=pd.read_parquet(project_path(config['data'][f'{window_type}_metrics_parquet']))
    if t08.time_window.tolist()!=calendar.time_window.tolist():
        raise ValueError('Lịch snapshot T08 không khớp config.')
    if set(edges.time_window)-set(calendar.time_window):
        raise ValueError('Cạnh có cửa sổ ngoài phạm vi nghiên cứu.')
    if max_windows:
        calendar=calendar.head(max_windows)
    groups={w:sub for w,sub in edges.groupby('time_window',sort=True)}
    results=[];stats=[]
    for i,row in enumerate(calendar.to_dict('records'),1):
        w=row.pop('time_window')
        nodes,snapshot=calculate_snapshot(groups.get(w,edges.iloc[:0]),window_type,w,row,config)
        if not nodes.empty:
            results.append(nodes)
        stats.append(snapshot)
        if i==1 or i%100==0 or i==len(calendar):
            print(f'{window_type}: {i}/{len(calendar)} | {w} | nodes={len(nodes):,} | PageRank={snapshot["pagerank_status"]}',flush=True)
    final=pd.concat(results,ignore_index=True) if results else empty_nodes()
    snapshots=pd.DataFrame(stats)
    if final.duplicated(['window_type','time_window','address']).any():
        raise ValueError('Trùng khóa node/cửa sổ.')
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    paths={f'node_metrics_{window_type}.parquet':final,f'snapshot_metrics_{window_type}.parquet':snapshots}
    artifacts={}
    for name,frame in paths.items():
        path=output_dir/name;temporary=path.with_suffix('.parquet.tmp')
        frame.to_parquet(temporary,index=False);temporary.replace(path)
        artifacts[name]=dict(path=relative_path(path),sha256=sha256(path),rows=len(frame))
    return dict(snapshots=len(calendar),node_metric_rows=len(final),
        empty_snapshots=int(snapshots.num_nodes.eq(0).sum()),
        partial_weeks=int(snapshots.is_partial_week.sum()),
        eligible_regression_snapshots=int(snapshots.eligible_for_regression.sum()),
        pagerank_retry_snapshots=int(snapshots.pagerank_status.eq('converged_retry').sum()),
        max_pagerank_residual_l1=float(snapshots.pagerank_residual_l1.max()),artifacts=artifacts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window',choices=['daily','weekly','both'],default='both')
    parser.add_argument('--max-windows',type=int,default=0)
    parser.add_argument('--output-dir',default=None)
    args=parser.parse_args()
    if args.max_windows<0:
        parser.error('--max-windows phải không âm.')
    config=read_config()
    output=project_path(args.output_dir) if args.output_dir else (ROOT/'.cache/t09_preview' if args.max_windows else project_path(config['data']['processed_t09_dir']))
    if args.max_windows and output.resolve()==project_path(config['data']['processed_t09_dir']).resolve():
        parser.error('Chạy thử phải dùng thư mục .cache/, không ghi đè bản đầy đủ.')
    sources=verified_t08_inputs(config)
    old_provenance=ROOT/'data/processed/t09/t09_remote_provenance.json'
    summary=dict(task='T09',schema_version=2,status='RUNNING',ready_for_downstream=False,
        is_preview=bool(args.max_windows),is_complete_run=args.window=='both' and args.max_windows==0,
        time_range=dict(start_date=config['project']['start_date'],end_date=config['project']['end_date']),
        time_zone='UTC',weekly_rule='ISO Monday start',
        metrics=['degree','weighted_degree_usdt','weighted_degree_tx','pagerank'],
        pagerank=config['centrality'],input_files=sources,
        source_t08_summary_sha256=sha256(INPUT_DIR/'t08_summary.json'),
        config_sha256=sha256(ROOT/'config/config.yaml'),code_file=relative_path(Path(__file__)),code_sha256=sha256(Path(__file__)),
        package_versions={name:version(name) for name in ['networkx','numpy','pandas','scipy','pyarrow']},
        replaces_remote_outputs=json.loads(old_provenance.read_text()) if old_provenance.is_file() else None,
        generated_at=datetime.now(timezone.utc).isoformat(),results={})
    write_json(output/'t09_summary.json',summary)
    write_json(output/'t09_review.json',dict(status='PENDING',ready_for_downstream=False))
    for window in (['daily','weekly'] if args.window=='both' else [args.window]):
        summary['results'][window]=process_window(window,args.max_windows,output,config)
    if verified_t08_inputs(config)!=sources:
        raise ValueError('Đầu vào T08 thay đổi trong khi chạy.')
    summary['status']='GENERATED_PENDING_REVIEW'
    write_json(output/'t09_summary.json',summary)
    print('T09 generated; independent validation required before release.',flush=True)


if __name__=='__main__':
    main()
