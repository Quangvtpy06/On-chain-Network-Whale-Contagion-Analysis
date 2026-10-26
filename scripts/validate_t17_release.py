"""Kiểm định T17 trong tiến trình riêng, gồm lịch/mẫu/z-score bằng phép tính độc lập."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
import T17_Robustness as release
from src import robustness as rb
from src.analysis_release import frame_hash
from src.forecast_inputs import file_hash, hash_paths, json_write, local_path, read_config, require, verify_hashes


def direct_z(raw, k, norm):
    """Duyệt lát cắt lịch sử, không gọi rolling/normalise_flow của pipeline."""
    raw = np.asarray(raw, float)
    sums = np.full(len(raw), np.nan)
    z = sums.copy()
    for i in range(k - 1, len(raw)):
        window = raw[i-k+1:i+1]
        if np.isfinite(window).all():
            sums[i] = window.sum()
    for i in range(len(raw)):
        history = sums[max(0, i-int(norm['zscore_lookback_days'])):i]
        history = history[np.isfinite(history)]
        if len(history) >= norm['minimum_history_days'] and len(history) > 1:
            sd = history.std(ddof=1)
            if sd > 0:
                z[i] = (sums[i] - history.mean()) / sd
    return z


def independent_checks(loaded, cfg, table, membership):
    f, e, cfg15 = loaded['features'], loaded['eligibility'], loaded['cfg15']
    norm = loaded['t14_cfg']['normalisation']
    controls = cfg15['controls'] + cfg15['extended_controls']
    rv = f.rv.to_numpy(float)
    rows = []
    require(not membership.duplicated(['scenario_id', 'branch', 'date']).any(), 'Duplicate sample membership')
    require(set(zip(table.scenario_id, table.branch)) == set(zip(membership.scenario_id, membership.branch)), 'Missing scenario membership')
    for r in table.itertuples():
        raw = f[rb.BRANCH_RAW[r.branch]].to_numpy(float)
        z = direct_z(raw, int(r.flow_window_days), norm)
        target = np.full(len(f), np.nan)
        h = int(r.horizon_h)
        for i in range(len(f)-h):
            values = rv[i+h:i+h+1] if r.definition == 'single_day' else rv[i+1:i+h+1]
            if np.isfinite(values).all() and values.sum() > 0:
                target[i] = np.log(values.sum())
        opts = cfg15['branches'][r.branch]
        mask = e[f'predictors_ready_{opts["eligibility"]}'].to_numpy(bool)
        mask = mask & np.isfinite(f[controls].to_numpy(float)).all(axis=1) & np.isfinite(z) & np.isfinite(target)
        if r.axis == 'flow_window_common_sample':
            for k in [1] + cfg['flow_window']['trailing_days']:
                mask &= np.isfinite(direct_z(raw, k, norm))
        selected = membership[membership.scenario_id.eq(r.scenario_id) & membership.branch.eq(r.branch)]
        expected = list(f.loc[mask, 'date'])
        actual = list(pd.to_datetime(selected.date, utc=True))
        require(actual == expected and len(actual) == r.n_obs, 'Independent sample dates differ: ' + r.scenario_id)
        x = np.column_stack([f.loc[mask, controls].to_numpy(float), z[mask]])
        beta, se = rb.numpy_hac(target[mask], x, int(r.maxlags_hac))
        require(np.isclose(beta[-1], r.coefficient, rtol=1e-7, atol=1e-8), 'Independent coefficient differs')
        require(np.isclose(se[-1], r.hac_se, rtol=1e-7, atol=1e-8), 'Independent HAC differs')
        rows.append(dict(check='independent_history_slices_sample_target_matrix_hac', scope=r.scenario_id+'|'+r.branch, status='PASS'))
    return rows


def validate(config='config/t17.yaml', folder=None):
    path = local_path(config); cfg = read_config(path)
    release.preflight(cfg)
    folder = local_path(folder or cfg['output_dir'])
    summary_path = folder/'t17_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    require(summary['computation_validated'] is True and summary['task_complete_within_approved_scope'] is True, 'Unvalidated T17')
    require(summary['parameters'] == cfg and summary['protocol_id'] == cfg['protocol_id'], 'Changed T17 protocol/config')
    require(summary['scope'] == cfg['scope'] and summary['token_axis']['status'] == 'excluded_by_approved_scope', 'Invalid scope decision')
    require(summary['token_axis']['cross_token_generalization_tested'] is False, 'Unsupported cross-token claim')
    require(all(summary[k] is False for k in ['rq3_answered', 'causal_claim', 'out_of_sample_claim']), 'Unsupported research claim')
    sources = hash_paths([ROOT/n for n in release.SOURCE_FILES] + [path])
    require(summary['source_config_sha256'] == sources, 'T17 source/config differs')
    loaded = release.load(cfg)
    require(summary['input_sha256'] == loaded['hashes'], 'T17 input provenance differs')
    out = release.compute(cfg, loaded)
    checks = release.validation(cfg, loaded, out)
    require(checks.status.eq('PASS').all(), 'Recomputed validation failed')
    names = {'t17_regression_robustness.parquet':'regression', 't17_regression_summary.parquet':'summary',
             't17_event_robustness.parquet':'events', 't17_scenario_plan.parquet':'plan',
             't17_sample_membership.parquet':'membership'}
    expected_outputs = set(names) | {'t17_validation.parquet','t17_report.md','t17_regression_robustness.png'}
    require(set(summary['output_sha256']) == expected_outputs, 'Incomplete output manifest')
    require(set(summary['content_hashes']) == set(names), 'Incomplete reproduction map')
    for n, h in summary['output_sha256'].items():
        require(file_hash(folder/n) == h, 'Changed output: '+n)
    for n, key in names.items():
        saved = pd.read_parquet(folder/n); digest = frame_hash(out[key])
        require(frame_hash(saved) == digest, 'Independent recomputation differs: '+n)
        require(summary['content_hashes'][n] == dict(run1=digest, run2=digest), 'Reproduction map differs: '+n)
    saved_checks = pd.read_parquet(folder/'t17_validation.parquet')
    repeated = pd.DataFrame([dict(check='two_runs_identical_content_hash',scope='all',status='PASS',detail='')])
    expected_checks = pd.concat([checks,repeated],ignore_index=True)
    require(frame_hash(saved_checks) == frame_hash(expected_checks), 'Saved validation differs')
    require((folder/'t17_report.md').read_text(encoding='utf-8') == release.report(cfg,out,saved_checks), 'Report differs')
    independent = independent_checks(loaded,cfg,pd.read_parquet(folder/'t17_regression_robustness.parquet'),
                                     pd.read_parquet(folder/'t17_sample_membership.parquet'))
    verify_hashes(sources); verify_hashes(loaded['hashes'])
    result = dict(all_pass=True, protocol_id=cfg['protocol_id'], scope=cfg['scope'], separate_process_recomputation=True,
                  summary_sha256=file_hash(summary_path), output_sha256=summary['output_sha256'],
                  source_config_sha256=sources, input_sha256=loaded['hashes'], independent_checks=independent,
                  task_complete_within_approved_scope=True, cross_token_generalization_tested=False,
                  rq3_answered=False, caveat='USDT-only sensitivity; no causal or untouched out-of-sample claim.')
    json_write(folder/'t17_independent_review.json', result)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='config/t17.yaml'); parser.add_argument('--output-dir')
    args=parser.parse_args(); result=validate(args.config,args.output_dir)
    print(json.dumps(dict(all_pass=result['all_pass'], independent_checks=len(result['independent_checks']))))
