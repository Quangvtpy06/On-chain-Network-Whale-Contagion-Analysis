"""Scoped T14 input certification; never edits upstream gates or certifies ownership."""
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd

VERSION = 't14_inputs_v1'
PRODUCTS = ['t14_features_daily.parquet', 't14_cex_coverage_daily.parquet',
            't14_cex_coverage_monthly.parquet', 't14_cohort_cex_overlap_daily.parquet',
            't14_sample_eligibility_daily.parquet']
POLICY = dict(cex_scope='observed_approved_cex_subset',
              cohort_scope='unidentified_high_activity_addresses',
              endpoint_information_policy='approved_public_history_asof_day_start',
              cohort_information_policy='t12_v2_research_knowledge',
              boundary_policy='keep_membership_cohort_side_W_minus_C',
              individual_ownership_inference=False,
              selection_policy='frozen_without_regression_outcomes')


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def verify_hash_map(root, hashes, label):
    if not hashes:
        raise ValueError(f'{label}: empty hash map')
    root = Path(root).resolve()
    for rel, expected in hashes.items():
        path = (root / rel).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_hash(path) != expected:
            raise ValueError(f'{label}: changed or missing {rel}')


def contract_data_checks(inputs, table, settings, dates):
    """Independent calendar/RV/HAR/target checks and full T12 membership metadata."""
    rows = []

    def add(name, ok, detail=''):
        rows.append(dict(check='contract_' + name, cut_date='',
                         status='PASS' if bool(ok) else 'FAIL', detail=str(detail)))

    def same(a, b):
        return np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float),
                           rtol=1e-9, atol=1e-12, equal_nan=True)

    minute = inputs['minute'].sort_values('datetime_utc')
    stamps = pd.DatetimeIndex(pd.to_datetime(minute.datetime_utc, utc=True)).as_unit('ns')
    grid = pd.date_range(dates[0], periods=len(dates) * 1440, freq='min', tz='UTC').as_unit('ns')
    calendar_ok = stamps.equals(grid)
    add('minute_grid', calendar_ok, f'{len(stamps)}/{len(grid)}')
    close = minute.close.to_numpy(dtype=float)
    add('minute_positive_finite', np.isfinite(close).all() and (close > 0).all())
    if calendar_ok:
        ret = np.r_[np.nan, np.diff(np.log(close))].reshape(len(dates), 1440)
        rv = np.sum(ret ** 2, axis=1)  # first day intentionally lacks a pre-sample close
        ret5 = np.r_[np.nan, np.diff(np.log(close[::5]))].reshape(len(dates), 288)
        rv5 = np.sum(ret5 ** 2, axis=1)
        add('minute_rv_independent', same(table.rv, rv))
        add('five_minute_rv_independent', same(table.rv_5m, rv5))
        add('minute_return_counts', same(table.n_minute_returns, np.isfinite(ret).sum(axis=1)))
        add('five_minute_return_counts', same(table.n_5m_returns, np.isfinite(ret5).sum(axis=1)))
        for width, name in [(7, 'log_rv_week'), (30, 'log_rv_month')]:
            expected = [np.log(np.mean(rv[i-width+1:i+1])) if i >= width-1 else np.nan
                        for i in range(len(dates))]
            add(name + '_independent', same(table[name], expected))
        for horizon in settings['horizons']:
            expected = np.full(len(dates), np.nan)
            for i in range(len(dates) - horizon):
                window = rv[i+1:i+horizon+1]
                value = rv[i+horizon] if settings['target']['horizon_definition'] == 'single_day' else window.sum()
                if np.isfinite(value) and value > 0:
                    expected[i] = np.log(value)
            add(f'target_h{horizon}_independent', same(table[f'target_log_rv_h{horizon}'], expected))
    else:
        for name in ['minute_rv_independent', 'five_minute_rv_independent',
                     'minute_return_counts', 'five_minute_return_counts',
                     'log_rv_week_independent', 'log_rv_month_independent'] + [
                         f'target_h{h}_independent' for h in settings['horizons']]:
            add(name, False, 'minute grid invalid')
    cutoff = pd.to_datetime(table.available_at, utc=True)
    add('exact_available_at', (cutoff.to_numpy() ==
                              (pd.to_datetime(dates, utc=True) + pd.Timedelta(days=1)).to_numpy()).all())

    metadata = inputs['cohort_metadata']
    day = pd.to_datetime(metadata.date, utc=True)
    add('cohort_lag', ((pd.to_datetime(metadata.information_cutoff, utc=True) == day - pd.Timedelta(days=1)) &
                       (pd.to_datetime(metadata.window_start, utc=True) == day - pd.Timedelta(days=30))).all()
        and not metadata.empty)
    add('cohort_protocol_policy', metadata.protocol_id.eq(settings['t12_protocol_id']).all() and
        metadata.label_policy.eq('human_verified_available_by_cutoff_only').all() and not metadata.empty)
    add('cohort_membership_preserved', not metadata[['date', 'address']].duplicated().any() and
        set(zip(metadata.date, metadata.address)) == set(zip(inputs['cohort'].date, inputs['cohort'].address)))
    add('cohort_warmup_and_ranks', not metadata.empty and
        day.min() >= pd.Timestamp(dates[0], tz='UTC') + pd.Timedelta(days=30) and
        all(sorted(group.cohort_rank) == list(range(1, len(group) + 1)) and len(group) <= 50
            for _, group in metadata.groupby('date')))
    # Enforce the status classification rather than merely checking raw/z algebra.
    from src.flow_volatility import eligibility_table
    eligibility = eligibility_table(table, settings).set_index('date')
    raw = table.whaleflow_pit_usdt
    expected = []
    values = raw.to_numpy()
    for i, day_name in enumerate(dates):
        past = values[max(0, i-settings['normalisation']['zscore_lookback_days']):i]
        past = past[np.isfinite(past)]
        if not table.loc[day_name, 'has_cohort']:
            state = 'no_cohort'
        elif not np.isfinite(values[i]):
            state = 'missing_input'
        elif len(past) < settings['normalisation']['minimum_history_days']:
            state = 'insufficient_flow_history'
        elif np.std(past, ddof=1) == 0:
            state = 'zero_variance'
        else:
            state = 'ok'
        expected.append(state)
    add('cohort_warmup_status', eligibility.whaleflow_pit_z_status.tolist() == expected)
    return pd.DataFrame(rows)


def build_readiness(settings, gates, validation, repro_hashes):
    """Fail closed if required evidence is missing, not merely when an existing row fails."""
    conditions = {}

    def rows_pass(names, count=1):
        return all(len(validation[validation.check.eq(name)]) == count and
                   validation.loc[validation.check.eq(name), 'status'].eq('PASS').all() for name in names)

    conditions['computation_validated'] = (not validation.empty and validation.status.eq('PASS').all() and
        set(repro_hashes) == set(PRODUCTS) and all(
            bool(row.get('run1')) and row.get('run1') == row.get('run2') for row in repro_hashes.values()))
    conditions['contract_version'] = settings.get('readiness_contract_version') == VERSION
    conditions['scope_and_information_policy'] = settings.get('readiness_policy') == POLICY
    t07, t12 = gates['t07'], gates['t12']
    conditions['t07_endpoint_contract_verified'] = (t07.get('protocol_id') == settings['t07_protocol_id'] and
        t07.get('technical_validation_passed') is True and t07.get('ready_for_t14_endpoint_lookup') is True and
        not t07.get('blocking_reasons') and bool(t07.get('input_hashes')) and bool(t07.get('output_hashes')))
    conditions['t12_activity_contract_verified'] = (t12.get('protocol_id') == settings['t12_protocol_id'] and
        t12.get('ready_for_cohort_whaleflow') is True and not t12.get('blocking_reasons') and
        bool(t12.get('input_hashes')) and bool(t12.get('output_hashes')))
    conditions['calendar_and_target_separation'] = rows_pass([
        'calendar_complete_unique', 'calendar_expected_days', 'predictor_sets_clean',
        'pit_and_retro_predictors_disjoint', 'contract_exact_available_at'])
    conditions['future_information_tests'] = rows_pass(['pit_truncation', 'pit_future_label_mutation'], 4)
    conditions['cex_asof_usage_validated'] = (rows_pass(['independent_asof_subset']) and
        rows_pass(['adapter_matches_load_cex_for_cutoff'], 3) and
        len(validation[validation.check.str.startswith('label_boundary:')]) == 7 and
        validation.loc[validation.check.str.startswith('label_boundary:'), 'status'].eq('PASS').all())
    conditions['cex_flow_validated'] = rows_pass([
        'pit_netflow_identity', 'pit_flow_nan_iff_no_labels', 'pit_flow_not_above_volume',
        'pit_scaled_z_use_pit_flow', 'example_inflow', 'example_outflow', 'example_internal',
        'example_direction_reversal', 'example_conservation', 'example_no_labels_is_nan',
        'example_labels_no_edges_is_zero'])
    market = ['minute_grid', 'minute_positive_finite', 'minute_rv_independent',
              'five_minute_rv_independent', 'minute_return_counts', 'five_minute_return_counts',
              'log_rv_week_independent', 'log_rv_month_independent']
    conditions['market_targets_validated'] = rows_pass(['contract_' + n for n in market] +
        ['rv_sufficient_coverage'] + [f'contract_target_h{h}_independent' for h in settings['horizons']] +
        [f'target_h{h}_sufficient_coverage' for h in settings['horizons']])
    conditions['cohort_lag_membership_validated'] = rows_pass([
        'contract_cohort_lag', 'contract_cohort_protocol_policy', 'contract_cohort_membership_preserved',
        'contract_cohort_warmup_and_ranks', 'contract_cohort_warmup_status'])
    conditions['activity_scope_chosen'] = settings.get('whaleflow_scope') == 'v2_activity_cohort'
    conditions['overlap_boundary_validated'] = rows_pass([
        'overlap_matches_handoff_reference', 'cohort_overlap_nonnegative', 'whaleflow_pit_identity',
        'whaleflow_pit_scaled_z_use_pit_flow', 'whaleflow_pit_nan_iff_no_cohort_or_no_labels',
        'example_whaleflow', 'example_overlap_count_and_volume',
        'example_cex_to_whale_includes_overlap_node_as_cex'])
    cex_required = ['computation_validated', 'contract_version', 'scope_and_information_policy',
                    't07_endpoint_contract_verified', 'calendar_and_target_separation',
                    'future_information_tests', 'cex_asof_usage_validated', 'cex_flow_validated',
                    'market_targets_validated']
    activity_required = cex_required + ['t12_activity_contract_verified', 'cohort_lag_membership_validated',
                                        'activity_scope_chosen', 'overlap_boundary_validated']
    blockers = {branch: [name for name in required if not conditions[name]] for branch, required in
                [('cex', cex_required), ('activity_cohort', activity_required)]}
    return dict(contract_version=VERSION, conditions={k: bool(v) for k, v in conditions.items()},
                forecast_inputs_ready_cex=not blockers['cex'],
                forecast_inputs_ready_activity_cohort=not blockers['activity_cohort'],
                blocking_reasons=blockers, policy=POLICY,
                ready_for_individual_investor_inference=False, rq3_answered=False)
