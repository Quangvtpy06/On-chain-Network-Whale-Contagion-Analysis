"""I/O T18: chỉ đọc release upstream, khóa hash, không sửa gate hay output T15/T16."""
import argparse
import importlib.metadata
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analysis_release import SOURCE_FILES as UPSTREAM_SOURCE_FILES, frame_hash
from src.forecast_inputs import (ROOT, allowed, file_hash, hash_paths, json_write, load_t14,
                                 local_path, read_config, relative_path, require, verify_hashes)
from src import time_split_backtest as bt

SOURCE_FILES = ['T18_Time_Split_Backtest.py', 'src/time_split_backtest.py', 'src/t18_release.py',
                'scripts/validate_t18_release.py', 'scripts/prepare_t18_release.py']


def upstream_outputs(task):
    if task == 't15':
        return {'t15_volatility_regression_results.parquet', 't15_volatility_regression_summary.parquet',
                't15_sample_membership.parquet', 't15_validation.parquet', 't15_report.md', 't15_flow_coefficients.png'}
    return {'t16_event_study_results.parquet', 't16_event_selection.parquet', 't16_event_windows.parquet',
            't16_event_candidates.parquet', 't16_validation.parquet', 't16_report.md'} | {
            f't16_{event}_response.png' for event in bt.EVENTS}


def verify_upstream(task, config, folder, gate, t14_hashes):
    config, folder = local_path(config), local_path(folder)
    cfg = read_config(config)
    require(folder == local_path(cfg['output_dir']), 'Upstream output/config path mismatch')
    summary_path, review_path = folder / f'{task}_summary.json', folder / f'{task}_independent_review.json'
    # A set is used for membership checks; sort it before constructing serialized hash maps.
    files = [summary_path, review_path, config] + [folder / n for n in sorted(upstream_outputs(task))]
    before = hash_paths(files)
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    review = json.loads(review_path.read_text(encoding='utf-8'))
    require(summary.get('computation_validated') is True and review.get('all_pass') is True, 'Unaccepted upstream ' + task)
    require(summary['parameters'] == cfg and summary['protocol_id'] == cfg['protocol_id'], 'Upstream config changed')
    sources = hash_paths([ROOT / p for p in UPSTREAM_SOURCE_FILES] + [config])
    require(summary['source_config_sha256'] == review['source_config_sha256'] == sources, 'Upstream source/config not bound')
    require(review['summary_sha256'] == file_hash(summary_path), 'Upstream summary differs from accepted review')
    require(set(summary['output_sha256']) == upstream_outputs(task), 'Incomplete upstream output list')
    require(summary['output_sha256'] == review['output_sha256'], 'Upstream review/output disagreement')
    require(summary['input_sha256'] == review['input_sha256'], 'Upstream input provenance disagreement')
    expected_tables = {n for n in upstream_outputs(task) if n.endswith('.parquet')}
    require(set(summary['content_hashes']) == set(review['content_hashes']) == expected_tables,
            'Incomplete upstream table reproduction evidence')
    for name, expected in summary['output_sha256'].items():
        require(file_hash(folder / name) == expected, 'Changed upstream output: ' + name)
    for name, expected in t14_hashes.items():
        require(summary['input_sha256'].get(name) == expected, 'Upstream T14 release differs: ' + name)
    for name, pair in summary['content_hashes'].items():
        require(pair['run1'] == pair['run2'] == review['content_hashes'].get(name), 'Upstream reproduction disagreement')
    require(summary['policy'] == gate['policy'], 'Upstream information scope changed')
    require(summary['rq3_answered'] is False and summary['ready_for_individual_investor_inference'] is False,
            'Unsupported upstream research claim')
    verify_hashes(summary['input_sha256']); verify_hashes(sources); verify_hashes(before)
    return cfg, before, sources


def load(cfg):
    f, e, summary, gate, hashes = load_t14(cfg)
    cfg15, h15, s15 = verify_upstream('t15', cfg['t15_config'], cfg['t15_dir'], gate, hashes)
    cfg16, h16, s16 = verify_upstream('t16', cfg['t16_config'], cfg['t16_dir'], gate, hashes)
    folder = local_path(cfg['t16_dir'])
    selection = pd.read_parquet(folder / 't16_event_selection.parquet')
    windows = pd.read_parquet(folder / 't16_event_windows.parquet')
    for frame, columns in [(selection, ['date']), (windows, ['event_date', 'event_available_at', 'response_date'])]:
        for col in columns:
            frame[col] = pd.to_datetime(frame[col], utc=True).dt.as_unit('ns')
            require(frame[col].notna().all() and frame[col].eq(frame[col].dt.normalize()).all(), 'Invalid UTC event calendar')
    require((windows.event_available_at == windows.event_date + pd.Timedelta(days=1)).all(), 'Invalid event cutoff')
    require(not selection.duplicated(['event_type', 'selection_policy', 'date']).any(), 'Duplicate upstream selection')
    require(not windows.duplicated(['event_type', 'selection_policy', 'event_date', 'tau']).any(), 'Duplicate upstream event window')
    verify_hashes(h15); verify_hashes(h16)
    return (f, e, summary, gate, cfg15, cfg16, selection, windows), {**hashes, **h15, **h16}, {**s15, **s16}


def validate_tables(loaded, cfg, tables, exercise_leakage=True):
    f, _, _, _, cfg15, cfg16, _, _ = loaded
    member = tables['t18_sample_membership.parquet']
    coeff = tables['t18_coefficients.parquet']
    pred = tables['t18_predictions.parquet']
    _, start, fit, evaluation = bt.timestamps(cfg)
    rows = []

    def check(name, ok, detail='', scope='all'):
        require(bool(ok), name + ': ' + str(detail))
        rows.append(dict(check=name, scope=scope, status='PASS', detail=str(detail)))

    for (branch, h), group in member.groupby(['branch', 'horizon_h']):
        scope = f'{branch}:h{h}'
        train = group[group.train_selected]
        check('train_labels_available_at_fit', train.target_available_at.le(fit).all(), scope=scope)
        check('train_features_available_at_fit', train.available_at.le(fit).all(), scope=scope)
        check('no_test_row_used_for_training', train.coarse_split.eq('train').all(), scope=scope)
        check('unavailable_labels_purged', not group.loc[group.purged, 'train_selected'].any(), int(group.purged.sum()), scope)
        cp = coeff[coeff.branch.eq(branch) & coeff.horizon_h.eq(h)]
        check('matched_training_sample_models', cp.n_obs.nunique() == 1 and cp.n_obs.iloc[0] == len(train), scope=scope)
        pp = pred[pred.branch.eq(branch) & pred.horizon_h.eq(h)]
        check('model_fitted_before_every_forecast', pp.available_at.ge(fit).all(), scope=scope)
        check('target_starts_after_predictor_window', pp.target_date.ge(pp.available_at).all(), scope=scope)
        check('evaluation_truth_available', pp.loc[pp.evaluate, 'target_available_at'].le(evaluation).all(), scope=scope)
        check('matched_test_dates_models', pp.groupby('date').model.nunique().eq(len(bt.MODELS)).all(), scope=scope)
        check('unique_forecast_keys', not pp.duplicated(['date', 'model']).any(), scope=scope)
        # Direct RV-day lookup, not shift from production target construction.
        reference = f.set_index('date').rv.reindex(group.target_date).to_numpy(float)
        expected = np.log(np.where(reference > 0, reference, np.nan))
        observed = f[f'target_log_rv_h{h}'].to_numpy(float)
        check('target_equals_direct_future_rv_day', np.allclose(expected, observed, equal_nan=True), scope=scope)
    part = tables['t18_event_partition.parquet']
    train_end, test_start, _, _ = bt.timestamps(cfg)
    check('event_train_windows_inside_train', part.loc[part.partition.eq('train'), 'window_end'].le(train_end).all())
    check('event_test_windows_inside_test', part.loc[part.partition.eq('test'), 'window_start'].ge(test_start).all())
    check('event_test_responses_observable_at_evaluation',
          (part.loc[part.partition.eq('test'), 'window_end']+pd.Timedelta(days=1)).le(evaluation).all())
    stats = tables['t18_event_statistics.parquet']
    check('insufficient_event_ci_is_missing', stats.loc[stats.ci_status.eq('insufficient_events'), ['ci_lower','ci_upper']].isna().all().all())
    check('all_event_types_retained_even_if_empty', set(stats.event_type) == set(bt.EVENTS))
    check('no_infinite_predictions', np.isfinite(pred.prediction_log_rv).all())
    if exercise_leakage:
        # Hindsight labels beyond fit_at may change evaluation, never coefficients or forecasts.
        changed = f.copy()
        for h in cfg15['horizons']:
            future = changed.date + pd.Timedelta(days=h+1) > fit
            col = f'target_log_rv_h{h}'
            changed.loc[future, col] = changed.loc[future, col] * 9 + 100
        fresh = bt.ledger(changed, loaded[1], loaded[2], loaded[3], cfg15, cfg)
        cf, pf = bt.forecast(changed, fresh, cfg15, cfg)
        check('future_target_mutation_does_not_change_coefficients', frame_hash(cf) == frame_hash(coeff))
        columns = ['branch','horizon_h','model','date','prediction_log_rv']
        check('future_target_mutation_does_not_change_forecasts', frame_hash(pf[columns]) == frame_hash(pred[columns]))
        cut = pd.Timestamp(cfg['leakage_check_cut_date'], tz='UTC')
        require(start < cut < f.date.max(), 'Leakage cutoff outside test')
        prefix = f[f.date.le(cut)].reset_index(drop=True)
        ep = loaded[1].iloc[:len(prefix)].reset_index(drop=True)
        ml = bt.ledger(prefix, ep, loaded[2], loaded[3], cfg15, cfg)
        cf, pf = bt.forecast(prefix, ml, cfg15, cfg)
        check('future_rows_removed_does_not_change_coefficients', frame_hash(cf) == frame_hash(coeff))
        earlier = pred[pred.date.le(cut)][columns].reset_index(drop=True)
        prior = pf[columns].reset_index(drop=True)
        keys = columns[:-1]
        same = len(prior) == len(earlier) and prior[keys].equals(earlier[keys]) and np.allclose(
            prior.prediction_log_rv, earlier.prediction_log_rv, rtol=1e-12, atol=1e-12)
        check('future_rows_removed_does_not_change_prior_forecasts',
              same, 'Numeric tolerance 1e-12: BLAS accumulation may differ with matrix row count')
    return pd.DataFrame(rows)


def report(cfg, tables):
    lines = ['# T18 — purged fixed-origin pseudo-OOS', '',
        f'Protocol: {cfg["protocol_id"]}. Train feature end: {cfg["split"]["train_feature_end"]}; '
        f'test start: {cfg["split"]["test_feature_start"]}; fit at: {cfg["split"]["fit_at"]}.',
        'Retrospective backtest: the test period was already inspected in full-sample analyses.',
        'No retuning, no causal claim, no individual-investor inference. Coefficients remain fixed through test.',
        'CEX scope is observed approved subset; cohort policy is T12 v2 research knowledge.', '',
        '| Branch | h | Train | Purged | Test evaluated | RMSE controls | RMSE flow | R2 flow vs controls |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    member, metrics = tables['t18_sample_membership.parquet'], tables['t18_metrics.parquet']
    for r in metrics[metrics.model.eq('flow_model')].itertuples():
        baseline = metrics[metrics.branch.eq(r.branch) & metrics.horizon_h.eq(r.horizon_h) & metrics.model.eq('controls_baseline')].iloc[0]
        purged = int(member.loc[member.branch.eq(r.branch) & member.horizon_h.eq(r.horizon_h), 'purged'].sum())
        lines.append(f'| {r.branch} | {r.horizon_h} | {r.n_train} | {purged} | {r.n_test} | {baseline.rmse:.6f} | '
                     f'{r.rmse:.6f} | {r.r2_vs_controls_forecast:.6f} |')
    lines += ['', 'R2 vs test mean is a scoring normalization, not an available forecasting benchmark.',
        'Train-mean, persistence and HAR forecasts are also scored on exactly the same days.',
        'Loss difference = flow squared error minus controls squared error: negative favors flow.',
        'Paired circular time-block intervals are exploratory; Bonferroni intervals cover the six predeclared comparisons '
        'approximately under bootstrap assumptions. No nested-model significance claim is made.', '',
        '| Branch | h | Mean loss difference | Pointwise 95% block CI |', '|---|---:|---:|---|']
    for row in tables['t18_loss_comparison.parquet'].itertuples():
        ci=f'[{row.ci_lower:.6f}, {row.ci_upper:.6f}]' if row.ci_status=='available_exploratory' else row.ci_status
        lines.append(f'| {row.branch} | {row.horizon_h} | {row.mean_loss_difference:.6f} | {ci} |')
    lines += ['', '## Event holdout (primary nonoverlap)', '', '| Event | Train | Test | Boundary excluded |', '|---|---:|---:|---:|']
    counts = tables['t18_event_counts.parquet']
    for event in bt.EVENTS:
        sub = counts[counts.event_type.eq(event) & counts.selection_policy.eq('nonoverlap')].set_index('partition')
        lines.append(f'| {event} | {sub.loc["train","n_events"]} | {sub.loc["test","n_events"]} | {sub.loc["boundary_excluded","n_events"]} |')
    lines += ['', 'Event selection and thresholds are inherited unchanged from verified T16; full response windows must be inside a split.',
        'Zero/insufficient events are reported explicitly. Event paths/post-pre contrasts are descriptive, not forecasts or causal effects.',
        'Missing CI never implies no response. Flows only describe the thresholded >=500,000 USDT transfer subnetwork.']
    return '\n'.join(lines)+'\n'


def figures(tables, folder):
    plt.rcParams.update({'font.family':'DejaVu Sans','axes.spines.top':False,'axes.spines.right':False})
    metrics = tables['t18_metrics.parquet']
    fig, axes = plt.subplots(1,2,figsize=(11,4),constrained_layout=True)
    for ax, branch in zip(axes,['activity_cohort','cex']):
        for model,color in [('controls_baseline','#DB7C26'),('flow_model','#117A8B'),('har_baseline','#687782')]:
            sub=metrics[metrics.branch.eq(branch)&metrics.model.eq(model)].sort_values('horizon_h')
            ax.plot(sub.horizon_h,sub.rmse,'o-',label=model,color=color)
        ax.set(title=branch,xlabel='Horizon (days)',ylabel='Test RMSE (log RV)');ax.set_xticks([1,3,7]);ax.legend(fontsize=8)
    first=folder/'t18_oos_rmse.png';fig.savefig(first,dpi=160,metadata={'Software':'crypto-analysis'});plt.close(fig)
    counts=tables['t18_event_counts.parquet'];fig,ax=plt.subplots(figsize=(10,4),constrained_layout=True)
    x=np.arange(len(bt.EVENTS))
    for j,part,color in [(0,'train','#687782'),(1,'test','#117A8B'),(2,'boundary_excluded','#DB7C26')]:
        sub=counts[counts.selection_policy.eq('nonoverlap')&counts.partition.eq(part)].set_index('event_type').reindex(bt.EVENTS)
        bars=ax.bar(x+(j-1)*.25,sub.n_events,width=.25,label=part,color=color);ax.bar_label(bars,padding=2)
    ax.set_xticks(x);ax.set_xticklabels(['Activity cohort','CEX net inflow','Concentration','Large transfer']);ax.set(ylabel='Primary events',title='T18: complete event windows by split');ax.legend()
    second=folder/'t18_event_holdout_counts.png';fig.savefig(second,dpi=160,metadata={'Software':'crypto-analysis'});plt.close(fig)
    return [first,second]


def run(config='config/t18.yaml', output_dir=None):
    path=local_path(config);cfg=read_config(path);folder=local_path(output_dir or cfg['output_dir']);folder.mkdir(parents=True,exist_ok=True)
    sources=hash_paths([ROOT/n for n in SOURCE_FILES]+[path])
    loaded, hashes, deps=load(cfg)
    tables=bt.compute(loaded,cfg)
    checks=validate_tables(loaded,cfg,tables)
    loaded2, hashes2, deps2=load(cfg)
    require(hashes==hashes2 and deps==deps2,'Inputs changed between runs')
    again=bt.compute(loaded2,cfg)
    repro={name:dict(run1=frame_hash(table),run2=frame_hash(again[name])) for name,table in tables.items()}
    require(all(v['run1']==v['run2'] for v in repro.values()),'Internal reproduction failed')
    tables['t18_validation.parquet']=checks
    for name,table in tables.items():table.to_parquet(folder/name,index=False)
    rp=folder/'t18_report.md';rp.write_text(report(cfg,tables),encoding='utf-8')
    images=figures(tables,folder)
    verify_hashes(sources);verify_hashes(deps);verify_hashes(hashes)
    summary=dict(protocol_id=cfg['protocol_id'],parameters=cfg,contract_version=cfg['contract_version'],
        computation_validated=True,independent_review_required=True,upload_performed=False,
        rq3_answered=False,ready_for_individual_investor_inference=False,causal_claim=False,untouched_holdout=False,
        policy=loaded[3]['policy'],source_config_sha256=sources,dependency_source_sha256=deps,input_sha256=hashes,
        versions={p:importlib.metadata.version(p) for p in ['numpy','pandas','pyarrow','statsmodels','matplotlib']},
        content_hashes=repro,validation_pass=len(checks),n_rows={n:len(t) for n,t in tables.items()},
        output_sha256={p.name:file_hash(p) for p in [folder/n for n in tables]+[rp]+images})
    json_write(folder/'t18_summary.json',summary)
    print(f'T18: validated; {len(checks)} PASS; output={relative_path(folder)}')
    return summary


def cli():
    parser=argparse.ArgumentParser(description='T18 purged fixed-origin backtest')
    parser.add_argument('--config',default='config/t18.yaml');parser.add_argument('--output-dir')
    args=parser.parse_args();run(args.config,args.output_dir)
