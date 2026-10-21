"""Whale Score mô tả hoạt động mạng; không xác nhận nhà đầu tư cá nhân."""
import hashlib
import json
import shutil
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from src.graph_config import ROOT, read_config, project_path, relative_path
from src.node_centrality import calendar_metadata, sha256, verified_t08_inputs, write_json

SETTINGS_FILE = ROOT/'config/t12.yaml'
COMPONENTS = {'value': 'value_column', 'weighted_degree': 'weighted_degree_column', 'pagerank': 'pagerank_column'}
LABEL_COLUMNS = ['address','entity_name','entity_type','class','public_category','confidence',
    'source_url','is_contract','label_conflict_review','is_entity_attributed','contract_status_as_of']
OUTPUT_NAMES = ['whale_scores_daily.parquet','whale_scores_weekly.parquet',
    'snapshot_metrics_daily.parquet','snapshot_metrics_weekly.parquet',
    't12_standardization.parquet','t12_validation.parquet']


def checked_path(value):
    path = project_path(value).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('Đường dẫn T12 phải nằm trong dự án.')
    return path


def verify_inputs(cfg):
    """Chặn T09 cũ, dữ liệu bị đổi và nhãn không khớp bản bàn giao T07."""
    sources = verified_t08_inputs(cfg)
    directory = project_path(cfg['data']['processed_t09_dir'])
    summary_path = directory/'t09_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    review_path = directory/'t09_review.json'
    review = json.loads(review_path.read_text(encoding='utf-8'))
    repro_path = directory/'t09_reproducibility.json'
    repro = json.loads(repro_path.read_text(encoding='utf-8'))
    if not (summary.get('ready_for_downstream') and summary.get('is_complete_run') and
            review.get('ready_for_downstream') and review.get('reproducibility_pass') and repro.get('all_match')):
        raise ValueError('T09 chưa nghiệm thu đầy đủ.')
    if summary['config_sha256'] != sha256(ROOT/'config/config.yaml') or summary['code_sha256'] != sha256(ROOT/summary['code_file']):
        raise ValueError('Code/config T09 đã thay đổi sau nghiệm thu.')
    if summary['source_t08_summary_sha256'] != sha256(project_path(cfg['data']['summary_json'])):
        raise ValueError('T09 không dùng đúng bản T08 hiện tại.')
    for path, expected in review['input_hashes'].items():
        if sha256(project_path(path)) != expected:
            raise ValueError('Nguồn T09 thay đổi.')
    tracked = [summary_path, review_path, repro_path, ROOT/'config/config.yaml',
        ROOT/summary['code_file']]
    for window in ['daily','weekly']:
        for stem in ['node_metrics','snapshot_metrics']:
            name = f'{stem}_{window}.parquet'; path = directory/name
            actual = sha256(path); proof = repro['hashes'][name]
            if not actual == proof['run1'] == proof['run2'] == review['output_hashes'][name]:
                raise ValueError(f'T09 output không khớp nghiệm thu: {name}')
            tracked.append(path)
    labels_path = project_path(cfg['data']['processed_labels_parquet'])
    label_summary_path = labels_path.parent/'t07_complete_summary.json'
    label_summary = json.loads(label_summary_path.read_text(encoding='utf-8'))
    if not label_summary.get('complete'):
        raise ValueError('T07 chưa hoàn tất bảng nhãn đầy đủ.')
    labels = pd.read_parquet(labels_path)
    if set(LABEL_COLUMNS)-set(labels) or labels.address.duplicated().any() or not labels.address.str.fullmatch(r'0x[0-9a-f]{40}',na=False).all():
        raise ValueError('T07 thiếu thuộc tính, trùng hoặc sai định dạng địa chỉ.')
    if len(labels) != label_summary['total_addresses']:
        raise ValueError('Số địa chỉ T07 không khớp summary.')
    release_path = ROOT/'data/hf_release_manifest.json'
    if release_path.is_file():
        release = json.loads(release_path.read_text(encoding='utf-8'))
        records = {r['path']: r for r in release.get('upload_files', [])}
        expected = records.get(relative_path(labels_path), {}).get('sha256')
        if expected and expected != sha256(labels_path):
            raise ValueError('Nhãn T07 khác bản đã được bàn giao; kiểm định lại T07/manifest trước.')
    tracked += [labels_path, label_summary_path]
    return dict(inputs={relative_path(p):sha256(p) for p in tracked}, t08_inputs=sources), labels[LABEL_COLUMNS].copy()


def attach_labels(nodes, labels, settings):
    result = nodes.merge(labels, on='address', how='left', validate='many_to_one', indicator=True)
    result['flag_missing_label'] = result.pop('_merge').eq('left_only')
    for column in ['entity_name','entity_type','class','public_category','confidence','source_url','contract_status_as_of']:
        result[column] = result[column].fillna('Unknown' if column in ['entity_name','entity_type'] else '')
    result['is_contract'] = result.is_contract.astype('boolean')
    result['flag_contract_status_unknown'] = result.is_contract.isna()
    tokens = pd.concat([result[c].str.strip().str.lower() for c in ['entity_type','class','public_category']],axis=1)
    result['flag_exchange'] = tokens.isin(['cex','dex','exchange','centralized exchange','decentralized exchange']).any(axis=1)
    result['flag_bridge'] = tokens.isin(['bridge','cross-chain bridge']).any(axis=1)
    result['flag_contract'] = result.is_contract.fillna(False).astype(bool) | tokens.isin(['contract','smart contract']).any(axis=1)
    result['flag_zero_address'] = result.address.eq('0x'+'0'*40)
    result['flag_label_conflict'] = result.label_conflict_review.astype('boolean').fillna(False).astype(bool)
    result['flag_unattributed'] = ~result.is_entity_attributed.astype('boolean').fillna(False).astype(bool)
    result['flag_other_attributed_entity'] = ~result.flag_unattributed & ~(
        result.flag_exchange | result.flag_bridge | result.flag_contract)
    reasons = {name: result[name] for name in ['flag_exchange','flag_bridge','flag_contract',
        'flag_zero_address','flag_label_conflict','flag_missing_label','flag_contract_status_unknown']}
    if settings['exclude_other_attributed_entities']:
        reasons['flag_other_attributed_entity'] = result.flag_other_attributed_entity
    result['exclusion_reason'] = ''
    for reason, mask in reasons.items():
        result.loc[mask,'exclusion_reason'] += reason.removeprefix('flag_')+';'
    result['exclusion_reason'] = result.exclusion_reason.str.rstrip(';')
    result['eligible_for_whale_ranking'] = result.exclusion_reason.eq('')
    result['label_policy'] = settings['label_policy']
    return result


def standardize(values):
    """Population z, ddof=0; nhóm rỗng/hằng có z=0, được ghi cờ riêng."""
    mean = float(values.mean()) if len(values) else 0.
    std = float(values.std(ddof=0)) if len(values) else 0.
    z = (values-mean)/std if std > 0 else pd.Series(0.,index=values.index)
    return z, mean, std


def score_window(frame, meta, window, settings):
    output = frame.copy()
    parameters = []
    for scope, mask in [('all', pd.Series(True,index=output.index)),
                        ('eligible',output.eligible_for_whale_ranking)]:
        zcolumns = []
        for component, key in COMPONENTS.items():
            name = f'z_{component}'+('_all' if scope=='all' else '')
            output[name] = np.nan
            z, mean, std = standardize(output.loc[mask,settings[key]])
            output.loc[mask,name] = z
            zcolumns.append(name)
            parameters.append(dict(window_type=window, **meta, scope=scope, component=component,
                source_column=settings[key], n_population=int(mask.sum()), mean=mean, std=std,
                ddof=0, is_degenerate=std==0))
        score = 'whale_score_all' if scope=='all' else 'whale_score'
        rank = 'rank_all' if scope=='all' else 'whale_rank'
        output[score] = output[zcolumns].sum(axis=1,min_count=3)
        output[rank] = output[score].rank(ascending=False,method='min').astype('Int64')
    output['value'] = output[settings['value_column']]
    output['weighted_degree'] = output[settings['weighted_degree_column']]
    return output, parameters


def validate_scores(output, original, meta, window, settings):
    """Đối chiếu công thức bằng NumPy, dân số, rank và loại trừ ở từng cửa sổ."""
    ok = (output.address.tolist()==original.address.tolist() and
        not output.address.duplicated().any() and len(output)==len(original))
    max_error = 0.
    for scope in ['all','eligible']:
        mask = np.ones(len(output),dtype=bool) if scope=='all' else output.eligible_for_whale_ranking.to_numpy()
        columns = [settings[key] for key in COMPONENTS.values()]
        matrix = output.loc[mask,columns].to_numpy(dtype=float)
        if len(matrix):
            mean = np.mean(matrix,axis=0); std = np.std(matrix,axis=0,ddof=0)
            expected_z = np.divide(matrix-mean,std,out=np.zeros_like(matrix),where=std>0)
            names = [f'z_{c}'+('_all' if scope=='all' else '') for c in COMPONENTS]
            error = float(np.max(np.abs(expected_z-output.loc[mask,names].to_numpy())))
            max_error = max(max_error,error)
            expected = expected_z.sum(axis=1)
            scores = output.loc[mask,'whale_score_all' if scope=='all' else 'whale_score'].to_numpy()
            ok &= bool(np.allclose(expected,scores,rtol=1e-12,atol=1e-10))
            ranks = output.loc[mask,'rank_all' if scope=='all' else 'whale_rank'].to_numpy(dtype=np.int64)
            # Minimum rank = count of strictly larger scores + 1, using unique score bins.
            unique, inverse, counts = np.unique(scores,return_inverse=True,return_counts=True)
            reference_ranks = (len(scores)-np.cumsum(counts)+1)[inverse]
            ok &= bool(np.array_equal(ranks,reference_ranks) and np.isfinite(scores).all())
    excluded = ~output.eligible_for_whale_ranking
    ok &= bool(output.loc[excluded,['whale_score','whale_rank','z_value','z_weighted_degree','z_pagerank']].isna().all().all())
    prohibited = output[['flag_exchange','flag_bridge','flag_contract','flag_zero_address',
        'flag_label_conflict','flag_missing_label','flag_contract_status_unknown']].any(axis=1)
    ok &= not bool((output.eligible_for_whale_ranking & prohibited).any())
    ok &= max_error <= 1e-10
    return dict(window_type=window, **meta,n_nodes_in=len(original),n_nodes_out=len(output),
        n_eligible=int((~excluded).sum()),n_excluded=int(excluded.sum()),
        max_z_error=max_error,status='PASS' if ok else 'FAIL')


def run(folder, cfg, settings, labels):
    folder.mkdir(parents=True,exist_ok=True)
    all_parameters = []; validations = []; shapes = {}
    directory = project_path(cfg['data']['processed_t09_dir'])
    for window in ['daily','weekly']:
        nodes = pd.read_parquet(directory/f'node_metrics_{window}.parquet').sort_values(['time_window','address']).reset_index(drop=True)
        snapshots = pd.read_parquet(directory/f'snapshot_metrics_{window}.parquet')
        calendar = calendar_metadata(window,cfg)
        if snapshots.time_window.tolist()!=calendar.time_window.tolist() or nodes.duplicated(['time_window','address']).any():
            raise ValueError('T09 sai lịch hoặc trùng khóa node.')
        if not nodes.window_type.eq(window).all() or set(nodes.time_window)-set(calendar.time_window):
            raise ValueError('T09 chứa cửa sổ ngoài lịch.')
        values = nodes[[settings[key] for key in COMPONENTS.values()]].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values<0).any():
            raise ValueError('T12 không chấp nhận giá trị thiếu, vô hạn hoặc âm từ T09.')
        joined = attach_labels(nodes,labels,settings)
        groups = {str(k):v for k,v in joined.groupby('time_window',sort=True)}
        frames = []; stats = []
        for i,meta in enumerate(calendar.to_dict('records')):
            frame = groups.get(meta['time_window'],joined.iloc[:0]).copy()
            for column in ['days_in_window','is_partial_week','eligible_for_regression']:
                if not frame[column].eq(meta[column]).all():
                    raise ValueError('T09 metadata cửa sổ không khớp lịch.')
            output, parameters = score_window(frame,meta,window,settings)
            check = validate_scores(output,frame,meta,window,settings)
            if check['status']!='PASS':
                raise ValueError(f'T12 sai công thức: {window}/{meta["time_window"]}')
            check['n_unattributed_eligible'] = int((output.eligible_for_whale_ranking & output.flag_unattributed).sum())
            stats.append({**check,**{f'n_{flag.removeprefix("flag_")}':int(output[flag].sum()) for flag in output if flag.startswith('flag_')}})
            validations.append(check); all_parameters.extend(parameters); frames.append(output)
            if i%100==0:
                print(f'T12 {window}: {i+1}/{len(calendar)}',flush=True)
        table = pd.concat(frames,ignore_index=True)
        table.to_parquet(folder/f'whale_scores_{window}.parquet',index=False)
        pd.DataFrame(stats).to_parquet(folder/f'snapshot_metrics_{window}.parquet',index=False)
        shapes[window] = dict(rows=len(table),snapshots=len(calendar),
            eligible_node_windows=int(table.eligible_for_whale_ranking.sum()),
            excluded_node_windows=int((~table.eligible_for_whale_ranking).sum()),
            eligible_unique_addresses=int(table.loc[table.eligible_for_whale_ranking,'address'].nunique()),
            partial_weeks=int(calendar.is_partial_week.sum()))
    pd.DataFrame(all_parameters).to_parquet(folder/'t12_standardization.parquet',index=False)
    pd.DataFrame(validations).to_parquet(folder/'t12_validation.parquet',index=False)
    return shapes


def main():
    cfg = read_config(); settings = read_config(SETTINGS_FILE)
    if settings['standard_deviation_ddof']!=0 or settings['pagerank_column']!='pagerank':
        raise ValueError('Đặc tả T12 yêu cầu population z và PageRank gốc T09.')
    if settings['value_column']==settings['weighted_degree_column']:
        raise ValueError('Value và WeightedDegree trùng cột, cần quyết định trọng số rõ ràng trước.')
    folder = checked_path(settings['output_dir'])
    provenance, labels = verify_inputs(cfg)
    code_hash = sha256(Path(__file__))
    settings_hash = sha256(SETTINGS_FILE)
    write_json(folder/'t12_summary.json',dict(ready_for_downstream=False))
    shapes = run(folder,cfg,settings,labels)
    hashes = {name:dict(run1=sha256(folder/name)) for name in OUTPUT_NAMES}
    cache = ROOT/'.cache'; cache.mkdir(exist_ok=True)
    temporary = cache/f't12_repro_{uuid.uuid4().hex}'
    temporary.mkdir()
    try:
        probe = temporary/'write_probe'; probe.write_bytes(b'ok'); probe.unlink()
        run(temporary,cfg,settings,labels)
        for name in OUTPUT_NAMES:
            hashes[name]['run2'] = sha256(temporary/name)
    finally:
        if not temporary.resolve().is_relative_to(cache.resolve()):
            raise ValueError('Refuse cleanup outside project cache.')
        shutil.rmtree(temporary)
    same = all(proof['run1']==proof['run2'] for proof in hashes.values())
    after,_ = verify_inputs(cfg)
    if provenance!=after or code_hash!=sha256(Path(__file__)) or settings_hash!=sha256(SETTINGS_FILE):
        raise ValueError('Nguồn hoặc code/config đã đổi trong lúc chạy.')
    write_json(folder/'t12_reproducibility.json',dict(all_match=same,hashes=hashes))
    validation = pd.read_parquet(folder/'t12_validation.parquet')
    summary = dict(task='T12',ready_for_downstream=False,settings=settings,settings_sha256=settings_hash,
        code_sha256=code_hash,**provenance,shapes=shapes,validation_pass=int(validation.status.eq('PASS').sum()),
        formula='z(value) + z(weighted_degree) + z(pagerank)',
        normalization='Per window; ddof=0; all and eligible populations standardized separately; no log/winsorization.',
        identity_caveat='High centrality does not identify an individual investor or measure wealth/holdings.',
        label_caveat='Static retrospective T07 labels as of study end; not historically point-in-time identity evidence.')
    write_json(folder/'t12_summary.json',summary)
    if not same:
        raise ValueError('T12 không khớp hash hai lượt.')
    from scripts.validate_t12_current import main as review
    review()
    print(json.dumps(dict(shapes=shapes,reproducibility=same),indent=2),flush=True)
