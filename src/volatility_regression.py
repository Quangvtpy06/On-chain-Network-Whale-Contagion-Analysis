"""T15: OLS/HAC trên mẫu cố định; nghiên cứu liên hệ trong mẫu, không nhân quả."""
import hashlib
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from src.forecast_inputs import allowed, bool_column, finite, require


def fit_hac(sample, target, columns, horizon, minimum):
    require(len(sample) >= minimum, 'Insufficient regression observations')
    require(finite(sample, [target] + columns).all(), 'Incomplete fixed sample')
    dates = pd.DatetimeIndex(sample.date)
    require(dates.equals(pd.date_range(dates.min(), dates.max(), freq='D')), 'HAC sample has calendar gaps')
    design = sm.add_constant(sample[columns].astype(float), has_constant='add')
    # Standardize only to assess rank/conditioning; OLS coefficients remain in original units.
    scaled = (sample[columns] - sample[columns].mean()) / sample[columns].std(ddof=0)
    require(np.isfinite(scaled.to_numpy()).all(), 'Zero-variance regression predictor')
    check = np.column_stack([np.ones(len(sample)), scaled.to_numpy()])
    require(np.linalg.matrix_rank(check) == check.shape[1], 'Rank-deficient regression design')
    n = len(sample)
    lags = min(max(horizon, int(np.ceil(4 * (n / 100) ** (2 / 9)))), n // 5)
    result = sm.OLS(sample[target].astype(float), design, missing='raise').fit(
        cov_type='HAC', cov_kwds={'maxlags': lags, 'use_correction': True})
    require(np.isfinite(result.params).all() and np.isfinite(result.bse).all(), 'Invalid regression result')
    ci = result.conf_int(alpha=0.05)
    rows = [dict(variable=v, coef=float(result.params[v]), hac_se=float(result.bse[v]),
                 t_stat=float(result.tvalues[v]), p_value=float(result.pvalues[v]),
                 ci_lower=float(ci.loc[v, 0]), ci_upper=float(ci.loc[v, 1]),
                 significant_5pct=bool(result.pvalues[v] < .05)) for v in result.params.index]
    return rows, dict(n_obs=n, r2=float(result.rsquared), r2_adj=float(result.rsquared_adj),
                      maxlags_hac=lags, condition_number_standardized=float(np.linalg.cond(check)))


def compute(features, eligibility, upstream, gate, cfg):
    require(upstream['horizon_definition'] == 'single_day', 'Only single-day targets implemented')
    require(set(cfg['horizons']) <= set(upstream['horizons']), 'Unsupported horizon')
    controls = cfg['controls'] + cfg['extended_controls']
    require(len(controls) == len(set(controls)) and len(controls) > 0, 'Invalid controls')
    coefficient_rows, comparisons, membership, audit = [], [], [], []
    for branch, opts in cfg['branches'].items():
        require(gate.get(opts['readiness']) is True, 'T14 branch closed: ' + branch)
        main, retro = opts['predictor'], opts['retrospective_predictor']
        require(main not in controls and retro not in controls and main != retro, 'Predictor duplicated in controls')
        allowed(upstream, opts['predictor_set'], [main] + controls)
        allowed(upstream, opts['retrospective_set'], [retro] + controls)
        complete = finite(features, [main, retro] + controls)
        for h in cfg['horizons']:
            target = f'target_log_rv_h{h}'
            target_ok = finite(features, [target])
            ep = bool_column(eligibility, f'eligible_{opts["eligibility"]}_h{h}')
            er = bool_column(eligibility, f'eligible_{opts["retrospective_eligibility"]}_h{h}')
            # Retrospective is deliberately included in the fixed sample for a paired robustness comparison.
            selected = ep & er & complete & target_ok
            sample = features.loc[selected].copy()
            target_dates = sample.date + pd.Timedelta(days=h)
            require((target_dates >= pd.to_datetime(sample.available_at, utc=True)).all(), 'Target precedes cutoff')
            membership.append(pd.DataFrame(dict(date=features.date, branch=branch, horizon_h=h,
                upstream_eligible=ep, retrospective_eligible=er, complete_predictors=complete,
                target_available=target_ok, selected=selected)))
            models = {}
            for model, predictor in [('matched_baseline', None), ('primary', main), ('retrospective_robustness', retro)]:
                columns = controls + ([predictor] if predictor else [])
                rows, stats = fit_hac(sample, target, columns, h, cfg['minimum_observations'])
                models[model] = stats
                for row in rows:
                    coefficient_rows.append(dict(branch=branch, horizon_h=h, model=model,
                        predictor=main if predictor is None else predictor,
                        predictors='|'.join(columns), **stats, **row))
                effect = next((r for r in rows if r['variable'] == predictor), None)
                comparisons.append(dict(branch=branch, horizon_h=h, model=model, **stats,
                    sample_start=sample.date.min(), sample_end=sample.date.max(),
                    predictor=main if predictor is None else predictor,
                    coefficient=effect['coef'] if effect else np.nan,
                    p_value=effect['p_value'] if effect else np.nan,
                    significant_5pct=bool(effect and effect['significant_5pct']),
                    sample_dates_hash=hashlib.sha256(pd.util.hash_pandas_object(sample.date, index=False).to_numpy().tobytes()).hexdigest()))
            require(len({v['n_obs'] for v in models.values()}) == 1, 'Unmatched regression samples')
            delta = models['primary']['r2'] - models['matched_baseline']['r2']
            require(delta >= -1e-10, 'Nested OLS R2 decreased on identical sample')
            audit.append(dict(check='matched_sample_controls_and_nested_r2', branch=branch, horizon_h=h,
                              status='PASS', n_obs=len(sample), delta_r2=delta))
    coefs = pd.DataFrame(coefficient_rows)
    summary = pd.DataFrame(comparisons)
    summary['p_holm'] = np.nan
    summary['significant_holm_5pct'] = False
    # Six primary tests (2 branches x 3 horizons); retrospective tests form a separate robustness family.
    for model in ['primary', 'retrospective_robustness']:
        mask = summary.model.eq(model)
        reject, p, _, _ = multipletests(summary.loc[mask, 'p_value'], method='holm')
        summary.loc[mask, 'p_holm'] = p
        summary.loc[mask, 'significant_holm_5pct'] = reject
    coefs = coefs.merge(summary[['branch', 'horizon_h', 'model', 'p_holm', 'significant_holm_5pct']],
                        on=['branch', 'horizon_h', 'model'], validate='many_to_one')
    # Adjusted predictor p-values are model-level metadata, not adjusted control coefficient p-values.
    base = summary[summary.model.eq('matched_baseline')].set_index(['branch', 'horizon_h']).r2
    summary['delta_r2_vs_matched_baseline'] = [r.r2 - base.loc[(r.branch, r.horizon_h)] for r in summary.itertuples()]
    tables = {'t15_volatility_regression_results.parquet': coefs,
              't15_volatility_regression_summary.parquet': summary,
              't15_sample_membership.parquet': pd.concat(membership, ignore_index=True),
              't15_validation.parquet': pd.DataFrame(audit)}
    return tables
