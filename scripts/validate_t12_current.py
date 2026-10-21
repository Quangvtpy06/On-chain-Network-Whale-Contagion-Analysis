"""Nghiệm thu T12: nguồn T07/T09, phân loại và phương trình z độc lập NumPy."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.graph_config import read_config, project_path, relative_path
from src.node_centrality import sha256, write_json, calendar_metadata
from src.whale_score import verify_inputs, SETTINGS_FILE, COMPONENTS, OUTPUT_NAMES, LABEL_COLUMNS


def reference_flags(row, settings):
    """Reference on unique addresses; no call to production label attachment."""
    missing=row is None
    tokens=set() if missing else {str(row[c]).strip().casefold() for c in ['entity_type','class','public_category']}
    unknown=missing or pd.isna(row['is_contract'])
    exchange=bool(tokens & {'cex','dex','exchange','centralized exchange','decentralized exchange'})
    bridge=bool(tokens & {'bridge','cross-chain bridge'})
    contract=(not unknown and bool(row['is_contract'])) or bool(tokens & {'contract','smart contract'})
    zero=False if missing else row['address']=='0x'+'0'*40
    conflict=False if missing or pd.isna(row['label_conflict_review']) else bool(row['label_conflict_review'])
    unattributed=True if missing or pd.isna(row['is_entity_attributed']) else not bool(row['is_entity_attributed'])
    other=not unattributed and not (exchange or bridge or contract)
    values=dict(flag_exchange=exchange,flag_bridge=bridge,flag_contract=contract,
        flag_zero_address=zero,flag_label_conflict=conflict,flag_missing_label=missing,
        flag_contract_status_unknown=unknown,flag_unattributed=unattributed,
        flag_other_attributed_entity=other)
    excluded=exchange or bridge or contract or zero or conflict or missing or unknown or (
        settings['exclude_other_attributed_entities'] and other)
    values['eligible_for_whale_ranking']=not excluded
    return values


def main():
    cfg=read_config(); settings=read_config(SETTINGS_FILE); folder=project_path(settings['output_dir'])
    summary=json.loads((folder/'t12_summary.json').read_text(encoding='utf-8'))
    provenance,labels=verify_inputs(cfg)
    if summary['inputs']!=provenance['inputs'] or summary['t08_inputs']!=provenance['t08_inputs'] or summary['settings_sha256']!=sha256(SETTINGS_FILE) or summary['code_sha256']!=sha256(ROOT/'src/whale_score.py'):
        raise ValueError('T12 source/code/config provenance changed.')
    proof=json.loads((folder/'t12_reproducibility.json').read_text(encoding='utf-8'))
    if not proof.get('all_match') or set(proof['hashes'])!=set(OUTPUT_NAMES):
        raise ValueError('T12 incomplete reproducibility proof.')
    for name in OUTPUT_NAMES:
        if not sha256(folder/name)==proof['hashes'][name]['run1']==proof['hashes'][name]['run2']:
            raise ValueError('T12 artifacts differ from the reproduced run.')
    parameters=pd.read_parquet(folder/'t12_standardization.parquet')
    if parameters.duplicated(['window_type','time_window','scope','component']).any():
        raise ValueError('Duplicate normalization parameters.')
    reference=pd.DataFrame([dict(address=r['address'],**reference_flags(r,settings)) for r in labels.to_dict('records')]).set_index('address')
    reports=[]
    for window in ['daily','weekly']:
        actual=pd.read_parquet(folder/f'whale_scores_{window}.parquet').sort_values(['time_window','address']).reset_index(drop=True)
        original=pd.read_parquet(project_path(cfg['data']['processed_t09_dir'])/f'node_metrics_{window}.parquet').sort_values(['time_window','address']).reset_index(drop=True)
        snapshots=pd.read_parquet(folder/f'snapshot_metrics_{window}.parquet')
        calendar=calendar_metadata(window,cfg)
        if not actual[original.columns].equals(original) or actual.duplicated(['time_window','address']).any():
            raise ValueError('T12 changed/dropped/added original T09 rows or metrics.')
        if not snapshots.time_window.tolist()==calendar.time_window.tolist():
            raise ValueError('T12 lost a calendar snapshot.')
        joined_labels=labels.set_index('address').reindex(actual.address).reset_index()
        if not actual[LABEL_COLUMNS].equals(joined_labels[LABEL_COLUMNS]):
            raise ValueError('T12 labels differ from the T07 lookup.')
        refs=reference.reindex(actual.address)
        if refs.isna().any().any():
            raise ValueError('Missing T07 reference labels; review before release.')
        if any(not np.array_equal(actual[c].to_numpy(),refs[c].to_numpy()) for c in reference):
            raise ValueError('T12 entity flags/filter differ from independent reference.')
        grouped={k:v for k,v in actual.groupby('time_window')}
        for meta in calendar.to_dict('records'):
            key=meta['time_window']; sub=grouped.get(key,actual.iloc[:0]); error=0.; ok=True
            for name in ['days_in_window','is_partial_week','eligible_for_regression']:
                ok &= bool(sub[name].eq(meta[name]).all())
                ok &= bool(snapshots.set_index('time_window').loc[key,name]==meta[name])
            for scope in ['all','eligible']:
                selected=sub if scope=='all' else sub.loc[sub.eligible_for_whale_ranking]
                matrix=selected[[settings[k] for k in COMPONENTS.values()]].to_numpy(dtype=float)
                # A separate summation path (stdlib fsum), rather than production
                # pandas/NumPy reductions. Analytic pytest examples anchor ddof/formula.
                mean=np.array([math.fsum(matrix[:,j])/len(matrix) for j in range(3)]) if len(matrix) else np.zeros(3)
                std=np.array([math.sqrt(math.fsum((float(v)-mean[j])**2 for v in matrix[:,j])/len(matrix)) for j in range(3)]) if len(matrix) else np.zeros(3)
                z=np.divide(matrix-mean,std,out=np.zeros_like(matrix),where=std>0)
                score_name='whale_score_all' if scope=='all' else 'whale_score'
                score=selected[score_name].to_numpy()
                if len(matrix):
                    error=max(error,float(np.max(abs(z.sum(axis=1)-score))))
                    for j,c in enumerate(COMPONENTS):
                        col='z_'+c+('_all' if scope=='all' else '')
                        ok &= bool(np.allclose(z[:,j],selected[col],rtol=1e-12,atol=1e-10))
                    rank_name='rank_all' if scope=='all' else 'whale_rank'
                    ranks=len(score)-np.searchsorted(np.sort(score),score,side='right')+1
                    ok &= bool(np.array_equal(ranks,selected[rank_name].to_numpy(dtype=int)))
                par=parameters[(parameters.window_type==window)&(parameters.time_window==key)&(parameters.scope==scope)].set_index('component')
                if len(par)!=3:
                    raise ValueError('Missing normalization parameter rows.')
                for j,c in enumerate(COMPONENTS):
                    r=par.loc[c]
                    ok &= bool(r.source_column==settings[COMPONENTS[c]] and r.n_population==len(matrix) and r.ddof==0 and
                        np.isclose(r['mean'],mean[j],rtol=1e-12,atol=1e-9) and
                        np.isclose(r['std'],std[j],rtol=1e-12,atol=1e-9) and r.is_degenerate==(std[j]==0))
            excluded=~sub.eligible_for_whale_ranking
            ok &= bool(sub.loc[excluded,['whale_score','whale_rank','z_value','z_weighted_degree','z_pagerank']].isna().all().all())
            ok &= bool(np.array_equal(sub.value,sub[settings['value_column']]) and
                np.array_equal(sub.weighted_degree,sub[settings['weighted_degree_column']]))
            ok &= error<=1e-10
            reports.append(dict(window_type=window,time_window=key,status='PASS' if ok else 'FAIL',max_score_error=error))
        print(f'T12 independent review {window}: {len(calendar)} snapshots',flush=True)
    validation=pd.read_parquet(folder/'t12_validation.parquet')
    all_pass=bool(len(validation)==len(reports) and validation.status.eq('PASS').all() and all(r['status']=='PASS' for r in reports))
    report=dict(all_pass=all_pass,windows_checked=len(reports),
        max_score_error=max(r['max_score_error'] for r in reports),
        flags_verified_against_t07=True,source_metrics_unchanged=True,
        validator_sha256=sha256(Path(__file__)),output_hashes={n:sha256(folder/n) for n in OUTPUT_NAMES},
        numerical_reference='stdlib math.fsum population moments; separate from production pandas reductions',
        validity_scope='Checks the specified mathematics and data joins; does not establish economic identity or construct validity.',
        identity_caveat='Eligible means passed infrastructure filters; it does not mean confirmed individual investor.')
    write_json(folder/'t12_review.json',report)
    summary['technical_validation_pass']=all_pass
    summary['ready_for_exploration']=all_pass
    # Economic/WhaleFlow readiness is a separate, explicitly evaluated audit gate.
    summary['ready_for_downstream']=False
    summary['ready_for_t14_t15']=False
    write_json(folder/'t12_summary.json',summary)
    print(json.dumps(report,indent=2),flush=True)
    if not all_pass:
        raise ValueError('T12 independent validation failed.')


if __name__=='__main__':
    main()
