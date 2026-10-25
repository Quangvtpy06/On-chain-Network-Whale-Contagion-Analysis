"""T18: fixed-origin pseudo-OOS, nhãn train khả dụng tại fit, benchmark cùng mẫu."""
import numpy as np
import pandas as pd

from src.event_study import block_indices, stable_seed
from src.forecast_inputs import allowed, bool_column, finite, require
from src.volatility_regression import fit_hac

MODELS = ['controls_baseline', 'flow_model', 'har_baseline', 'train_mean', 'last_log_rv']
EVENTS = ['activity_cohort_net_inflow', 'cex_net_inflow', 'concentration', 'large_transfer']


def timestamps(cfg):
    sp = cfg['split']
    end, start, fit, evaluation = [pd.Timestamp(sp[k], tz='UTC') if pd.Timestamp(sp[k]).tzinfo is None
        else pd.Timestamp(sp[k]).tz_convert('UTC') for k in
        ['train_feature_end', 'test_feature_start', 'fit_at', 'evaluation_at']]
    # Arrow promotes second-resolution timestamps to milliseconds on disk; use ns explicitly
    # so the persisted ledger and the in-memory availability contract have the same schema.
    end, start, fit, evaluation = [x.as_unit('ns') for x in [end, start, fit, evaluation]]
    require(start == end + pd.Timedelta(days=1), 'Train/test calendar must be adjacent')
    require(all(x == x.normalize() for x in [end, start, fit, evaluation]), 'Split cutoffs must be UTC midnight')
    require(fit <= start + pd.Timedelta(days=1) and fit > end, 'Fit must precede first forecast and follow train features')
    require(evaluation > fit, 'Evaluation precedes fit')
    require(sp['policy'] == 'fixed_coefficients', 'Only fixed-coefficient evaluation implemented')
    require(sp['holdout_status'] == 'retrospective_pseudo_oos_already_inspected', 'Do not claim an untouched holdout')
    return end, start, fit, evaluation


def ledger(features, eligibility, upstream, gate, cfg15, cfg):
    end, start, fit, evaluation = timestamps(cfg)
    require(upstream['horizon_definition'] == 'single_day', 'Unsupported horizon definition')
    require(features.date.min() <= end < features.date.max(), 'Split outside data calendar')
    controls = cfg15['controls'] + cfg15['extended_controls']
    require(len(set(controls)) == len(controls), 'Duplicate controls')
    require(set(cfg['har_controls']) <= set(controls), 'HAR terms must be in controls')
    require(not set(cfg['har_controls']) & {'date', 'available_at'}, 'Calendar in HAR model')
    rows = []
    for branch, opts in cfg15['branches'].items():
        require(gate.get(opts['readiness']) is True, 'Upstream branch closed: ' + branch)
        allowed(upstream, opts['predictor_set'], controls + [opts['predictor']])
        ready = bool_column(eligibility, f'predictors_ready_{opts["eligibility"]}')
        complete = finite(features, controls + [opts['predictor']])
        available = pd.to_datetime(features.available_at, utc=True).dt.as_unit('ns')
        for h in cfg15['horizons']:
            require(h in upstream['horizons'] and isinstance(h, int) and h >= 1, 'Invalid forecast horizon')
            target = f'target_log_rv_h{h}'
            outcome = finite(features, [target])
            upstream_eligible = bool_column(eligibility, f'eligible_{opts["eligibility"]}_h{h}')
            target_date = features.date + pd.Timedelta(days=h)
            label_at = target_date + pd.Timedelta(days=1)
            coarse_train = features.date.le(end)
            train = coarse_train & ready & complete & outcome & upstream_eligible & label_at.le(fit) & available.le(fit)
            predict = features.date.ge(start) & ready & complete & available.ge(fit) & available.le(evaluation)
            evaluate = predict & outcome & upstream_eligible & label_at.le(evaluation)
            purged = coarse_train & ready & complete & outcome & upstream_eligible & label_at.gt(fit)
            reason = np.select([train, purged, coarse_train, evaluate, predict],
                ['train', 'purged_unavailable_label', 'unavailable_train_inputs', 'test_evaluated', 'test_outcome_censored'],
                default='unavailable_test_inputs')
            rows.append(pd.DataFrame(dict(date=features.date, branch=branch, horizon_h=h,
                available_at=available, target_date=target_date, target_available_at=label_at,
                coarse_split=np.where(coarse_train, 'train', 'test'), fit_at=fit,
                predictors_ready=ready, complete_predictors=complete, upstream_eligible=upstream_eligible,
                outcome_observed=outcome, train_selected=train, purged=purged,
                predict_selected=predict, evaluate_selected=evaluate, status=reason)))
    return pd.concat(rows, ignore_index=True)


def forecast(features, membership, cfg15, cfg):
    _, _, fit, _ = timestamps(cfg)
    controls = cfg15['controls'] + cfg15['extended_controls']
    coefficient_rows, prediction_rows = [], []
    for (branch, h), group in membership.groupby(['branch', 'horizon_h'], sort=True):
        group = group.reset_index(drop=True)
        require(group.date.equals(features.date), 'Membership not aligned to feature calendar')
        target = f'target_log_rv_h{h}'
        train = features.loc[group.train_selected.to_numpy()]
        test = features.loc[group.predict_selected.to_numpy()]
        require(len(test) > 0, 'No ready test predictors: ' + branch)
        predictor = cfg15['branches'][branch]['predictor']
        trained = {}
        for model, columns in [('controls_baseline', controls), ('flow_model', controls + [predictor]),
                               ('har_baseline', cfg['har_controls'])]:
            rows, stats = fit_hac(train, target, columns, int(h), cfg15['minimum_observations'])
            for row in rows:
                coefficient_rows.append(dict(branch=branch, horizon_h=int(h), model=model, fit_at=fit,
                    predictors='|'.join(columns), train_first=train.date.min(), train_last=train.date.max(),
                    train_max_target_available_at=group.loc[group.train_selected, 'target_available_at'].max(),
                    **stats, **row))
            beta = {r['variable']: r['coef'] for r in rows}
            trained[model] = beta['const'] + test[columns].to_numpy(float) @ np.array([beta[c] for c in columns])
        trained['train_mean'] = np.full(len(test), train[target].mean())
        trained['last_log_rv'] = test.log_rv.to_numpy(float)
        selected = group[group.predict_selected].reset_index(drop=True)
        for model in MODELS:
            values = np.asarray(trained[model], float)
            require(np.isfinite(values).all(), 'Nonfinite forecast')
            prediction_rows.append(pd.DataFrame(dict(branch=branch, horizon_h=int(h), model=model,
                date=test.date.to_numpy(), available_at=selected.available_at,
                target_date=selected.target_date, target_available_at=selected.target_available_at,
                fit_at=fit, n_train=len(train), evaluate=selected.evaluate_selected,
                prediction_log_rv=values, actual_log_rv=test[target].to_numpy(float))))
    return pd.DataFrame(coefficient_rows), pd.concat(prediction_rows, ignore_index=True)


def score(predictions, cfg, n_families):
    boot = cfg['loss_bootstrap']
    require(boot['resamples'] >= 100 and boot['block_days'] >= 1 and boot['seed'] >= 0, 'Invalid loss bootstrap')
    require(0 < boot['alpha'] < 1, 'Invalid alpha')
    metrics, losses, contrasts = [], [], []
    for (branch, h), group in predictions.groupby(['branch', 'horizon_h'], sort=True):
        evaluated = group[group.evaluate].copy()
        pivot = evaluated.pivot(index='date', columns='model', values='prediction_log_rv').reindex(columns=MODELS)
        actual = evaluated.groupby('date').actual_log_rv.first().reindex(pivot.index)
        n = len(actual)
        if n:
            require(np.isfinite(pivot.to_numpy()).all() and np.isfinite(actual).all(), 'Unmatched scoring sample')
            expected = pd.date_range(pivot.index.min(), pivot.index.max(), freq='D')
            require(pivot.index.equals(expected), 'Loss bootstrap requires consecutive calendar days')
            squared = (pivot.sub(actual, axis=0)) ** 2
            absolute = pivot.sub(actual, axis=0).abs()
            for model in MODELS:
                for i, date in enumerate(pivot.index):
                    losses.append(dict(branch=branch, horizon_h=int(h), date=date, model=model,
                        squared_error_log_rv=float(squared[model].iloc[i]), absolute_error_log_rv=float(absolute[model].iloc[i])))
            sst = float(((actual - actual.mean()) ** 2).sum())
            mean_sse = float(squared.train_mean.sum())
            control_sse = float(squared.controls_baseline.sum())
        for model in MODELS:
            mse = float(squared[model].mean()) if n else np.nan
            metrics.append(dict(branch=branch, horizon_h=int(h), model=model, n_test=n,
                n_predicted=int(group[group.model.eq(model)].shape[0]),
                n_train=int(group.n_train.iloc[0]), mse=mse, rmse=np.sqrt(mse),
                mae=float(absolute[model].mean()) if n else np.nan,
                r2_vs_test_mean=1-float(squared[model].sum())/sst if n and sst > 0 else np.nan,
                r2_vs_train_mean_forecast=1-float(squared[model].sum())/mean_sse if n and mean_sse > 0 else np.nan,
                r2_vs_controls_forecast=1-float(squared[model].sum())/control_sse if n and control_sse > 0 else np.nan,
                status='available' if n >= cfg['minimum_test_observations'] else 'insufficient_test_observations'))
        diff = (squared.flow_model - squared.controls_baseline).to_numpy() if n else np.array([])
        ci = np.full(4, np.nan)
        ci_ok = n >= max(cfg['minimum_test_observations'], 2 * boot['block_days'])
        if ci_ok:
            idx = block_indices(n, boot['block_days'], boot['resamples'],
                stable_seed(boot['seed'], branch, f'h{h}_loss', boot['block_days']))
            means = diff[idx].mean(axis=1)
            a = boot['alpha']
            ci = np.quantile(means, [a/2, 1-a/2, a/(2*n_families), 1-a/(2*n_families)])
        contrasts.append(dict(branch=branch, horizon_h=int(h), n_test=n,
            mean_loss_difference=float(diff.mean()) if n else np.nan,
            ci_lower=ci[0], ci_upper=ci[1], family_ci_lower=ci[2], family_ci_upper=ci[3],
            family_size=n_families, block_days=boot['block_days'],
            ci_status='available_exploratory' if ci_ok else 'insufficient_test_observations'))
    return pd.DataFrame(metrics), pd.DataFrame(losses), pd.DataFrame(contrasts)


def event_holdout(selection, windows, cfg16, cfg):
    end, start, _, evaluation = timestamps(cfg)
    require(cfg['event_partition']['require_entire_response_window_in_split'] is True, 'Require pure response windows')
    require(cfg['event_partition']['selection_policies'] == cfg16['selection_policies'], 'Do not retune event policy')
    chosen = selection[selection.selected].copy().rename(columns={'date': 'event_date'})
    k = int(cfg16['window_days'])
    chosen['window_start'] = chosen.event_date - pd.Timedelta(days=k)
    chosen['window_end'] = chosen.event_date + pd.Timedelta(days=k)
    chosen['partition'] = np.select([chosen.window_end.le(end),
        chosen.window_start.ge(start) & (chosen.window_end + pd.Timedelta(days=1)).le(evaluation)],
        ['train', 'test'], default='boundary_excluded')
    require(not chosen.duplicated(['event_type', 'selection_policy', 'event_date']).any(), 'Duplicate event key')
    used = windows.merge(chosen[['event_type', 'selection_policy', 'event_date', 'partition']],
        on=['event_type', 'selection_policy', 'event_date'], validate='many_to_one')
    require((used.response_date-used.event_date).dt.days.eq(used.tau).all(), 'Event offset is not calendar days')
    boot = cfg16['bootstrap']; variables = cfg16['response_variables']
    counts, rows = [], []
    for event in EVENTS:
        for policy in cfg16['selection_policies']:
            for part in ['train', 'test', 'boundary_excluded']:
                n = int(chosen.event_type.eq(event).mul(chosen.selection_policy.eq(policy)).mul(chosen.partition.eq(part)).sum())
                counts.append(dict(event_type=event, selection_policy=policy, partition=part, n_events=n,
                    ci_status='available_exploratory' if n >= max(boot['minimum_events'], 2*boot['primary_block_events'])
                        and part != 'boundary_excluded' else 'insufficient_events' if part != 'boundary_excluded' else 'excluded'))
                if part == 'boundary_excluded':
                    continue
                sub = used[used.event_type.eq(event) & used.selection_policy.eq(policy) & used.partition.eq(part)]
                if n:
                    sub = sub.sort_values(['event_date', 'tau'])
                    require(len(sub) == n * (2*k+1), 'Incomplete selected event window')
                    cube = sub[variables].to_numpy(float).reshape(n, 2*k+1, len(variables))
                    require(np.isfinite(cube).all(), 'Missing event response')
                    contrast = cube[:, k:, :].mean(axis=1) - cube[:, :k, :].mean(axis=1)
                    values = np.concatenate([cube, contrast[:, None, :]], axis=1)
                    mean = values.mean(axis=0)
                else:
                    mean = np.full((2*k+2, len(variables)), np.nan)
                ci_ok = n >= max(boot['minimum_events'], 2*boot['primary_block_events'])
                lo = hi = np.full_like(mean, np.nan)
                if ci_ok:
                    idx = block_indices(n, boot['primary_block_events'], boot['resamples'],
                        stable_seed(boot['seed'], event, f'{policy}_{part}', boot['primary_block_events']))
                    lo, hi = np.quantile(values[idx].mean(axis=1), [boot['alpha']/2, 1-boot['alpha']/2], axis=0)
                for j in range(2*k+2):
                    for v, variable in enumerate(variables):
                        rows.append(dict(event_type=event, selection_policy=policy, partition=part, variable=variable,
                            statistic='path' if j <= 2*k else 'post_minus_pre', tau=j-k if j <= 2*k else None,
                            n_events=n, mean=float(mean[j,v]), ci_lower=float(lo[j,v]), ci_upper=float(hi[j,v]),
                            ci_status='available_exploratory' if ci_ok else 'insufficient_events'))
    return chosen.reset_index(drop=True), pd.DataFrame(counts), pd.DataFrame(rows)


def compute(loaded, cfg):
    f, e, upstream, gate, cfg15, cfg16, selection, windows = loaded
    member = ledger(f, e, upstream, gate, cfg15, cfg)
    coefficients, predictions = forecast(f, member, cfg15, cfg)
    metrics, losses, contrasts = score(predictions, cfg, len(cfg15['branches']) * len(cfg15['horizons']))
    partition, counts, event_stats = event_holdout(selection, windows, cfg16, cfg)
    return {'t18_sample_membership.parquet': member, 't18_coefficients.parquet': coefficients,
            't18_predictions.parquet': predictions, 't18_metrics.parquet': metrics,
            't18_daily_losses.parquet': losses, 't18_loss_comparison.parquet': contrasts,
            't18_event_partition.parquet': partition, 't18_event_counts.parquet': counts,
            't18_event_statistics.parquet': event_stats}
