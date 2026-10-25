"""Kiểm định T18 bằng dữ liệu thật; chạy riêng, không thay upstream hoặc cờ RQ3."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np
import pandas as pd
from src import time_split_backtest as bt
from src import t18_release as release
from src.forecast_inputs import (file_hash, hash_paths, json_write, local_path, read_config,
                                 require, verify_hashes)


def independent_checks(loaded, cfg, tables):
    f,e,upstream,gate,cfg15,cfg16,selection,windows=loaded
    member=tables['t18_sample_membership.parquet'];pred=tables['t18_predictions.parquet']
    coeff=tables['t18_coefficients.parquet'];metrics=tables['t18_metrics.parquet']
    end,start,fit,evaluation=bt.timestamps(cfg)
    results=[]
    for (branch,h),group in member.groupby(['branch','horizon_h']):
        group=group.reset_index(drop=True);opts=cfg15['branches'][branch]
        controls=cfg15['controls']+cfg15['extended_controls'];all_columns=controls+[opts['predictor']]
        outcome=f[f'target_log_rv_h{h}'].to_numpy(float)
        complete=np.isfinite(f[all_columns].to_numpy(float)).all(axis=1)
        ready=e[f'predictors_ready_{opts["eligibility"]}'].to_numpy(bool)
        eligible=e[f'eligible_{opts["eligibility"]}_h{h}'].to_numpy(bool)
        cutoff=pd.to_datetime(f.available_at,utc=True)
        label=f.date+pd.Timedelta(days=int(h)+1)
        independent_train=(f.date.le(end)&cutoff.le(fit)&label.le(fit)).to_numpy() & ready & eligible & complete & np.isfinite(outcome)
        require(np.array_equal(independent_train,group.train_selected.to_numpy()),'Independent training mask differs')
        independent_predict=f.date.ge(start).to_numpy() & cutoff.ge(fit).to_numpy() & cutoff.le(evaluation).to_numpy() & ready & complete
        independent_eval=independent_predict & np.isfinite(outcome) & eligible & label.le(evaluation).to_numpy()
        require(np.array_equal(independent_predict,group.predict_selected.to_numpy()),'Independent forecast mask differs')
        require(np.array_equal(independent_eval,group.evaluate_selected.to_numpy()),'Independent scoring mask differs')
        subset=pred[pred.branch.eq(branch)&pred.horizon_h.eq(h)]
        test=f.loc[independent_predict]
        train=f.loc[independent_train]
        for model,columns in [('controls_baseline',controls),('flow_model',all_columns),('har_baseline',cfg['har_controls'])]:
            x=np.column_stack([np.ones(len(train)),train[columns].to_numpy(float)])
            beta=np.linalg.lstsq(x,train[f'target_log_rv_h{h}'].to_numpy(float),rcond=None)[0]
            actual_coeff=coeff[coeff.branch.eq(branch)&coeff.horizon_h.eq(h)&coeff.model.eq(model)].set_index('variable').loc[['const']+columns]
            require(np.allclose(beta,actual_coeff.coef,rtol=1e-7,atol=1e-8),'Independent OLS differs')
            manual=np.column_stack([np.ones(len(test)),test[columns].to_numpy(float)])@beta
            saved=subset[subset.model.eq(model)].prediction_log_rv.to_numpy(float)
            require(np.allclose(manual,saved,rtol=1e-7,atol=1e-8),'Independent prediction differs')
        for model,expected in [('train_mean',np.full(len(test),train[f'target_log_rv_h{h}'].mean())),
                               ('last_log_rv',test.log_rv.to_numpy(float))]:
            require(np.allclose(subset[subset.model.eq(model)].prediction_log_rv,expected),'Invalid available benchmark')
        for model in bt.MODELS:
            pp=subset[subset.model.eq(model)&subset.evaluate]
            row=metrics[metrics.branch.eq(branch)&metrics.horizon_h.eq(h)&metrics.model.eq(model)].iloc[0]
            truth=f.set_index('date').loc[pp.date,f'target_log_rv_h{h}'].to_numpy(float)
            errors=truth-pp.prediction_log_rv.to_numpy(float)
            require(row.n_test==len(pp) and np.isclose(row.mse,np.mean(errors**2)),'Independent MSE differs')
            require(np.isclose(row.mae,np.mean(np.abs(errors))),'Independent MAE differs')
        results.append(dict(check='independent_availability_masks_matrix_fit_predictions_and_losses',
                            branch=branch,horizon_h=int(h),status='PASS'))
    chosen=selection[selection.selected].copy()
    partition=tables['t18_event_partition.parquet']
    require(len(chosen)==len(partition),'Event selection changed during holdout evaluation')
    for row in partition.itertuples():
        lo=row.event_date-pd.Timedelta(days=cfg16['window_days']);hi=row.event_date+pd.Timedelta(days=cfg16['window_days'])
        expected='train' if hi<=end else 'test' if lo>=start and hi+pd.Timedelta(days=1)<=evaluation else 'boundary_excluded'
        require(row.partition==expected,'Independent event partition differs')
    results.append(dict(check='independent_full_window_event_partition',status='PASS'))
    return results


def validate(config='config/t18.yaml',folder=None):
    path=local_path(config);cfg=read_config(path);folder=local_path(folder or cfg['output_dir'])
    summary_path=folder/'t18_summary.json';summary=json.loads(summary_path.read_text(encoding='utf-8'))
    require(summary['computation_validated'] is True and summary['parameters']==cfg,'Unaccepted/config-mismatched T18')
    require(summary['protocol_id']==cfg['protocol_id'] and summary['contract_version']==cfg['contract_version'],'Protocol mismatch')
    expected_sources=hash_paths([ROOT/n for n in release.SOURCE_FILES]+[path])
    require(summary['source_config_sha256']==expected_sources,'Incomplete or changed T18 source/config hashes')
    verify_hashes(summary['input_sha256']);verify_hashes(summary['dependency_source_sha256'])
    loaded,inputs,deps=release.load(cfg)
    require(summary['input_sha256']==inputs and summary['dependency_source_sha256']==deps,'Incomplete dependency provenance')
    require(summary['policy']==loaded[3]['policy'],'Changed information policy')
    for flag in ['rq3_answered','ready_for_individual_investor_inference','causal_claim','untouched_holdout']:
        require(summary.get(flag) is False,'Unsupported research claim: '+flag)
    tables=bt.compute(loaded,cfg);checks=release.validate_tables(loaded,cfg,tables)
    require(set(summary['content_hashes'])==set(tables),'Incomplete table hash map')
    hashes={name:release.frame_hash(frame) for name,frame in tables.items()}
    for name,value in hashes.items():
        require(summary['content_hashes'][name]=={'run1':value,'run2':value},'Reproduction differs: '+name)
    tables['t18_validation.parquet']=checks
    expected_outputs=set(tables)|{'t18_report.md','t18_oos_rmse.png','t18_event_holdout_counts.png'}
    require(set(summary['output_sha256'])==expected_outputs,'Incomplete output manifest')
    for name,expected in summary['output_sha256'].items():
        require(Path(name).name==name and file_hash(folder/name)==expected,'Changed output: '+name)
    for name,frame in tables.items():
        require(release.frame_hash(pd.read_parquet(folder/name))==release.frame_hash(frame),'Saved table differs: '+name)
    require((folder/'t18_report.md').read_text(encoding='utf-8')==release.report(cfg,tables),'Report differs')
    arithmetic=independent_checks(loaded,cfg,tables)
    verify_hashes(expected_sources);verify_hashes(inputs);verify_hashes(deps)
    result=dict(protocol_id=cfg['protocol_id'],all_pass=True,separate_process_recomputation=True,
        source_config_sha256=expected_sources,dependency_source_sha256=deps,input_sha256=inputs,
        summary_sha256=file_hash(summary_path),output_sha256=summary['output_sha256'],content_hashes=hashes,
        independent_arithmetic_checks=arithmetic,scope='Purged retrospective pseudo-OOS, not an untouched holdout or causal evidence.')
    json_write(folder/'t18_independent_review.json',result)
    return result


if __name__=='__main__':
    result=validate();print(json.dumps(dict(all_pass=True,independent_checks=len(result['independent_arithmetic_checks']))))
