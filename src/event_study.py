"""T16: sự kiện UTC, cửa sổ không chồng nhau và bootstrap block theo sự kiện."""
import hashlib
import json

import numpy as np
import pandas as pd

from src.forecast_inputs import bool_column, finite, local_path, require, utc_daily, file_hash


def load_concentration(cfg, dates):
    path, meta = local_path(cfg['t11_snapshot']), local_path(cfg['t11_summary'])
    summary = json.loads(meta.read_text(encoding='utf-8'))
    require(summary.get('ready_for_downstream') is True and summary.get('independent_review_pass') is True,
            'T11 is not validated for downstream')
    repro = json.loads(local_path(cfg['t11_reproducibility']).read_text(encoding='utf-8'))
    pair = repro.get('hashes', {}).get(path.name, {})
    require(repro.get('all_match') is True and pair.get('run1') == pair.get('run2') == file_hash(path),
            'T11 snapshot differs from reproduced artifact')
    frame = pd.read_parquet(path)
    require('window_type' in frame and frame.window_type.eq('daily').all(), 'T11 snapshot must be daily')
    frame = utc_daily(frame.rename(columns={'time_window': 'date'}))
    require(frame.date.equals(dates.reset_index(drop=True)), 'T11/T14 calendar mismatch')
    require(finite(frame, ['community_concentration_index']).all(), 'Missing T11 concentration')
    require(frame.community_concentration_index.between(0, 1).all(), 'Invalid T11 concentration')
    return frame[['date', 'community_concentration_index']], summary


def thresholds(series, window, history, quantile):
    require(window >= history >= 1 and 0 < quantile < 1, 'Invalid event history/quantile')
    # Strictly earlier days; first 30 complete historical days required by frozen protocol.
    return series.shift(1).rolling(window, min_periods=history).quantile(quantile)


def detect(features, eligibility, concentration, gate, cfg):
    require(gate.get('forecast_inputs_ready_cex') is True, 'T14 CEX branch closed')
    require(gate.get('forecast_inputs_ready_activity_cohort') is True, 'T14 cohort branch closed')
    require(features.date.equals(concentration.date), 'Concentration calendar mismatch')
    options = [
        ('large_transfer', 'large_transfer_count', 'predictors_ready_pit_cex'),
        ('cex_net_inflow', 'pit_cex_netflow_z', 'predictors_ready_pit_cex'),
        ('activity_cohort_net_inflow', 'whaleflow_pit_z', 'predictors_ready_pit_whale'),
        ('concentration', 'community_concentration_index', None),
    ]
    df = features.merge(concentration, on='date', validate='one_to_one')
    rows = []
    for event, signal, eligible_col in options:
        observed = finite(df, [signal])
        if event in {'large_transfer', 'concentration'}:
            q = cfg['large_transfer_quantile'] if event == 'large_transfer' else cfg['concentration_quantile']
            threshold = thresholds(df[signal], cfg['lookback_days'], cfg['minimum_history_days'], q)
        else:
            threshold = pd.Series(float(cfg['flow_z_threshold']), index=df.index)
        available = observed & threshold.notna()
        if eligible_col:
            available &= bool_column(eligibility, eligible_col)
        if event == 'cex_net_inflow':
            available &= eligibility.pit_cex_z_status.eq('ok')
        if event == 'activity_cohort_net_inflow':
            available &= eligibility.whaleflow_pit_z_status.eq('ok')
        candidate = available & df[signal].gt(threshold)
        rows.append(pd.DataFrame(dict(date=df.date, available_at=df.date + pd.Timedelta(days=1),
            event_type=event, signal_column=signal,
            signal_value=df[signal], threshold=threshold, signal_available=available, candidate=candidate)))
    return df, pd.concat(rows, ignore_index=True)


def select_events(df, candidates, cfg):
    k = int(cfg['window_days'])
    require(k >= 1, 'Invalid event half-window')
    require(cfg['selection_policies'] == ['nonoverlap', 'all_events_sensitivity'], 'Unsupported event policy')
    responses = cfg['response_variables']
    response_ok = finite(df, responses)
    # Exclude boundary/missing-response windows identically for all variables: no changing n across tau.
    full_window = response_ok.rolling(2 * k + 1, center=True, min_periods=2 * k + 1).sum().eq(2 * k + 1)
    selections, windows = [], []
    dated = df.set_index('date')
    for event, source in candidates.groupby('event_type', sort=True):
        source = source.set_index('date').reindex(df.date).reset_index()
        valid_window = full_window.to_numpy()
        for policy in cfg['selection_policies']:
            last = None
            for i, row in enumerate(source.itertuples()):
                reason = 'not_candidate'
                selected = False
                if not row.signal_available:
                    reason = 'signal_unavailable'
                elif row.candidate:
                    if not valid_window[i]:
                        reason = 'incomplete_response_window'
                    elif policy == 'nonoverlap' and last is not None and (row.date - last).days <= 2 * k:
                        reason = 'cooldown'
                    else:
                        selected, reason, last = True, 'selected', row.date
                selections.append(dict(date=row.date, available_at=row.date + pd.Timedelta(days=1),
                    event_type=event, selection_policy=policy,
                    selected=selected, reason=reason, signal_value=row.signal_value, threshold=row.threshold))
                if selected:
                    for tau in range(-k, k + 1):
                        response_date = row.date + pd.Timedelta(days=tau)
                        values = dated.loc[response_date, responses]
                        windows.append(dict(event_type=event, selection_policy=policy, event_date=row.date,
                            event_available_at=row.date + pd.Timedelta(days=1),
                            response_date=response_date, tau=tau, **{v: float(values[v]) for v in responses}))
    window_cols = ['event_type', 'selection_policy', 'event_date', 'event_available_at', 'response_date', 'tau'] + responses
    return pd.DataFrame(selections), pd.DataFrame(windows, columns=window_cols)


def stable_seed(seed, event, policy, block):
    tag = f'{seed}|{event}|{policy}|{block}'.encode('utf-8')
    return int.from_bytes(hashlib.sha256(tag).digest()[:8], 'little')


def block_indices(n, block, resamples, seed):
    require(n > 0 and block >= 1 and resamples >= 100, 'Invalid bootstrap settings')
    # Circular moving blocks of chronologically adjacent complete event windows.
    length = min(n, block)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(resamples, int(np.ceil(n / length))))
    return ((starts[..., None] + np.arange(length)) % n).reshape(resamples, -1)[:, :n]


def statistics(windows, candidates, cfg):
    boot = cfg['bootstrap']
    require(0 < boot['alpha'] < 1 and boot['minimum_events'] >= 2, 'Invalid CI specification')
    blocks = [boot['primary_block_events']] + boot['sensitivity_block_events']
    require(len(blocks) == len(set(blocks)) and min(blocks) >= 1, 'Invalid bootstrap block lengths')
    k, variables = cfg['window_days'], cfg['response_variables']
    rows = []
    for event in sorted(candidates.event_type.unique()):
        for policy in cfg['selection_policies']:
            sub = windows[windows.event_type.eq(event) & windows.selection_policy.eq(policy)]
            n = int(sub.event_date.nunique())
            if n:
                sub = sub.sort_values(['event_date', 'tau'])
                require(len(sub) == n * (2 * k + 1), 'Incomplete extracted event windows')
                cube = sub[variables].to_numpy(float).reshape(n, 2 * k + 1, len(variables))
                require(np.isfinite(cube).all(), 'Nonfinite complete event window')
            for block in blocks:
                has_ci = n >= max(boot['minimum_events'], 2 * block)
                mean = cube.mean(axis=0) if n else np.full((2 * k + 1, len(variables)), np.nan)
                median = np.median(cube, axis=0) if n else mean.copy()
                lo = hi = np.full_like(mean, np.nan)
                if has_ci:
                    idx = block_indices(n, block, boot['resamples'], stable_seed(boot['seed'], event, policy, block))
                    # Joint resampling preserves the entire response path and cross-variable dependence.
                    means = cube[idx].mean(axis=1)
                    lo, hi = np.quantile(means, [boot['alpha'] / 2, 1 - boot['alpha'] / 2], axis=0)
                for j, tau in enumerate(range(-k, k + 1)):
                    for v, variable in enumerate(variables):
                        rows.append(dict(event_type=event, selection_policy=policy, block_events=block,
                            analysis_role='primary' if policy == 'nonoverlap' and block == boot['primary_block_events'] else 'sensitivity',
                            tau=tau, variable=variable, mean=float(mean[j, v]), median=float(median[j, v]),
                            ci_lower=float(lo[j, v]), ci_upper=float(hi[j, v]), n_events=n,
                            ci_status='available_exploratory' if has_ci else 'insufficient_events',
                            effective_block_events=min(n, block), seed=str(stable_seed(boot['seed'], event, policy, block))))
    return pd.DataFrame(rows)


def compute(features, eligibility, concentration, gate, cfg):
    variables = cfg['response_variables']
    require(len(variables) == len(set(variables)) and len(variables) > 0, 'Invalid response variable list')
    require(not any(v.startswith('target_') or v in {'date', 'available_at'} for v in variables), 'Invalid event response')
    require(cfg['bootstrap']['resamples'] >= 100 and cfg['bootstrap']['seed'] >= 0, 'Invalid bootstrap settings')
    df, candidates = detect(features, eligibility, concentration, gate, cfg)
    selection, windows = select_events(df, candidates, cfg)
    stats = statistics(windows, candidates, cfg)
    checks = []
    for event in sorted(candidates.event_type.unique()):
        primary = selection[selection.event_type.eq(event) & selection.selection_policy.eq('nonoverlap') & selection.selected]
        gaps = primary.date.sort_values().diff().dropna().dt.days
        require(gaps.gt(2 * cfg['window_days']).all(), 'Primary event windows overlap')
        checks.append(dict(check='complete_calendar_nonoverlapping_primary_windows', event_type=event,
                           status='PASS', n_events=len(primary)))
    require((windows.response_date - windows.event_date).dt.days.eq(windows.tau).all(), 'Incorrect event calendar offset')
    return {'t16_event_study_results.parquet': stats, 't16_event_selection.parquet': selection,
            't16_event_windows.parquet': windows, 't16_event_candidates.parquet': candidates,
            't16_validation.parquet': pd.DataFrame(checks)}
