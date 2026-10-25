"""T17: robustness of T15 (matched OLS/HAC) and T16 (event study) on the verified T14 release.

Nothing here edits T14/T15/T16 outputs. T17 recomputes the base scenario first and refuses to run
the grid if it does not reproduce the accepted T15/T16 results. Every scenario is reported; none is
selected by sign, p-value or size of the response. Findings are in-sample association, not causal
effects and not out-of-sample forecast evidence (that belongs to T18).
"""
import copy

import numpy as np
import pandas as pd

from src import event_study as events
from src import flow_volatility as fv
from src import volatility_regression as regression
from src.forecast_inputs import bool_column, finite, require
from src.graph_ml_features import window_bounds

BRANCH_RAW = {'activity_cohort': 'whaleflow_pit_usdt', 'cex': 'pit_cex_netflow_usdt'}
POLICIES = ['nonoverlap', 'all_events_sensitivity']
EVENT_FAMILIES = {'large_transfer': ['large_transfer'], 'concentration': ['concentration'],
                  'flow_z': ['cex_net_inflow', 'activity_cohort_net_inflow'], 'large_edge': ['large_transfer'],
                  'weekly_concentration': ['concentration']}


# ----------------------------------------------------------------------------- multiple testing
def holm(p):
    """Holm step-down adjusted p-values (same as statsmodels `holm`), NaN-safe for an empty family."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p, kind='mergesort')
    adjusted = np.minimum(1.0, (m - np.arange(m)) * p[order])
    adjusted = np.maximum.accumulate(adjusted)
    out = np.empty(m)
    out[order] = adjusted
    return out


# ----------------------------------------------------------------------------- independent HAC (matrix algebra)
def numpy_hac(y, X, lags):
    """OLS beta and Newey-West (Bartlett) HAC SE with n/(n-k) correction, by matrix algebra only."""
    y = np.asarray(y, float)
    X = np.column_stack([np.ones(len(y)), np.asarray(X, float)])
    n, k = X.shape
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    u = y - X @ beta
    xu = X * u[:, None]
    s = xu.T @ xu
    for lag in range(1, lags + 1):
        gamma = xu[lag:].T @ xu[:-lag]
        s += (1 - lag / (lags + 1)) * (gamma + gamma.T)
    cov = xtx_inv @ s @ xtx_inv * n / (n - k)
    return beta, np.sqrt(np.diag(cov))


# ----------------------------------------------------------------------------- flow windows
def trailing_flow_z(features, raw_column, k, norm):
    """z-score of the k-day trailing sum of a daily net flow, normalised from earlier days only.

    The k-day sum and the k-day volume both end at day D (known at D+1 00:00). A NaN day inside the window
    makes the sum NaN (never zero). Scale and z-score use windows [D-L, D), as in T14.
    """
    require(k >= 1, 'Invalid flow window')
    raw = features[raw_column].astype(float)
    volume = features['transfer_volume_usdt'].astype(float)
    if k > 1:
        raw, volume = raw.rolling(k, min_periods=k).sum(), volume.rolling(k, min_periods=k).sum()
    return fv.normalise_flow(raw, volume, norm)[1]


def trailing_leak_checks(features, norm, ks, cut_fractions, tolerance):
    """Truncation and future-mutation tests of the trailing-window flow z-scores."""
    rows = []
    n = len(features)
    for branch, raw in BRANCH_RAW.items():
        for k in ks:
            full = trailing_flow_z(features, raw, k, norm)
            for frac in cut_fractions:
                cut = int(frac * (n - 1))
                part = trailing_flow_z(features.iloc[:cut + 1].reset_index(drop=True), raw, k, norm)
                changed = features.copy()
                for col in [raw, 'transfer_volume_usdt']:
                    values = changed[col].to_numpy(float).copy()
                    values[cut + 1:] = values[cut + 1:] * 9.0 + 1.0e6
                    changed[col] = values
                mutated = trailing_flow_z(changed, raw, k, norm)
                for name, other in [('truncation', part), ('future_mutation', mutated)]:
                    a, b = full.iloc[:cut + 1].to_numpy(), other.iloc[:cut + 1].to_numpy()
                    same = np.array_equal(np.isnan(a), np.isnan(b)) and np.allclose(a[~np.isnan(a)], b[~np.isnan(b)],
                                                                                   rtol=tolerance, atol=tolerance)
                    rows.append(dict(check=f'trailing_flow_{name}', scope=f'{branch}:k={k}:cut={cut}',
                                     status='PASS' if same else 'FAIL', detail=''))
    return rows


# ----------------------------------------------------------------------------- regression grid
def regression_plan(cfg17, base_horizons):
    """Scenario list. Horizon definitions are never mixed inside one scenario."""
    plan = []
    for h in sorted(set(base_horizons) | set(cfg17['horizon']['extra_single_day'])):
        plan.append(dict(axis='horizon_single_day', definition='single_day', horizon_h=h, flow_window_days=1))
    for h in cfg17['horizon']['cumulative']:
        plan.append(dict(axis='horizon_cumulative', definition='sum_days', horizon_h=h, flow_window_days=1))
    for k in [1] + list(cfg17['flow_window']['trailing_days']):
        for h in base_horizons:
            plan.append(dict(axis='flow_window', definition='single_day', horizon_h=h, flow_window_days=k))
    for i, row in enumerate(plan):
        row['scenario_id'] = f"{row['axis']}|{row['definition']}|h{row['horizon_h']}|k{row['flow_window_days']}"
    require(len({r['scenario_id'] for r in plan}) == len(plan), 'Duplicate regression scenario')
    return plan


def run_regressions(features, eligibility, cfg15, cfg17, norm, fit=None, return_dates=False):
    """OLS/HAC with and without the flow on the same days; one row per scenario and branch."""
    fit = fit or regression.fit_hac
    controls = cfg15['controls'] + cfg15['extended_controls']
    base_h = list(cfg15['horizons'])
    finite(features, controls + ['rv', 'transfer_volume_usdt'])   # columns exist, no infinity
    plan = regression_plan(cfg17, base_h)
    targets, flows, rows, sample_dates = {}, {}, [], {}
    for scenario in plan:
        h, definition, k = scenario['horizon_h'], scenario['definition'], scenario['flow_window_days']
        if (definition, h) not in targets:
            targets[(definition, h)] = fv.forward_targets(features.rv, [h], definition)[f'target_log_rv_h{h}']
        for branch, opts in cfg15['branches'].items():
            if (branch, k) not in flows:
                flows[(branch, k)] = trailing_flow_z(features, BRANCH_RAW[branch], k, norm)
            ready = bool_column(eligibility, f'predictors_ready_{opts["eligibility"]}')
            work = features[['date'] + controls].copy()
            work['flow_z'] = flows[(branch, k)].to_numpy()
            work['target'] = targets[(definition, h)].to_numpy()
            work['cutoff'] = pd.to_datetime(features.available_at, utc=True).dt.as_unit('ns')
            selected = ready & finite(work, controls + ['flow_z', 'target'])
            sample = work.loc[selected]
            sample_dates[(scenario['scenario_id'], branch)] = pd.to_datetime(sample.date).dt.normalize().tolist()
            row = dict(scenario, branch=branch, n_obs=int(len(sample)), status='ok', error='',
                       sample_start=sample.date.min() if len(sample) else pd.NaT,
                       sample_end=sample.date.max() if len(sample) else pd.NaT)
            try:
                # every target window (single day D+h, or D+1..D+h) starts at D+1 00:00 UTC = the predictor cutoff
                require(((sample.date + pd.Timedelta(days=1)) >= sample.cutoff).all(), 'Target window precedes cutoff')
                base_rows, base_stats = fit(sample, 'target', controls, h, cfg15['minimum_observations'])
                rows_f, stats = fit(sample, 'target', controls + ['flow_z'], h, cfg15['minimum_observations'])
                effect = next(r for r in rows_f if r['variable'] == 'flow_z')
                row.update(r2_baseline=base_stats['r2'], r2=stats['r2'], delta_r2=stats['r2'] - base_stats['r2'],
                           coefficient=effect['coef'], hac_se=effect['hac_se'], t_stat=effect['t_stat'],
                           p_value=effect['p_value'], ci_lower=effect['ci_lower'], ci_upper=effect['ci_upper'],
                           maxlags_hac=stats['maxlags_hac'], condition_number=stats['condition_number_standardized'],
                           sample_dates_sha256=_date_hash(sample.date))
            except ValueError as error:
                row.update(status='failed', error=str(error))
            rows.append(row)
    table = pd.DataFrame(rows)
    table['p_holm_axis'] = np.nan
    for axis, group in table[table.status.eq('ok')].groupby('axis'):
        table.loc[group.index, 'p_holm_axis'] = holm(group.p_value.to_numpy())
    if return_dates:
        return table, sample_dates
    return table


def _date_hash(dates):
    import hashlib
    return hashlib.sha256(pd.util.hash_pandas_object(dates, index=False).to_numpy().tobytes()).hexdigest()


def regression_summary(table, base_horizons):
    """Descriptive recap per axis and branch: no scenario is picked or dropped."""
    ok = table[table.status.eq('ok')].copy()
    base = ok[ok.axis.eq('horizon_single_day') & ok.horizon_h.isin(base_horizons)].set_index(['branch', 'horizon_h']).coefficient
    rows = []
    for (axis, branch), g in ok.groupby(['axis', 'branch']):
        ref = [base.get((branch, h), np.nan) for h in g.horizon_h]
        rows.append(dict(axis=axis, branch=branch, n_scenarios=len(g), n_failed=int(((table.axis == axis) & (table.branch == branch) & table.status.ne('ok')).sum()),
                         coefficient_min=g.coefficient.min(), coefficient_max=g.coefficient.max(),
                         n_p_below_005=int((g.p_value < .05).sum()), n_p_holm_axis_below_005=int((g.p_holm_axis < .05).sum()),
                         n_same_sign_as_base_same_h=int((np.sign(g.coefficient.to_numpy()) == np.sign(ref)).sum()),
                         n_with_base_reference=int(np.isfinite(ref).sum()),
                         delta_r2_min=g.delta_r2.min(), delta_r2_max=g.delta_r2.max()))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- event grid
def event_plan(cfg17, cfg16):
    plan = [dict(scenario_id='base', axis='base', parameter='frozen_config', value='t16', family=None)]
    spec = [('large_transfer', 'large_transfer_quantile', cfg16['large_transfer_quantile'], cfg17['events']['large_transfer_quantile']),
            ('concentration', 'concentration_quantile', cfg16['concentration_quantile'], cfg17['events']['concentration_quantile']),
            ('flow_z', 'flow_z_threshold', cfg16['flow_z_threshold'], cfg17['events']['flow_z_threshold']),
            ('large_edge', 'large_edge_percentile', None, cfg17['events']['large_edge_percentile'])]
    for family, parameter, base, values in spec:
        for value in values:
            require(base is None or float(value) != float(base), 'Alternative equals the frozen base value')
            plan.append(dict(scenario_id=f'{parameter}={value}', axis=family, parameter=parameter, value=float(value), family=family))
    if cfg17['events'].get('weekly_concentration'):
        plan.append(dict(scenario_id='concentration_window=weekly', axis='weekly_concentration', parameter='graph_window',
                         value='weekly', family='weekly_concentration'))
    return plan


def weekly_concentration_frame(weekly_snapshot, dates):
    """T11 weekly concentration index placed on the last day of each fully completed ISO week.

    The index is available at the week end, which equals D+1 00:00 UTC of that last day, so it matches the
    daily cutoff convention. All other days are NaN (signal unavailable, never replicated or zero).
    """
    frame = weekly_snapshot
    require(frame.window_type.eq('weekly').all(), 'T11 weekly snapshot must be weekly')
    require(not frame.duplicated('time_window').any(), 'Duplicate T11 weekly window')
    bounds = window_bounds(frame, 'weekly')
    require((bounds.window_start.iloc[1:].to_numpy() == bounds.window_end.iloc[:-1].to_numpy()).all(), 'Weekly calendar gap')
    value = frame.set_index('time_window').community_concentration_index
    require(value.between(0, 1).all(), 'Invalid weekly concentration')
    complete = bounds[bounds.eligible_for_regression.astype(bool) & ~bounds.is_partial_week.astype(bool)]
    last_day = (complete.window_end - pd.Timedelta(days=1)).dt.normalize()
    series = pd.Series(value.reindex(complete.time_window).to_numpy(), index=pd.DatetimeIndex(last_day).as_unit('ns'))
    require(not series.index.duplicated().any(), 'Weekly windows share a last day')
    out = pd.DataFrame({'date': pd.DatetimeIndex(dates).as_unit('ns')})
    out['community_concentration_index'] = series.reindex(out.date).to_numpy()
    return out


def _variant(cfg16, scenario, cfg17):
    cfg = copy.deepcopy(cfg16)
    if scenario['parameter'] == 'large_transfer_quantile':
        cfg['large_transfer_quantile'] = scenario['value']
    elif scenario['parameter'] == 'concentration_quantile':
        cfg['concentration_quantile'] = scenario['value']
    elif scenario['parameter'] == 'flow_z_threshold':
        cfg['flow_z_threshold'] = scenario['value']
    elif scenario['parameter'] == 'graph_window':
        cfg['minimum_history_days'] = int(cfg17['events']['weekly_minimum_history_values'])
    return cfg


def _post_minus_pre(windows, event, policy, variable, k):
    sub = windows[windows.event_type.eq(event) & windows.selection_policy.eq(policy)]
    if sub.empty:
        return np.array([]), []
    post = sub[sub.tau.between(0, k)].groupby('event_date')[variable].mean()
    pre = sub[sub.tau.between(-k, -1)].groupby('event_date')[variable].mean()
    diff = (post - pre).sort_index()
    return diff.to_numpy(float), list(diff.index)


def summarize_events(tables, scenario, base_selected, cfg16):
    """Counts, overlap with the base selection and a block-bootstrap CI of (post - pre) mean response."""
    cand, sel, windows = tables['t16_event_candidates.parquet'], tables['t16_event_selection.parquet'], tables['t16_event_windows.parquet']
    boot, k = cfg16['bootstrap'], int(cfg16['window_days'])
    rows = []
    affected = EVENT_FAMILIES.get(scenario['family'], sorted(cand.event_type.unique())) if scenario['family'] else sorted(cand.event_type.unique())
    for event in affected:
        c = cand[cand.event_type.eq(event)]
        for policy in POLICIES:
            chosen = sel[sel.event_type.eq(event) & sel.selection_policy.eq(policy) & sel.selected]
            dates = set(chosen.date)
            base = base_selected.get((event, policy), set())
            union = dates | base
            row = dict(scenario_id=scenario['scenario_id'], axis=scenario['axis'], parameter=scenario['parameter'], value=str(scenario['value']),
                       event_type=event, selection_policy=policy, signal_available_days=int(c.signal_available.sum()),
                       n_candidates=int(c.candidate.sum()), n_events=len(dates), n_events_base=len(base),
                       jaccard_with_base=len(dates & base) / len(union) if union else np.nan)
            for variable in ['log_rv', 'log_volume_usdt']:
                diff, _ = _post_minus_pre(windows, event, policy, variable, k)
                block = int(boot['primary_block_events'])
                n = len(diff)
                row[f'{variable}_post_minus_pre'] = float(diff.mean()) if n else np.nan
                lo = hi = np.nan
                status = 'insufficient_events'
                if n >= max(boot['minimum_events'], 2 * block):
                    seed = events.stable_seed(boot['seed'], f"{event}|{scenario['scenario_id']}", policy, block)
                    idx = events.block_indices(n, block, boot['resamples'], seed)
                    lo, hi = np.quantile(diff[idx].mean(axis=1), [boot['alpha'] / 2, 1 - boot['alpha'] / 2])
                    status = 'available_exploratory'
                row[f'{variable}_ci_lower'], row[f'{variable}_ci_upper'], row[f'{variable}_ci_status'] = float(lo), float(hi), status
            rows.append(row)
    return rows


def run_events(features, eligibility, concentration, weekly, edge_counts, gate, cfg16, cfg17):
    """Base run plus one-at-a-time variants; returns summary rows and the base tables for reconciliation."""
    plan = event_plan(cfg17, cfg16)
    base_tables = events.compute(features, eligibility, concentration, gate, cfg16)
    base_sel = base_tables['t16_event_selection.parquet']
    base_selected = {(e, p): set(g.date) for (e, p), g in base_sel[base_sel.selected].groupby(['event_type', 'selection_policy'])}
    rows = []
    for scenario in plan:
        if scenario['scenario_id'] == 'base':
            tables = base_tables
        else:
            feat, conc = features, concentration
            if scenario['parameter'] == 'large_edge_percentile':
                feat = features.copy()
                feat['large_transfer_count'] = edge_counts[scenario['value']].to_numpy()
            if scenario['parameter'] == 'graph_window':
                conc = weekly
            tables = events.compute(feat, eligibility, conc, gate, _variant(cfg16, scenario, cfg17))
        rows.extend(summarize_events(tables, scenario, base_selected, cfg16))
    return pd.DataFrame(rows), base_tables, plan


def large_edge_counts(edges, dates, percentiles, t14_cfg):
    """large_transfer_count with another edge percentile, by the same past-only T14 function (CEX set not needed)."""
    lt = t14_cfg['large_transfer']
    out = {}
    for p in percentiles + [lt['percentile']]:
        frame = fv.large_transfer_flow(edges, frozenset(), dates, float(p), lt['lookback_days'],
                                       lt['minimum_history_days'], lt['minimum_edges_in_history'])
        out[float(p)] = frame.large_transfer_count
    return out


# ----------------------------------------------------------------------------- reconciliation and validation
def reconcile_t15(table, t15_summary, base_horizons, tolerance, t15_membership=None, sample_dates=None):
    rows = []
    primary = t15_summary[t15_summary.model.eq('primary')].set_index(['branch', 'horizon_h'])
    baseline = t15_summary[t15_summary.model.eq('matched_baseline')].set_index(['branch', 'horizon_h'])
    ok = table[table.axis.eq('horizon_single_day') & table.horizon_h.isin(base_horizons) & table.status.eq('ok')]
    for r in ok.itertuples():
        a, b = primary.loc[(r.branch, r.horizon_h)], baseline.loc[(r.branch, r.horizon_h)]
        same = (r.n_obs == a.n_obs and abs(r.r2 - a.r2) <= tolerance and abs(r.coefficient - a.coefficient) <= tolerance
                and abs(r.p_value - a.p_value) <= tolerance and abs(r.r2_baseline - b.r2) <= tolerance)
        rows.append(dict(check='base_scenario_reproduces_accepted_t15', scope=f'{r.branch}:h{r.horizon_h}',
                         status='PASS' if same else 'FAIL', detail=''))
        if t15_membership is not None and sample_dates is not None:
            t15_dates = set(pd.to_datetime(t15_membership[t15_membership.branch.eq(r.branch) &
                                                          t15_membership.horizon_h.eq(r.horizon_h) &
                                                          t15_membership.selected]['date']).dt.normalize())
            base_id = f"horizon_single_day|single_day|h{r.horizon_h}|k1"
            my_dates = set(sample_dates.get((base_id, r.branch), []))
            dates_match = (my_dates == t15_dates)
            rows.append(dict(check='base_scenario_dates_identical_to_t15_membership', scope=f'{r.branch}:h{r.horizon_h}',
                             status='PASS' if dates_match else 'FAIL',
                             detail=f'n_dates={len(my_dates)}' if dates_match else f'mismatch:{len(my_dates)}!={len(t15_dates)}'))
    rows.append(dict(check='all_base_horizon_scenarios_present', scope='t15',
                     status='PASS' if len(ok) == 2 * len(base_horizons) else 'FAIL', detail=str(len(ok))))
    return rows


def reconcile_t16(base_tables, t16_selection, t16_candidates):
    def chosen(sel):
        return {(e, p): sorted(g.date) for (e, p), g in sel[sel.selected].groupby(['event_type', 'selection_policy'])}
    same_sel = chosen(base_tables['t16_event_selection.parquet']) == chosen(t16_selection)
    cand_a = base_tables['t16_event_candidates.parquet'].groupby('event_type').candidate.sum().to_dict()
    cand_b = t16_candidates.groupby('event_type').candidate.sum().to_dict()
    return [dict(check='base_scenario_reproduces_accepted_t16_selection', scope='t16', status='PASS' if same_sel else 'FAIL', detail=''),
            dict(check='base_scenario_reproduces_accepted_t16_candidates', scope='t16', status='PASS' if cand_a == cand_b else 'FAIL', detail='')]


def structural_checks(features, table, cfg15, norm, tolerance, edge_counts=None, independent=None,
                      sample_dates=None, cfg17=None):
    rows = []

    def add(name, ok, detail='', scope='regression'):
        rows.append(dict(check=name, scope=scope, status='PASS' if bool(ok) else 'FAIL', detail=str(detail)))

    controls = cfg15['controls'] + cfg15['extended_controls']
    for branch, opts in cfg15['branches'].items():
        z = trailing_flow_z(features, BRANCH_RAW[branch], 1, norm)
        add('trailing_k1_equals_t14_z', np.allclose(z.to_numpy(), features[opts['predictor']].to_numpy(), rtol=tolerance, atol=tolerance, equal_nan=True), branch)
    for h in cfg15['horizons']:
        mine = fv.forward_targets(features.rv, [h], 'single_day')[f'target_log_rv_h{h}']
        add('recomputed_single_day_target_equals_t14', np.allclose(mine.to_numpy(), features[f'target_log_rv_h{h}'].to_numpy(), rtol=tolerance, atol=tolerance, equal_nan=True), f'h={h}')
    one = fv.forward_targets(features.rv, [1], 'sum_days')['target_log_rv_h1'].to_numpy()
    add('cumulative_h1_equals_single_day_h1', np.allclose(one, features.target_log_rv_h1.to_numpy(), equal_nan=True))
    add('controls_exclude_targets_and_calendar', not any(c.startswith('target_') or c in {'date', 'available_at'} for c in controls))
    add('all_scenarios_estimated', bool(table.status.eq('ok').all()), table.loc[table.status.ne('ok'), ['scenario_id', 'branch', 'error']].to_dict('records'))
    ok = table[table.status.eq('ok')]
    add('holm_not_below_raw_p', bool((ok.p_holm_axis + 1e-12 >= ok.p_value).all()))

    if sample_dates is not None and cfg17 is not None:
        all_strictly_nested = True
        for branch in cfg15['branches']:
            for h in cfg15['horizons']:
                base_id = f"horizon_single_day|single_day|h{h}|k1"
                base_dates = sample_dates.get((base_id, branch), [])
                base_set = set(base_dates)
                base_sorted = sorted(base_set)
                for k in cfg17['flow_window']['trailing_days']:
                    k_id = f"flow_window|single_day|h{h}|k{k}"
                    k_dates = sample_dates.get((k_id, branch), [])
                    k_set = set(k_dates)
                    is_subset = k_set.issubset(base_set)
                    dropped = base_set - k_set
                    expected_dropped = set(base_sorted[:k-1])
                    strictly_nested = is_subset and (dropped == expected_dropped)
                    if not strictly_nested:
                        all_strictly_nested = False
                    add('flow_window_sample_strictly_nested_in_base', strictly_nested,
                        f"n_k={len(k_set)},n_base={len(base_set)},dropped={len(dropped)}", scope=f'{branch}:h{h}:k{k}')
        add('flow_window_samples_nested_in_base_calendar', all_strictly_nested)
    else:
        add('flow_window_samples_nested_in_base_calendar', bool(ok.sample_start.ge(features.date.min()).all()))

    if edge_counts is not None:
        add('large_edge_base_percentile_reproduces_t14_count', np.allclose(
            edge_counts.to_numpy(), features.large_transfer_count.to_numpy(), rtol=tolerance, atol=tolerance, equal_nan=True), scope='events')
    if independent:
        for item in independent:
            add('statsmodels_hac_equals_matrix_algebra_beta_and_se', item['same'], item['scope'], scope='regression')
    return rows


def independent_hac_checks(features, eligibility, cfg15, norm, table, tolerance=1e-8):
    """Recompute beta and HAC SE of a few scenarios with matrix algebra and compare to the fitted result."""
    controls = cfg15['controls'] + cfg15['extended_controls']
    out = []
    ok = table[table.status.eq('ok')]
    picks = pd.concat([ok[ok.axis.eq('horizon_single_day')].groupby('branch').head(1),
                       ok[ok.axis.eq('flow_window') & ok.flow_window_days.gt(1)].groupby('branch').head(1),
                       ok[ok.axis.eq('horizon_cumulative')].groupby('branch').tail(1)])
    for r in picks.itertuples():
        opts = cfg15['branches'][r.branch]
        target = fv.forward_targets(features.rv, [r.horizon_h], r.definition)[f'target_log_rv_h{r.horizon_h}']
        work = features[['date'] + controls].copy()
        work['flow_z'] = trailing_flow_z(features, BRANCH_RAW[r.branch], r.flow_window_days, norm).to_numpy()
        work['target'] = target.to_numpy()
        selected = bool_column(eligibility, f'predictors_ready_{opts["eligibility"]}') & finite(work, controls + ['flow_z', 'target'])
        sample = work.loc[selected]
        beta, se = numpy_hac(sample.target, sample[controls + ['flow_z']], int(r.maxlags_hac))
        same = abs(beta[-1] - r.coefficient) <= tolerance * max(1, abs(r.coefficient)) and abs(se[-1] - r.hac_se) <= tolerance * max(1, abs(r.hac_se))
        out.append(dict(same=bool(same), scope=r.scenario_id + '|' + r.branch))
    return out
