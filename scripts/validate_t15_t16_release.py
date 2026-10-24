"""Đối chiếu release T15/T16 với dữ liệu thật trong tiến trình kiểm định riêng."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis_release import SOURCE_FILES, inputs, calculate, frame_hash, report
from src.forecast_inputs import (local_path, read_config, hash_paths, verify_hashes, require,
                                 json_write, file_hash, relative_path)


def independent_arithmetic(task, cfg, loaded, tables):
    """Đối chiếu số học bằng ma trận/lookup trực tiếp, không gọi hàm fit/detect của pipeline."""
    import numpy as np
    checks = []
    features = loaded[0]
    if task == 't15':
        members = tables['t15_sample_membership.parquet']
        results = tables['t15_volatility_regression_results.parquet']
        for (branch, horizon, model), group in results.groupby(['branch', 'horizon_h', 'model']):
            selected = members[members.branch.eq(branch) & members.horizon_h.eq(horizon)].selected.to_numpy()
            sample = features.loc[selected]
            variables = group.predictors.iloc[0].split('|')
            x = np.column_stack([np.ones(len(sample)), sample[variables].to_numpy(float)])
            y = sample[f'target_log_rv_h{horizon}'].to_numpy(float)
            beta = np.linalg.lstsq(x, y, rcond=None)[0]
            score = x * (y - x @ beta)[:, None]
            meat = score.T @ score
            lagmax = int(group.maxlags_hac.iloc[0])
            for lag in range(1, lagmax + 1):
                cross = score[lag:].T @ score[:-lag]
                meat += (1 - lag / (lagmax + 1)) * (cross + cross.T)
            inv = np.linalg.inv(x.T @ x)
            se = np.sqrt(np.diag(inv @ meat @ inv) * len(y) / (len(y) - x.shape[1]))
            ordered = group.set_index('variable').loc[['const'] + variables]
            require(np.allclose(beta, ordered.coef, rtol=1e-7, atol=1e-8), 'Matrix OLS differs')
            require(np.allclose(se, ordered.hac_se, rtol=1e-6, atol=1e-8), 'Matrix HAC differs')
            checks.append(dict(check='independent_matrix_ols_hac', branch=branch, horizon=int(horizon), model=model, status='PASS'))
    else:
        signals = {'large_transfer': features.large_transfer_count.to_numpy(float),
                   'concentration': loaded[5].community_concentration_index.to_numpy(float)}
        for event, values in signals.items():
            q = cfg['large_transfer_quantile'] if event == 'large_transfer' else cfg['concentration_quantile']
            expected = []
            for i in range(len(values)):
                history = values[max(0, i-cfg['lookback_days']):i]
                history = history[np.isfinite(history)]
                expected.append(np.quantile(history, q) if len(history) >= cfg['minimum_history_days'] else np.nan)
            saved = tables['t16_event_candidates.parquet']
            actual = saved[saved.event_type.eq(event)].threshold.to_numpy(float)
            require(np.allclose(expected, actual, rtol=1e-10, atol=1e-10, equal_nan=True), 'Direct historical quantile differs')
            checks.append(dict(check='independent_history_slice_quantile', event_type=event, status='PASS'))
        windows = tables['t16_event_windows.parquet']
        lookup = features.set_index('date')
        for variable in cfg['response_variables']:
            expected = lookup.loc[windows.response_date, variable].to_numpy(float)
            require(np.array_equal(expected, windows[variable].to_numpy(float)), 'Direct calendar response lookup differs')
        checks.append(dict(check='independent_calendar_response_lookup', status='PASS'))
    return checks


def validate(task, folder=None):
    config = local_path(f'config/{task}.yaml')
    cfg = read_config(config)
    folder = local_path(folder or cfg['output_dir'])
    summary_path = folder / f'{task}_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    require(summary.get('computation_validated') is True, 'Computation not certified')
    require(summary['protocol_id'] == cfg['protocol_id'] and summary['parameters'] == cfg, 'Protocol/config differs')
    expected_source = hash_paths([ROOT / p for p in SOURCE_FILES] + [config])
    require(summary['source_config_sha256'] == expected_source, 'Missing/changed source/config provenance')
    verify_hashes(summary['input_sha256'])
    for name, value in summary['output_sha256'].items():
        require(Path(name).name == name and file_hash(folder / name) == value, 'Changed output: ' + name)
    loaded = inputs(cfg, task)
    require(loaded[4] == summary['input_sha256'], 'Incomplete input provenance')
    require(summary['policy'] == loaded[3]['policy'], 'Information scope/policy mismatch')
    require(summary.get('ready_for_individual_investor_inference') is False and summary.get('rq3_answered') is False,
            'Computation cannot certify individual ownership or research conclusion')
    tables = calculate(task, cfg, loaded)
    figures = ({'t15_flow_coefficients.png'} if task == 't15' else
               {f't16_{name}_response.png' for name in ['large_transfer', 'cex_net_inflow',
                                                       'activity_cohort_net_inflow', 'concentration']})
    expected_outputs = set(tables) | {f'{task}_report.md'} | figures
    require(set(summary['output_sha256']) == expected_outputs, 'Incomplete output manifest')
    require(set(summary['content_hashes']) == set(tables), 'Incomplete content hash map')
    reproduced = {}
    import pandas as pd
    for name, frame in tables.items():
        saved = pd.read_parquet(folder / name)
        expected = frame_hash(frame)
        require(frame_hash(saved) == expected, 'Independent recomputation differs: ' + name)
        require(summary['content_hashes'][name] == {'run1': expected, 'run2': expected}, 'Missing reproducibility evidence')
        reproduced[name] = expected
    require((folder / f'{task}_report.md').read_text(encoding='utf-8') == report(task, cfg, tables), 'Report differs')
    arithmetic = independent_arithmetic(task, cfg, loaded, tables)
    verify_hashes(expected_source); verify_hashes(loaded[4])
    result = dict(task=task, protocol_id=cfg['protocol_id'], all_pass=True,
        separate_process_recomputation=True, output_sha256=summary['output_sha256'],
        summary_sha256=file_hash(summary_path), content_hashes=reproduced,
        source_config_sha256=expected_source, input_sha256=loaded[4],
        independent_arithmetic_checks=arithmetic,
        caveat='Recomputation and arithmetic checks do not establish economic identification or forecasting performance.')
    json_write(folder / f'{task}_independent_review.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', choices=['t15', 't16', 'all'], default='all')
    args = parser.parse_args()
    for task in ['t15', 't16'] if args.task == 'all' else [args.task]:
        result = validate(task)
        print(json.dumps(dict(task=task, all_pass=result['all_pass'], tables=len(result['content_hashes']))))
