"""T17 — robustness / sensitivity of T15 and T16; see config/t17.yaml and docs/T17_specification.md.

Run from the project root after the verified T14, T15, T16 releases and T11 are in data/processed:

    python T17_Robustness.py

The accepted T15/T16 base results are reproduced first; the grid is computed twice and the content
hashes compared. Output tables are Parquet; nothing is selected by sign, p-value or response size.
"""
import argparse
import importlib.metadata
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import event_study as events
from src import robustness as rb
from src.analysis_release import frame_hash
from src.forecast_inputs import (ROOT, file_hash, hash_paths, json_write, load_t14, local_path, read_config,
                                 relative_path, require, verify_hashes)

SOURCE_FILES = ['src/forecast_inputs.py', 'src/robustness.py', 'T17_Robustness.py', 'src/volatility_regression.py',
                'src/event_study.py', 'src/flow_volatility.py', 'src/graph_ml_features.py', 'src/analysis_release.py']
EDGES_KEY = 'data/processed/graphs/dynamic_edges_daily.parquet'


def required_files(cfg):
    t16 = local_path(cfg['t16_config'])
    cfg16 = read_config(t16)
    names = [local_path(cfg['t15_results_dir']) / 't15_volatility_regression_summary.parquet',
             local_path(cfg['t16_results_dir']) / 't16_event_selection.parquet',
             local_path(cfg['t16_results_dir']) / 't16_event_candidates.parquet',
             local_path(cfg['t11_weekly_snapshot']), local_path(cfg['t11_summary']), local_path(cfg['daily_edges_parquet']),
             local_path(cfg16['t11_snapshot']), local_path(cfg16['t11_reproducibility'])]
    return names


def preflight(cfg):
    missing = [relative_path(p) for p in required_files(cfg) if not p.is_file()]
    if missing:
        raise SystemExit('Thiếu dữ liệu đầu vào (tải đúng revision từ Hugging Face, giữ nguyên cấu trúc thư mục):\n  - ' + '\n  - '.join(missing))


def load(cfg):
    features, eligibility, summary, gate, hashes = load_t14(cfg)
    cfg15, cfg16 = read_config(local_path(cfg['t15_config'])), read_config(local_path(cfg['t16_config']))
    t14_cfg = read_config(ROOT / 'config/t14.yaml')
    files = required_files(cfg)
    before = hash_paths(files)
    concentration, t11 = events.load_concentration(cfg16, features.date)
    edges_hash = file_hash(local_path(cfg['daily_edges_parquet']))
    require(edges_hash == gate['input_sha256'][EDGES_KEY] == t11['inputs']['daily_edges_parquet']['sha256'],
            'Daily edges differ from the T14/T11 lineage')
    t11_summary = json.loads(local_path(cfg['t11_summary']).read_text(encoding='utf-8'))
    require(t11_summary.get('ready_for_downstream') is True and t11_summary.get('independent_review_pass') is True,
            'T11 is not validated for downstream')
    weekly = pd.read_parquet(local_path(cfg['t11_weekly_snapshot']))
    edges = pd.read_parquet(local_path(cfg['daily_edges_parquet']), columns=['time_window', 'from_address', 'to_address', 'total_value'])
    results = dict(t15=pd.read_parquet(local_path(cfg['t15_results_dir']) / 't15_volatility_regression_summary.parquet'),
                   t16_selection=pd.read_parquet(local_path(cfg['t16_results_dir']) / 't16_event_selection.parquet'),
                   t16_candidates=pd.read_parquet(local_path(cfg['t16_results_dir']) / 't16_event_candidates.parquet'))
    hashes = dict(hashes, **before)
    return dict(features=features, eligibility=eligibility, gate=gate, hashes=hashes, cfg15=cfg15, cfg16=cfg16, t14_cfg=t14_cfg,
                concentration=concentration, weekly=weekly, edges=edges, results=results)


def compute(cfg, loaded):
    f, e, gate = loaded['features'], loaded['eligibility'], loaded['gate']
    cfg15, cfg16, norm = loaded['cfg15'], loaded['cfg16'], loaded['t14_cfg']['normalisation']
    regression = rb.run_regressions(f, e, cfg15, cfg, norm)
    dates = f.date.dt.strftime('%Y-%m-%d').tolist()
    counts = rb.large_edge_counts(loaded['edges'], dates, cfg['events']['large_edge_percentile'], loaded['t14_cfg'])
    weekly = rb.weekly_concentration_frame(loaded['weekly'], f.date)
    event_rows, base_tables, plan = rb.run_events(f, e, loaded['concentration'], weekly, counts, gate, cfg16, cfg)
    summary = rb.regression_summary(regression, cfg15['horizons'])
    plan_rows = [dict(task='t15', **{k: v for k, v in r.items() if k in ('scenario_id', 'axis', 'definition', 'horizon_h', 'flow_window_days')},
                      status='planned') for r in rb.regression_plan(cfg, cfg15['horizons'])]
    plan_rows += [dict(task='t16', scenario_id=r['scenario_id'], axis=r['axis'], status='planned') for r in plan]
    plan_rows.append(dict(task='token', scenario_id='other_tokens', axis='token', status='not_run',
                          reason='No T04-T14 data exists for tokens other than USDT; the axis needs new on-chain downloads and a full pipeline rerun.'))
    plan_table = pd.DataFrame(plan_rows)
    plan_table['reason'] = plan_table['reason'].fillna('') if 'reason' in plan_table else ''
    return dict(regression=regression, summary=summary, events=event_rows, plan=plan_table, base_tables=base_tables,
                base_count=counts[float(loaded['t14_cfg']['large_transfer']['percentile'])])


def validation(cfg, loaded, out):
    f, e = loaded['features'], loaded['eligibility']
    cfg15, norm, tol = loaded['cfg15'], loaded['t14_cfg']['normalisation'], float(cfg['tolerance'])
    independent = rb.independent_hac_checks(f, e, cfg15, norm, out['regression'])
    rows = rb.structural_checks(f, out['regression'], cfg15, norm, tol, edge_counts=out['base_count'], independent=independent)
    rows += rb.reconcile_t15(out['regression'], loaded['results']['t15'], cfg15['horizons'], tol)
    rows += rb.reconcile_t16(out['base_tables'], loaded['results']['t16_selection'], loaded['results']['t16_candidates'])
    rows += rb.trailing_leak_checks(f, norm, cfg['flow_window']['trailing_days'], cfg['leakage_cut_fractions'], tol)
    rows.append(dict(check='token_axis_not_run_and_declared', scope='token', status='PASS', detail='other_tokens=[]'))
    df = pd.DataFrame(rows)
    df['detail'] = df['detail'].astype(str)
    return df


def figure(table, folder):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'axes.spines.top': False, 'axes.spines.right': False})
    axes_names = ['horizon_single_day', 'horizon_cumulative', 'flow_window']
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), constrained_layout=True, sharey=False)
    colors = {'activity_cohort': '#117A8B', 'cex': '#DB7C26'}
    for ax, axis in zip(axes, axes_names):
        sub = table[table.axis.eq(axis) & table.status.eq('ok')].copy()
        sub['label'] = [f'h={r.horizon_h}' if axis != 'flow_window' else f'k={r.flow_window_days},h={r.horizon_h}' for r in sub.itertuples()]
        labels = list(dict.fromkeys(sub.label))
        for j, branch in enumerate(['activity_cohort', 'cex']):
            g = sub[sub.branch.eq(branch)].set_index('label').reindex(labels)
            x = np.arange(len(labels)) + (j - .5) * .3
            ax.errorbar(x, g.coefficient, yerr=[g.coefficient - g.ci_lower, g.ci_upper - g.coefficient], fmt='o', ms=4,
                        capsize=3, color=colors[branch], label=branch)
        ax.axhline(0, color='#687782', lw=1)
        ax.set_xticks(np.arange(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
        ax.set(title=axis, ylabel='Flow coefficient; 95% HAC CI')
    axes[0].legend(frameon=False, fontsize=8)
    path = folder / 't17_regression_robustness.png'
    fig.savefig(path, dpi=160, metadata={'Software': 'crypto-analysis'})
    plt.close(fig)
    return path


def report(cfg, out, checks):
    lines = [f'# T17 — {cfg["protocol_id"]}', '',
             'Scope: robustness of T15/T16 on the verified T14 release (observed approved CEX subset; unidentified high-activity cohort).',
             'In-sample association only: no causal effect, no out-of-sample forecast evidence (T18), RQ3 not answered.',
             'Every scenario is reported; none is chosen by sign, p-value or response size. Holm is applied within each axis only.',
             'Token axis NOT run: no data other than USDT exists in T04-T14.', '',
             '## Regression grid (flow coefficient per scenario family)', '',
             '| Axis | Branch | Scenarios | Failed | Coef min | Coef max | p<0.05 | p Holm<0.05 | Same sign as base (same h) |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in out['summary'].itertuples():
        lines.append(f'| {r.axis} | {r.branch} | {r.n_scenarios} | {r.n_failed} | {r.coefficient_min:.5f} | {r.coefficient_max:.5f} | '
                     f'{r.n_p_below_005} | {r.n_p_holm_axis_below_005} | {r.n_same_sign_as_base_same_h}/{r.n_with_base_reference} |')
    lines += ['', 'The cumulative definition (sum of daily RV over D+1..D+h) and the k-day trailing flow sums are different estimands, '
              'not replacements for the primary single-day, 1-day-flow specification. Trailing sums add up already-netted daily flows; '
              'they are not graphs re-netted over k days.', '', '## Event grid', '',
              '| Scenario | Event | Policy | Events (base) | Jaccard | log RV post−pre | CI |', '|---|---|---|---:|---:|---:|---|']
    for r in out['events'][out['events'].selection_policy.eq('nonoverlap')].itertuples():
        ci = f'[{r.log_rv_ci_lower:.4f}, {r.log_rv_ci_upper:.4f}]' if r.log_rv_ci_status == 'available_exploratory' else r.log_rv_ci_status
        lines.append(f'| {r.scenario_id} | {r.event_type} | {r.selection_policy} | {r.n_events} ({r.n_events_base}) | '
                     f'{r.jaccard_with_base:.2f} | {r.log_rv_post_minus_pre:.4f} | {ci} |')
    lines += ['', 'Post−pre is the mean log RV over tau=0..k minus tau=−k..−1 per event; the interval is an exploratory pointwise circular '
              'block bootstrap over events, not a causal or abnormal-response estimate. Small event counts leave several intervals empty.',
              '', f'Validation: {int((checks.status == "PASS").sum())} PASS, {int((checks.status == "FAIL").sum())} FAIL.']
    return '\n'.join(lines) + '\n'


def run(config_path, output_dir=None):
    config_path = local_path(config_path)
    cfg = read_config(config_path)
    preflight(cfg)
    folder = local_path(output_dir or cfg['output_dir'])
    folder.mkdir(parents=True, exist_ok=True)
    sources = hash_paths([ROOT / name for name in SOURCE_FILES] + [config_path])
    loaded = load(cfg)
    out = compute(cfg, loaded)
    second = compute(cfg, load(cfg))
    checks = validation(cfg, loaded, out)
    names = {'t17_regression_robustness.parquet': 'regression', 't17_regression_summary.parquet': 'summary',
             't17_event_robustness.parquet': 'events', 't17_scenario_plan.parquet': 'plan'}
    hashes = {n: {'run1': frame_hash(out[k]), 'run2': frame_hash(second[k])} for n, k in names.items()}
    repeated = all(h['run1'] == h['run2'] for h in hashes.values())
    checks = pd.concat([checks, pd.DataFrame([dict(check='two_runs_identical_content_hash', scope='all',
                                                   status='PASS' if repeated else 'FAIL', detail='')])], ignore_index=True)
    checks['detail'] = checks['detail'].astype(str)
    tables = {n: out[k] for n, k in names.items()}
    tables['t17_validation.parquet'] = checks
    for n, frame in tables.items():
        frame.to_parquet(folder / n, index=False)
    report_path = folder / 't17_report.md'
    report_path.write_text(report(cfg, out, checks), encoding='utf-8')
    png = figure(out['regression'], folder)
    verify_hashes(sources)
    verify_hashes(loaded['hashes'])
    failed = checks[checks.status.eq('FAIL')]
    summary = dict(protocol_id=cfg['protocol_id'], contract_version=cfg['contract_version'], task='t17',
                   computation_validated=bool(failed.empty and repeated), independent_review_required=True, upload_performed=False,
                   rq3_answered=False, causal_claim=False, out_of_sample_claim=False,
                   token_axis=dict(status='not_run', other_tokens=cfg['token']['other_tokens'],
                                   reason='No data for tokens other than USDT in T04-T14.'),
                   scenario_counts=dict(regression=int(len(out['regression'])), event_rows=int(len(out['events']))),
                   failed_checks=failed[['check', 'scope', 'detail']].to_dict('records'),
                   source_config_sha256=sources, input_sha256=loaded['hashes'], parameters=cfg,
                   versions={p: importlib.metadata.version(p) for p in ['numpy', 'pandas', 'pyarrow', 'statsmodels', 'matplotlib']},
                   content_hashes=hashes, output_sha256={p.name: file_hash(p) for p in [folder / n for n in tables] + [report_path, png]})
    json_write(folder / 't17_summary.json', summary)
    print(f"t17: computation_validated={summary['computation_validated']} regression_rows={len(out['regression'])} "
          f"event_rows={len(out['events'])} output={relative_path(folder)}")
    if not failed.empty:
        print('FAILED CHECKS:\n' + failed[['check', 'scope', 'detail']].to_string())
        raise SystemExit(1)
    return summary


def main():
    parser = argparse.ArgumentParser(description='T17 robustness of T15/T16')
    parser.add_argument('--config', default='config/t17.yaml')
    parser.add_argument('--output-dir', help='Project-relative destination, including an isolated review cache')
    args = parser.parse_args()
    run(args.config, args.output_dir)


if __name__ == '__main__':
    main()
