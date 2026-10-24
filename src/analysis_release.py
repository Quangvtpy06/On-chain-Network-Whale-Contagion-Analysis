"""Ghi sản phẩm T15/T16, provenance và kiểm tra release dữ liệu thật."""
import argparse
import importlib.metadata
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.forecast_inputs import (ROOT, local_path, read_config, relative_path, hash_paths,
                                 verify_hashes, load_t14, require, json_write, file_hash)
from src import volatility_regression as regression, event_study as events

SOURCE_FILES = ['src/forecast_inputs.py', 'src/analysis_release.py', 'src/volatility_regression.py',
                'src/event_study.py', 'T15_Volatility_Regression.py', 'T16_Event_Study.py',
                'scripts/validate_t15_t16_release.py']


def inputs(cfg, task):
    f, e, summary, gate, hashes = load_t14(cfg)
    concentration = None
    if task == 't16':
        paths = [local_path(cfg[k]) for k in ['t11_snapshot', 't11_summary', 't11_reproducibility']]
        before = hash_paths(paths)
        concentration, t11 = events.load_concentration(cfg, f.date)
        require(t11['inputs']['daily_edges_parquet']['sha256'] ==
                gate['input_sha256']['data/processed/graphs/dynamic_edges_daily.parquet'], 'T11/T14 graph lineage differs')
        verify_hashes(before)
        hashes.update(before)
    return f, e, summary, gate, hashes, concentration


def calculate(task, cfg, loaded):
    f, e, summary, gate, hashes, concentration = loaded
    if task == 't15':
        return regression.compute(f, e, summary, gate, cfg)
    return events.compute(f, e, concentration, gate, cfg)


def frame_hash(df):
    import hashlib
    h = hashlib.sha256('|'.join(f'{c}:{t}' for c, t in zip(df.columns, df.dtypes)).encode())
    h.update(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes())
    return h.hexdigest()


def report(task, cfg, tables):
    lines = [f'# {task.upper()} — {cfg["protocol_id"]}', '',
        'Scope: observed approved CEX subset; activity cohort = unidentified high-activity addresses.',
        'Endpoint policy: public history as of day start; cohort policy: T12 v2 research knowledge.',
        'Transfers are restricted to the >=500,000 USDT whale subnetwork.',
        'No individual-investor identification, no causal claim, no out-of-sample forecasting claim.', '']
    if task == 't15':
        lines += ['OLS/Newey–West HAC; same dates and controls within every branch/horizon comparison.',
                  'Holm correction: six primary flow tests; six retrospective robustness tests form a separate family.',
                  'Retrospective predictors use end-of-period labels and are not forecasting evidence.', '',
                  '| Branch | h | n | R2 baseline | R2 primary | delta R2 | beta | p | p Holm |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        table = tables['t15_volatility_regression_summary.parquet']
        for r in table[table.model.eq('primary')].itertuples():
            baseline = r.r2 - r.delta_r2_vs_matched_baseline
            lines.append(f'| {r.branch} | {r.horizon_h} | {r.n_obs} | {baseline:.6f} | {r.r2:.6f} | '
                         f'{r.delta_r2_vs_matched_baseline:.6f} | {r.coefficient:.6f} | {r.p_value:.6f} | {r.p_holm:.6f} |')
        lines += ['', 'Horizon h is log RV of day D+h, not accumulated h-day RV. Predictors available D+1 00:00 UTC.',
                  'In-sample association and non-significance do not establish predictive ability or its absence.',
                  'CEX coverage is an observed subset, not complete exchange flow. Forecast evaluation belongs to T18.']
    else:
        lines += ['CEX net inflow and activity-cohort net inflow are separate event types; neither is gross inflow.',
                  'Signals of day D are available D+1 00:00 UTC; tau=0 is a same-day response, not a forecast.',
                  'Thresholds use earlier days only. Selection is earliest-event greedy cooldown >2k days.',
                  'Only full UTC response windows enter; unavailable signals remain distinct from zero events.',
                  'Circular moving-block bootstrap resamples whole event paths jointly, not individual tau values.',
                  'Block units are events, whose calendar spacing varies. Primary length=3; sensitivity=1 and 5.',
                  'Intervals are exploratory pointwise 95% intervals, not simultaneous bands or causal effects.',
                  'Small event samples and persistent market regimes limit interval reliability even after blocking.',
                  'CI is suppressed if n < max(minimum_events, 2*block_length). No tuning after looking at responses.', '',
                  '| Event | Candidates | Complete selected primary | Complete all-event sensitivity |',
                  '|---|---:|---:|---:|']
        cand, sel = tables['t16_event_candidates.parquet'], tables['t16_event_selection.parquet']
        for event in sorted(cand.event_type.unique()):
            group = sel[sel.event_type.eq(event)]
            n = int(cand.loc[cand.event_type.eq(event), 'candidate'].sum())
            primary = int(group.loc[group.selection_policy.eq('nonoverlap'), 'selected'].sum())
            all_n = int(group.loc[group.selection_policy.eq('all_events_sensitivity'), 'selected'].sum())
            lines.append(f'| {event} | {n} | {primary} | {all_n} |')
        lines += ['', 'Response plots show levels of log RV, log volume, spread proxy and returns around events.',
                  'They do not measure abnormal responses against a counterfactual or a no-event control group.']
    return '\n'.join(lines) + '\n'


def figures(task, tables, folder):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'axes.spines.top': False, 'axes.spines.right': False})
    names = []
    if task == 't15':
        s = tables['t15_volatility_regression_results.parquet']
        fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
        for ax, branch in zip(axes, ['activity_cohort', 'cex']):
            sub = s[s.branch.eq(branch) & s.model.eq('primary') & s.variable.eq(s.predictor)].sort_values('horizon_h')
            ax.errorbar(sub.horizon_h, sub.coef, yerr=[sub.coef-sub.ci_lower, sub.ci_upper-sub.coef],
                        fmt='o', color='#117A8B', capsize=5)
            ax.axhline(0, color='#687782', lw=1)
            ax.set(title=branch, xlabel='Horizon (days)', ylabel='Coefficient; pointwise 95% HAC CI')
            ax.set_xticks([1, 3, 7])
        path = folder / 't15_flow_coefficients.png'
        fig.savefig(path, dpi=160, metadata={'Software': 'crypto-analysis'}); plt.close(fig); names.append(path)
    else:
        s = tables['t16_event_study_results.parquet']
        for event in sorted(s.event_type.unique()):
            fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
            for ax, variable in zip(axes.ravel(), s.variable.unique()):
                sub = s[s.event_type.eq(event) & s.analysis_role.eq('primary') & s.variable.eq(variable)].sort_values('tau')
                ax.plot(sub.tau, sub['mean'], marker='o', ms=3, color='#117A8B')
                ax.fill_between(sub.tau, sub.ci_lower, sub.ci_upper, color='#117A8B', alpha=.18)
                ax.axvline(0, color='#DB7C26', linestyle='--', lw=1)
                ax.set(title=f'{variable} (n={int(sub.n_events.iloc[0])})', xlabel='Calendar days from event')
            fig.suptitle(f'{event}: descriptive response; exploratory pointwise block CI')
            path = folder / f't16_{event}_response.png'
            fig.savefig(path, dpi=160, metadata={'Software': 'crypto-analysis'}); plt.close(fig); names.append(path)
    return names


def run(task, config_path, output_dir=None):
    config_path = local_path(config_path)
    cfg = read_config(config_path)
    folder = local_path(output_dir or cfg['output_dir'])
    folder.mkdir(parents=True, exist_ok=True)
    sources = hash_paths([ROOT / name for name in SOURCE_FILES] + [config_path])
    loaded = inputs(cfg, task)
    tables = calculate(task, cfg, loaded)
    second = calculate(task, cfg, inputs(cfg, task))
    hashes = {name: {'run1': frame_hash(frame), 'run2': frame_hash(second[name])} for name, frame in tables.items()}
    require(all(x['run1'] == x['run2'] for x in hashes.values()), 'Internal reproduction failed')
    for name, frame in tables.items():
        frame.to_parquet(folder / name, index=False)
    report_path = folder / f'{task}_report.md'
    report_path.write_text(report(task, cfg, tables), encoding='utf-8')
    fig_paths = figures(task, tables, folder)
    verify_hashes(sources); verify_hashes(loaded[4])
    summary = dict(protocol_id=cfg['protocol_id'], contract_version=cfg['contract_version'], task=task,
        computation_validated=True, independent_review_required=True, upload_performed=False,
        ready_for_individual_investor_inference=False, rq3_answered=False,
        policy=loaded[3]['policy'], source_config_sha256=sources, input_sha256=loaded[4],
        parameters=cfg, versions={p: importlib.metadata.version(p) for p in ['numpy', 'pandas', 'pyarrow', 'statsmodels', 'matplotlib']},
        content_hashes=hashes, n_rows={name: len(frame) for name, frame in tables.items()},
        output_sha256={p.name: file_hash(p) for p in [folder / n for n in tables] + [report_path] + fig_paths})
    json_write(folder / f'{task}_summary.json', summary)
    print(f'{task}: validated, internal reproducibility PASS; output={relative_path(folder)}')
    return summary


def cli(task):
    parser = argparse.ArgumentParser(description=f'{task.upper()} validated scoped analysis')
    parser.add_argument('--config', default=f'config/{task}.yaml')
    parser.add_argument('--output-dir', help='Project-relative destination, including isolated review cache')
    args = parser.parse_args()
    run(task, args.config, args.output_dir)
