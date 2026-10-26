"""T17 — robustness / sensitivity of T15 and T16; see config/t17.yaml and docs/T17_specification.md.

Run from the project root after the verified T14, T15, T16 releases and T11 are in data/processed:

    python T17_Robustness.py

The accepted T15/T16 base results are reproduced first; the grid is computed twice and the content
hashes compared. Output tables are Parquet; nothing is selected by sign, p-value or response size.
"""
import argparse
import copy
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
from src.t17_release_inputs import verify_release
from src.forecast_inputs import (ROOT, file_hash, hash_paths, json_write, load_t14, local_path, read_config,
                                 relative_path, require, verify_hashes)

SOURCE_FILES = ['src/forecast_inputs.py', 'src/robustness.py', 'T17_Robustness.py', 'src/volatility_regression.py',
                'src/event_study.py', 'src/flow_volatility.py', 'src/graph_ml_features.py', 'src/analysis_release.py',
                'config/t15.yaml', 'config/t16.yaml', 'src/t17_release_inputs.py',
                'scripts/validate_t17_release.py']
EDGES_KEY = 'data/processed/graphs/dynamic_edges_daily.parquet'


def required_files(cfg):
    t15_cfg_file = local_path(cfg['t15_config'])
    t16_cfg_file = local_path(cfg['t16_config'])
    cfg16 = read_config(t16_cfg_file)
    names = [t15_cfg_file, t16_cfg_file,
             local_path(cfg['t15_results_dir']) / 't15_summary.json',
             local_path(cfg['t15_results_dir']) / 't15_volatility_regression_summary.parquet',
             local_path(cfg['t15_results_dir']) / 't15_sample_membership.parquet',
             local_path(cfg['t16_results_dir']) / 't16_summary.json',
             local_path(cfg['t16_results_dir']) / 't16_event_selection.parquet',
             local_path(cfg['t16_results_dir']) / 't16_event_candidates.parquet',
             local_path(cfg['t11_weekly_snapshot']), local_path(cfg['t11_summary']), local_path(cfg['daily_edges_parquet']),
             local_path(cfg16['t11_snapshot']), local_path(cfg16['t11_reproducibility'])]
    return names


def preflight(cfg):
    require(cfg['protocol_id'] == 't17_usdt_daily_weekly_v2', 'Unsupported T17 protocol')
    require(cfg['scope'] == dict(token='USDT', token_axis='excluded_by_approved_scope',
                                graph_windows=['daily', 'iso_weekly'], accepted_by='project_owner',
                                accepted_on='2026-10-26', cross_token_generalization_tested=False), 'Unapproved T17 scope')
    require(cfg['token']['other_tokens'] == [], 'Only USDT supported by this protocol; other tokens require a new release')
    require(cfg['events']['weekly_concentration'] is True, 'Approved graph scope requires daily/weekly comparison')
    missing = [relative_path(p) for p in required_files(cfg) if not p.is_file()]
    if missing:
        raise SystemExit('Thiếu dữ liệu đầu vào (tải đúng revision từ Hugging Face, giữ nguyên cấu trúc thư mục):\n  - ' + '\n  - '.join(missing))


def load(cfg):
    features, eligibility, summary, gate, hashes = load_t14(cfg)
    t15_cfg_path = local_path(cfg['t15_config'])
    t16_cfg_path = local_path(cfg['t16_config'])
    cfg15, t15_summary, h15 = verify_release('t15', cfg['t15_config'], cfg['t15_results_dir'], gate, hashes)
    cfg16, t16_summary, h16 = verify_release('t16', cfg['t16_config'], cfg['t16_results_dir'], gate, hashes)
    t14_cfg = read_config(ROOT / 'config/t14.yaml')
    files = required_files(cfg)
    before = hash_paths(files)

    t15_summary = json.loads((local_path(cfg['t15_results_dir']) / 't15_summary.json').read_text(encoding='utf-8'))
    t16_summary = json.loads((local_path(cfg['t16_results_dir']) / 't16_summary.json').read_text(encoding='utf-8'))
    t15_cfg_hash = file_hash(t15_cfg_path)
    t16_cfg_hash = file_hash(t16_cfg_path)
    expected_t15_hash = t15_summary.get('source_config_sha256', {}).get('config/t15.yaml')
    expected_t16_hash = t16_summary.get('source_config_sha256', {}).get('config/t16.yaml')
    require(t15_cfg_hash == expected_t15_hash,
            f'config/t15.yaml hash {t15_cfg_hash} mismatch with accepted T15 release ({expected_t15_hash})')
    require(t16_cfg_hash == expected_t16_hash,
            f'config/t16.yaml hash {t16_cfg_hash} mismatch with accepted T16 release ({expected_t16_hash})')
    hashes['config/t15.yaml'] = t15_cfg_hash
    hashes['config/t16.yaml'] = t16_cfg_hash

    concentration, t11 = events.load_concentration(cfg16, features.date)
    edges_hash = file_hash(local_path(cfg['daily_edges_parquet']))
    require(edges_hash == gate['input_sha256'][EDGES_KEY] == t11['inputs']['daily_edges_parquet']['sha256'],
            'Daily edges differ from the T14/T11 lineage')
    t11_summary = json.loads(local_path(cfg['t11_summary']).read_text(encoding='utf-8'))
    require(t11_summary.get('ready_for_downstream') is True and t11_summary.get('independent_review_pass') is True,
            'T11 is not validated for downstream')

    weekly_path = local_path(cfg['t11_weekly_snapshot'])
    weekly_hash = file_hash(weekly_path)
    t11_repro = json.loads(local_path(cfg16['t11_reproducibility']).read_text(encoding='utf-8'))
    weekly_pair = t11_repro.get('hashes', {}).get(weekly_path.name, {})
    require(t11_repro.get('all_match') is True and weekly_pair.get('run1') == weekly_pair.get('run2') == weekly_hash,
            f'T11 weekly snapshot differs from reproduced artifact hash: {weekly_hash} vs {weekly_pair.get("run1")}')
    weekly = pd.read_parquet(weekly_path)
    weekly_shape = t11_summary.get('shapes', {}).get('weekly', {})
    require(len(weekly) == weekly_shape.get('snapshots', 94),
            f'T11 weekly snapshot count mismatch: {len(weekly)} vs {weekly_shape.get("snapshots")}')
    require('community_concentration_index' in weekly, 'Missing community_concentration_index in T11 weekly snapshot')
    require(weekly.window_type.eq('weekly').all(), 'T11 snapshot must be weekly')
    require(weekly['community_concentration_index'].between(0, 1).all(), 'Invalid T11 weekly concentration values')
    require(np.isclose(weekly['community_concentration_index'].mean(), weekly_shape.get('mean_cci', 0.0811926715724106), atol=1e-6),
            f'T11 weekly mean CCI mismatch with accepted T11 summary: {weekly["community_concentration_index"].mean()} vs {weekly_shape.get("mean_cci")}')

    edges = pd.read_parquet(local_path(cfg['daily_edges_parquet']), columns=['time_window', 'from_address', 'to_address', 'total_value'])
    results = dict(t15=pd.read_parquet(local_path(cfg['t15_results_dir']) / 't15_volatility_regression_summary.parquet'),
                   t15_membership=pd.read_parquet(local_path(cfg['t15_results_dir']) / 't15_sample_membership.parquet'),
                   t16_selection=pd.read_parquet(local_path(cfg['t16_results_dir']) / 't16_event_selection.parquet'),
                   t16_candidates=pd.read_parquet(local_path(cfg['t16_results_dir']) / 't16_event_candidates.parquet'))
    hashes = {**hashes, **h15, **h16, **before}
    return dict(features=features, eligibility=eligibility, gate=gate, hashes=hashes, cfg15=cfg15, cfg16=cfg16, t14_cfg=t14_cfg,
                t15_summary=t15_summary, t16_summary=t16_summary, t11_summary=t11_summary,
                t15_cfg_hash=t15_cfg_hash, t16_cfg_hash=t16_cfg_hash, weekly_hash=weekly_hash,
                concentration=concentration, weekly=weekly, edges=edges, results=results)


def validate_base(cfg, loaded):
    """Tái tạo duy nhất base, dừng trước mọi kịch bản sensitivity nếu không khớp."""
    base_cfg = copy.deepcopy(cfg)
    base_cfg['horizon'] = dict(extra_single_day=[], cumulative=[])
    base_cfg['flow_window'] = dict(trailing_days=[], matched_sample_comparison=False)
    table, dates = rb.run_regressions(loaded['features'], loaded['eligibility'], loaded['cfg15'], base_cfg,
                                     loaded['t14_cfg']['normalisation'], return_dates=True)
    rows = rb.reconcile_t15(table, loaded['results']['t15'], loaded['cfg15']['horizons'], float(cfg['tolerance']),
                            loaded['results']['t15_membership'], dates)
    tables = events.compute(loaded['features'], loaded['eligibility'], loaded['concentration'], loaded['gate'], loaded['cfg16'])
    rows += rb.reconcile_t16(tables, loaded['results']['t16_selection'], loaded['results']['t16_candidates'], float(cfg['tolerance']))
    require(all(r['status'] == 'PASS' for r in rows), 'Base reconciliation failed before sensitivity grid: ' +
            str([r for r in rows if r['status'] != 'PASS']))
    return rows


def compute(cfg, loaded):
    # Hàm public cũng kiểm tra base trước grid, kể cả khi được gọi ngoài CLI.
    base_checks = validate_base(cfg, loaded)
    f, e, gate = loaded['features'], loaded['eligibility'], loaded['gate']
    cfg15, cfg16, norm = loaded['cfg15'], loaded['cfg16'], loaded['t14_cfg']['normalisation']
    regression, sample_dates = rb.run_regressions(f, e, cfg15, cfg, norm, return_dates=True)
    dates = f.date.dt.strftime('%Y-%m-%d').tolist()
    counts = rb.large_edge_counts(loaded['edges'], dates, cfg['events']['large_edge_percentile'], loaded['t14_cfg'])
    weekly = rb.weekly_concentration_frame(loaded['weekly'], f.date)
    event_rows, base_tables, plan = rb.run_events(f, e, loaded['concentration'], weekly, counts, gate, cfg16, cfg)
    summary = rb.regression_summary(regression, cfg15['horizons'])
    plan_rows = [dict(task='t15', **{k: v for k, v in r.items() if k in ('scenario_id', 'axis', 'definition', 'horizon_h', 'flow_window_days')},
                      status='completed' if regression[regression.scenario_id.eq(r['scenario_id'])].status.eq('ok').all() else 'failed')
                 for r in rb.regression_plan(cfg, cfg15['horizons'])]
    plan_rows += [dict(task='t16', scenario_id=r['scenario_id'], axis=r['axis'], status='completed') for r in plan]
    plan_rows.append(dict(task='token', scenario_id='other_tokens', axis='token', status='excluded_by_approved_scope',
                          reason='Project owner approved USDT-only on 2026-10-26. Cross-token generalization has not been tested.'))
    plan_table = pd.DataFrame(plan_rows)
    plan_table['reason'] = plan_table['reason'].fillna('') if 'reason' in plan_table else ''
    membership = pd.DataFrame([dict(scenario_id=s, branch=b, date=d) for (s, b), days in sample_dates.items() for d in days])
    return dict(regression=regression, summary=summary, events=event_rows, plan=plan_table, base_tables=base_tables,
                membership=membership, base_checks=base_checks,
                base_count=counts[float(loaded['t14_cfg']['large_transfer']['percentile'])],
                sample_dates=sample_dates)


def validation(cfg, loaded, out):
    f, e = loaded['features'], loaded['eligibility']
    cfg15, norm, tol = loaded['cfg15'], loaded['t14_cfg']['normalisation'], float(cfg['tolerance'])
    independent = rb.independent_hac_checks(f, e, cfg15, norm, out['regression'])
    rows = rb.structural_checks(f, out['regression'], cfg15, norm, tol, edge_counts=out['base_count'],
                                independent=independent, sample_dates=out.get('sample_dates'), cfg17=cfg, eligibility=e)
    rows += rb.reconcile_t15(out['regression'], loaded['results']['t15'], cfg15['horizons'], tol,
                             t15_membership=loaded['results'].get('t15_membership'),
                             sample_dates=out.get('sample_dates'))
    rows += rb.reconcile_t16(out['base_tables'], loaded['results']['t16_selection'], loaded['results']['t16_candidates'])
    rows += rb.trailing_leak_checks(f, norm, cfg['flow_window']['trailing_days'], cfg['leakage_cut_fractions'], tol)
    rows.append(dict(check='t15_config_hash_matches_accepted_release', scope='config',
                     status='PASS' if loaded['t15_cfg_hash'] == loaded['t15_summary'].get('source_config_sha256', {}).get('config/t15.yaml') else 'FAIL',
                     detail=loaded['t15_cfg_hash']))
    rows.append(dict(check='t16_config_hash_matches_accepted_release', scope='config',
                     status='PASS' if loaded['t16_cfg_hash'] == loaded['t16_summary'].get('source_config_sha256', {}).get('config/t16.yaml') else 'FAIL',
                     detail=loaded['t16_cfg_hash']))
    rows.append(dict(check='t11_weekly_snapshot_matches_accepted_reproducibility', scope='t11',
                     status='PASS', detail=loaded['weekly_hash']))
    rows.append(dict(check='t11_weekly_concentration_matches_accepted_summary', scope='t11',
                     status='PASS', detail=f"mean_cci={loaded['weekly']['community_concentration_index'].mean():.8f}"))
    rows += out['base_checks']
    rows.append(dict(check='approved_usdt_scope_and_graph_windows', scope='scope', status='PASS', detail=str(cfg['scope'])))
    rows.append(dict(check='upstream_releases_verified', scope='provenance', status='PASS', detail='T15/T16 source, config, input, artifact, review hashes verified before base'))
    df = pd.DataFrame(rows)
    df['detail'] = df['detail'].astype(str)
    return df


def figure(table, folder):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'axes.spines.top': False, 'axes.spines.right': False})
    axes_names = ['horizon_single_day', 'horizon_cumulative', 'flow_window', 'flow_window_common_sample']
    fig, axes = plt.subplots(1, 4, figsize=(20, 4.2), constrained_layout=True, sharey=False)
    colors = {'activity_cohort': '#117A8B', 'cex': '#DB7C26'}
    for ax, axis in zip(axes, axes_names):
        sub = table[table.axis.eq(axis) & table.status.eq('ok')].copy()
        sub['label'] = [f'h={r.horizon_h}' if not axis.startswith('flow_window') else f'k={r.flow_window_days},h={r.horizon_h}' for r in sub.itertuples()]
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
             'Approved scope: USDT only; graph windows = daily / full ISO weekly. Cross-token generalization has NOT been tested.',
             'The token axis is excluded by the project owner decision of 2026-10-26, not a completed cross-token experiment.',
             'Graph windows of 30 days or eight weeks are outside this release. weekly_minimum_history_values=8 counts valid weekly observations in a 90-day threshold history.',
             'Transfers are restricted to the >=500,000 USDT subnetwork. Flow counts do not represent all transactions.', '',
             '## Regression grid (flow coefficient per scenario family)', '',
             '| Axis | Branch | Scenarios | Failed | Coef min | Coef max | p<0.05 | p Holm<0.05 | Same sign as base (same h) |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in out['summary'].itertuples():
        lines.append(f'| {r.axis} | {r.branch} | {r.n_scenarios} | {r.n_failed} | {r.coefficient_min:.5f} | {r.coefficient_max:.5f} | '
                     f'{r.n_p_below_005} | {r.n_p_holm_axis_below_005} | {r.n_same_sign_as_base_same_h}/{r.n_with_base_reference} |')
    lines += ['', 'The cumulative definition (sum of daily RV over D+1..D+h) and the k-day trailing flow sums are different estimands, '
              'not replacements for the primary single-day, 1-day-flow specification. Trailing sums add up already-netted daily flows; '
              'they are not graphs re-netted over k days. flow_window_common_sample fits k=1,3,7 on the same intersection of valid days per branch/horizon. '
              'The regular flow_window family uses all valid days for each k. Missing raw flow propagates through rolling sums; volume is used for scaled flow, not the raw-flow z-score. '
              'Internal calendar gaps are refused by the HAC fitter; no NaN is replaced with zero.', '', '## Event grid', '',
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
             't17_event_robustness.parquet': 'events', 't17_scenario_plan.parquet': 'plan',
             't17_sample_membership.parquet': 'membership'}
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
                   task_complete_within_approved_scope=bool(failed.empty and repeated), scope=cfg['scope'],
                   token_axis=dict(status='excluded_by_approved_scope', other_tokens=[],
                                   cross_token_generalization_tested=False, reason='USDT-only approved by project owner on 2026-10-26.'),
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
