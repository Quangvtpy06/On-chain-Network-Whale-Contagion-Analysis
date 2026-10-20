"""Nghiệm thu độc lập T09 mới bằng pandas + phương trình PageRank SciPy.

Không import thuật toán production của T09. Chỉ bật ready khi đủ cả hai độ phân
giải, mọi node/cửa sổ khớp T08 và toàn bộ hash/provenance không đổi.
"""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.t09_reference import compare, METRICS


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_window(window,folder,cfg):
    nodes=pd.read_parquet(folder/f'node_metrics_{window}.parquet')
    snapshots=pd.read_parquet(folder/f'snapshot_metrics_{window}.parquet')
    edges=pd.read_parquet(ROOT/cfg['data'][f'{window}_edges_parquet'])
    t08=pd.read_parquet(ROOT/cfg['data'][f'{window}_metrics_parquet'])
    params=cfg['centrality'];tol=params['pagerank_l1_tolerance']*2
    checked=compare(nodes,edges,window,'current_netted_t08',
                    alpha=params['pagerank_alpha'],pagerank_tolerance=tol)
    days=pd.date_range(cfg['project']['start_date'],cfg['project']['end_date'])
    if window=='daily':
        calendar=pd.Series(1,index=days.strftime('%Y-%m-%d'))
    else:
        calendar=pd.Series(days.strftime('%G-W%V')).groupby(lambda i:days[i].strftime('%G-W%V')).size().sort_index()
    expected=calendar.index.tolist()
    calendar_ok=snapshots.time_window.tolist()==expected and not snapshots.time_window.duplicated().any()
    if not calendar_ok:
        raise ValueError(f'{window}: thiếu/trùng/sai thứ tự cửa sổ.')
    if not nodes.window_type.eq(window).all() or set(nodes.time_window)-set(expected):
        raise ValueError('Sai loại cửa sổ hoặc ngày ngoài kỳ nghiên cứu.')
    if nodes.duplicated(['window_type','time_window','address']).any():
        raise ValueError('Trùng khóa node/cửa sổ.')
    if not nodes.address.str.fullmatch(r'0x[0-9a-f]{40}').all():
        raise ValueError('Địa chỉ node không hợp lệ.')
    if not np.isfinite(nodes[METRICS+['pagerank']].to_numpy()).all():
        raise ValueError('Chỉ số node không hữu hạn.')
    if nodes[[x for x in METRICS if x!='net_inflow_usdt']+['pagerank']].lt(0).any().any():
        raise ValueError('Chỉ số không âm bị âm.')
    for col in ['in_degree','out_degree','degree','in_tx_count','out_tx_count','weighted_degree_tx']:
        if not pd.api.types.is_integer_dtype(nodes[col]):
            raise ValueError(f'{col} phải lưu bằng kiểu số nguyên.')
    checked=checked.set_index('time_window') if not checked.empty else pd.DataFrame()
    grouped={w:sub for w,sub in nodes.groupby('time_window')}
    t08=t08.set_index('time_window')
    rows=[]
    for snap in snapshots.to_dict('records'):
        w=snap['time_window'];sub=grouped.get(w,nodes.iloc[:0]);expected_days=int(calendar.loc[w])
        partial=window=='weekly' and expected_days<7
        metadata_ok=(snap['days_in_window']==expected_days and snap['is_partial_week']==partial
            and snap['eligible_for_regression']==(not partial)
            and sub.days_in_window.eq(expected_days).all() and sub.is_partial_week.eq(partial).all()
            and sub.eligible_for_regression.eq(not partial).all())
        if w in checked.index:
            result=checked.loc[w].to_dict()
            base_ok=result['status']=='PASS'
        else:
            result=dict(window_type=window,reference='current_netted_t08',pagerank_residual_l1=0.,
                        pagerank_residual_tolerance=tol)
            base_ok=len(sub)==0 and t08.loc[w,'num_nodes']==0
        n=len(sub);m=int(t08.loc[w,'num_edges']);volume=float(t08.loc[w,'total_volume_usdt'])
        sum_ok=(snap['num_nodes']==n==t08.loc[w,'num_nodes'] and snap['num_edges']==m
            and np.isclose(snap['total_volume_usdt'],volume,rtol=1e-12,atol=1e-4)
            and int(sub.in_degree.sum())==m==int(sub.out_degree.sum())
            and np.isclose(sub.in_strength_usdt.sum(),volume,rtol=1e-12,atol=1e-4)
            and np.isclose(sub.out_strength_usdt.sum(),volume,rtol=1e-12,atol=1e-4)
            and sub.in_tx_count.sum()==sub.out_tx_count.sum()==snap['total_edge_transactions']
            and snap['total_edge_transactions']==int(t08.loc[w,'total_transactions']))
        pr_ok=(snap['pagerank_weight']=='total_value' and
            snap['pagerank_l1_tolerance']==params['pagerank_l1_tolerance'] and
            snap['pagerank_residual_l1']<=tol and
            np.isclose(snap['pagerank_sum'],1. if n else 0.,rtol=0,atol=1e-12) and
            snap['pagerank_status'] in (['converged','converged_retry'] if n else ['empty']))
        result.update(time_window=w,window_type=window,metadata_pass=bool(metadata_ok),
            snapshot_totals_pass=bool(sum_ok),pagerank_status_pass=bool(pr_ok),
            status='PASS' if base_ok and metadata_ok and sum_ok and pr_ok else 'FAIL')
        rows.append(result)
    return pd.DataFrame(rows)


def main():
    cfg=yaml.safe_load((ROOT/'config/config.yaml').read_text(encoding='utf-8'))
    folder=ROOT/cfg['data']['processed_t09_dir']
    summary=json.loads((folder/'t09_summary.json').read_text(encoding='utf-8'))
    if not summary.get('is_complete_run') or summary.get('is_preview'):
        raise ValueError('Chưa phải lần chạy đầy đủ daily + weekly.')
    if sha256(ROOT/'config/config.yaml')!=summary['config_sha256'] or sha256(ROOT/summary['code_file'])!=summary['code_sha256']:
        raise ValueError('Config/code thay đổi sau khi sinh dữ liệu.')
    t08folder=ROOT/cfg['data']['processed_graphs_dir']
    t08=json.loads((t08folder/'t08_summary.json').read_text(encoding='utf-8'))
    if not t08.get('ready_for_t09_t12') or sha256(t08folder/'t08_summary.json')!=summary['source_t08_summary_sha256']:
        raise ValueError('T08 không còn đúng bản đã dùng sinh T09.')
    input_hashes={}
    manifest=json.loads((t08folder/'t08_reproducibility.json').read_text(encoding='utf-8'))
    for record in summary['input_files'].values():
        path=ROOT/record['path'];actual=sha256(path)
        expected=manifest['hashes'][path.name]
        if actual!=record['sha256'] or actual!=expected['run1'] or actual!=expected['run2']:
            raise ValueError('Hash đầu vào không khớp T08 nghiệm thu.')
        input_hashes[record['path']]=actual
    output_hashes={}
    for section in summary['results'].values():
        for name,record in section['artifacts'].items():
            actual=sha256(ROOT/record['path'])
            if actual!=record['sha256']:
                raise ValueError('Output thay đổi sau khi được sinh.')
            output_hashes[name]=actual
    validation=pd.concat([validate_window(w,folder,cfg) for w in ['daily','weekly']],ignore_index=True)
    validation.to_parquet(folder/'t09_validation.parquet',index=False)
    passed=bool(validation.status.eq('PASS').all())
    report=dict(status='PASS' if passed else 'FAIL',ready_for_downstream=passed,
        reference='current_netted_t08',scope='Independent pandas node aggregations and SciPy PageRank stationarity equation, every node/window.',
        input_hashes=input_hashes,output_hashes=output_hashes,
        checks=validation.groupby('window_type').status.value_counts().unstack(fill_value=0).reset_index().to_dict('records'),
        max_pagerank_residual_l1=float(validation.pagerank_residual_l1.max()),
        window_metadata_verified=True,source_code_and_config_hashes_verified=True)
    repro_path=folder/'t09_reproducibility.json'
    if repro_path.is_file():
        proof=json.loads(repro_path.read_text(encoding='utf-8'))
        report['reproducibility_pass']=bool(proof.get('all_match') and len(output_hashes)==4 and all(
            expected==proof.get('hashes',{}).get(name,{}).get('run1')==proof.get('hashes',{}).get(name,{}).get('run2')
            for name,expected in output_hashes.items()))
    (folder/'t09_review.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    summary.update(status='VALIDATED' if passed else 'VALIDATION_FAILED',ready_for_downstream=passed,
        validation_files=['data/processed/t09/t09_validation.parquet','data/processed/t09/t09_review.json'])
    (folder/'t09_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    lines=['# T09 — Nghiệm thu trên T08 netted','',
        '**Trạng thái: '+('Đạt' if passed else 'Chưa đạt')+'**. Đối chiếu độc lập toàn bộ node/cửa sổ bằng pandas và phương trình PageRank SciPy.','',
        '| Độ phân giải | Snapshot | Dòng node–cửa sổ | Tuần thiếu ngày |','|---|---:|---:|---:|']
    for window,section in summary['results'].items():
        lines.append(f'| {window} | {section["snapshots"]} | {section["node_metric_rows"]:,} | {section["partial_weeks"]} |')
    lines+=['',f'Sai số phương trình PageRank L1 lớn nhất: {report["max_pagerank_residual_l1"]:.3g}.',
        'Đã xác minh hash đầu vào, code, config và bốn bảng output. Đầu vào là T08 netted đã nghiệm thu; không dùng đồ thị thô cũ.',
        'Các bảng node và bảng cửa sổ đều có days_in_window, is_partial_week, eligible_for_regression. Hai tuần thiếu ngày không dùng trong hồi quy.',
        'Cửa sổ rỗng được giữ trong bảng snapshot (0 node, 0 cạnh, PageRank sum=0); bảng node không thêm ví giả.',
        'Degree là in + out; weighted_degree_usdt là tổng volume vào + ra; weighted_degree_tx là tổng tần suất transaction theo cạnh, không phải unique transaction của cả ví.',
        'PageRank có hướng dùng total_value, alpha trong config, phân phối uniform cho personalization/dangling; retry giữ cùng ngưỡng L1.',
        'Nguồn remote cũ được thay thế có revision/hash ghi trong replaces_remote_outputs ở summary. Review lịch sử nằm trong docs/T09_legacy_remote_review.md.',
        '', 'Bàn giao: node_metrics_daily/weekly.parquet, snapshot_metrics_daily/weekly.parquet, t09_validation.parquet, t09_summary.json, t09_review.json.',
        'Chạy lại: python T09_Network_Centrality.py rồi python scripts/validate_t09_current.py. Test/cache không nằm trong data/processed.']
    (ROOT/'docs/T09_completion_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ROOT/'docs/T09_review_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)
    if not passed:
        raise SystemExit(1)


if __name__=='__main__':
    main()
