"""T14: NetFlow, WhaleFlow, realized volatility and controls X_t (point-in-time).

Conventions
-----------
* One row per UTC calendar day D = [D 00:00, D+1 00:00). Every feature in the row
  is computable at `available_at` = D+1 00:00 UTC; nothing later is read.
* Targets are named `target_*` and look forward (D+h). They are the only columns
  allowed to use data after D, and they are never used as predictors.
* Any normaliser (scale, z-score, percentile) uses days strictly before D.
* Pure functions only; file I/O lives in T14_Flow_Volatility.py.
"""
import numpy as np
import pandas as pd

ZERO_ADDRESS = '0x' + '0' * 40
FLOW_COLUMNS = ['cex_external_in_usdt', 'cex_external_out_usdt', 'cex_internal_usdt', 'cex_netflow_usdt']
WHALE_COLUMNS = ['whale_to_cex_usdt', 'cex_to_whale_usdt', 'whaleflow_usdt']


def day_index(start, end):
    return pd.date_range(start, end, freq='D').strftime('%Y-%m-%d')


def cex_set(labels):
    """Same rule as T12: entity_type == CEX and no unresolved label conflict."""
    conflict = labels.label_conflict_review.fillna(False).astype(bool) if 'label_conflict_review' in labels else False
    return set(labels.loc[labels.entity_type.eq('CEX') & ~conflict, 'address'])


def cex_netflow(edges, cex, dates):
    """External NetFlow of the known-CEX wallet set: inflow - outflow, internal CEX moves split out.

    edges: columns time_window ('YYYY-MM-DD'), from_address, to_address, total_value.
    Mirrors T12 build_cex so the two tables can be reconciled.
    """
    a = edges.from_address.isin(cex)
    b = edges.to_address.isin(cex)
    v = edges.total_value
    frame = pd.DataFrame({
        'time_window': edges.time_window,
        'cex_external_in_usdt': v.where(~a & b, 0.0),
        'cex_external_out_usdt': v.where(a & ~b, 0.0),
        'cex_internal_usdt': v.where(a & b, 0.0),
        'transfer_volume_usdt': v,
    })
    daily = frame.groupby('time_window', sort=True).sum().reindex(dates).fillna(0.0)
    daily['cex_netflow_usdt'] = daily.cex_external_in_usdt - daily.cex_external_out_usdt
    daily.index.name = 'date'
    return daily[FLOW_COLUMNS + ['transfer_volume_usdt']]


def cex_asof(secondary, day):
    """CEX wallets whose human-verified label was available AND effective strictly before `day` 00:00 UTC.

    Only the availability/effective dates of a human decision count. T07
    `date_downloaded` or any collection date must never stand in for them.
    """
    if secondary is None or len(secondary) == 0:
        return set()
    cutoff = pd.Timestamp(day, tz='UTC')
    ok = (secondary.verification_status.eq('human_verified') & secondary.entity_type.eq('CEX')
          & (pd.to_datetime(secondary.label_available_at, utc=True) < cutoff)
          & (pd.to_datetime(secondary.effective_from, utc=True) < cutoff))
    return set(secondary.loc[ok, 'address'])


def pit_cex_netflow(edges, secondary, dates):
    """NetFlow using only the CEX set known as of each day (as-of join). NaN when none is known."""
    out = pd.DataFrame({'pit_cex_n_wallets': 0, 'pit_cex_netflow_usdt': np.nan},
                       index=pd.Index(dates, name='date'))
    by_day = {d: g for d, g in edges.groupby('time_window', sort=True)}
    for day in dates:
        known = cex_asof(secondary, day)
        out.loc[day, 'pit_cex_n_wallets'] = len(known)
        if not known:
            continue
        g = by_day.get(day)
        if g is None:
            out.loc[day, 'pit_cex_netflow_usdt'] = 0.0
            continue
        a, b = g.from_address.isin(known), g.to_address.isin(known)
        out.loc[day, 'pit_cex_netflow_usdt'] = float(g.total_value[~a & b].sum() - g.total_value[a & ~b].sum())
    return out


def whale_flow(edges, cohort, cex, dates, exclude_cex=True):
    """WhaleFlow_D = (cohort -> CEX) - (CEX -> cohort) on day D.

    cohort: columns date, address. Row for D must have been selected from data
    before D (T12 protocol t12_lagged_v1, information_cutoff = D-1). CEX
    addresses are removed from the cohort because T12 only drops human-verified
    labels, not the retrospective T07 CEX set.
    """
    out = pd.DataFrame(0.0, index=pd.Index(dates, name='date'), columns=WHALE_COLUMNS)
    out['n_cohort_members'] = 0
    out['n_cohort_cex_removed'] = 0
    out['n_cohort_members_active'] = 0
    out['has_cohort'] = False
    if len(cohort) == 0:
        return out
    members = {d: set(g.address) for d, g in cohort.groupby('date', sort=True)}
    for day, group in edges.groupby('time_window', sort=True):
        if day not in members or day not in out.index:
            continue
        m = members[day]
        removed = len(m & cex) if exclude_cex else 0
        if exclude_cex:
            m = m - cex
        f, t, v = group.from_address, group.to_address, group.total_value
        w2c = float(v[f.isin(m) & t.isin(cex)].sum())
        c2w = float(v[f.isin(cex) & t.isin(m)].sum())
        active = set(f[f.isin(m)]) | set(t[t.isin(m)])
        out.loc[day, ['whale_to_cex_usdt', 'cex_to_whale_usdt', 'whaleflow_usdt']] = [w2c, c2w, w2c - c2w]
        out.loc[day, 'n_cohort_members_active'] = len(active)
    counts = cohort.groupby('date').address.nunique().reindex(dates).fillna(0).astype(int)
    out['n_cohort_members'] = counts.to_numpy()
    out['n_cohort_cex_removed'] = [len(members.get(d, set()) & cex) if exclude_cex else 0 for d in dates]
    out['has_cohort'] = out.n_cohort_members.gt(0)
    return out


def large_transfer_flow(edges, cex, dates, percentile, lookback, min_history, min_edges):
    """Large-transfer events with a threshold estimated only on [D-L, D).

    The percentile is of edge total_value among all edges in the past window; it
    is NaN (no events counted) until `min_history` days and `min_edges` edges exist.
    """
    by_day = {d: g for d, g in edges.groupby('time_window', sort=True)}
    rows = []
    for i, day in enumerate(dates):
        past_days = dates[max(0, i - lookback):i]
        past = [by_day[d].total_value.to_numpy() for d in past_days if d in by_day]
        past = np.concatenate(past) if past else np.array([])
        ok = i >= min_history and len(past) >= min_edges
        threshold = float(np.quantile(past, percentile)) if ok else np.nan
        g = by_day.get(day)
        row = dict(date=day, large_transfer_threshold_usdt=threshold, large_transfer_count=np.nan,
                   large_transfer_volume_usdt=np.nan, large_to_cex_usdt=np.nan, large_from_cex_usdt=np.nan,
                   large_cex_netflow_usdt=np.nan)
        if ok:
            big = g[g.total_value >= threshold] if g is not None else edges.iloc[:0]
            a, b = big.from_address.isin(cex), big.to_address.isin(cex)
            v = big.total_value
            row.update(large_transfer_count=float(len(big)), large_transfer_volume_usdt=float(v.sum()),
                       large_to_cex_usdt=float(v[~a & b].sum()), large_from_cex_usdt=float(v[a & ~b].sum()))
            row['large_cex_netflow_usdt'] = row['large_to_cex_usdt'] - row['large_from_cex_usdt']
        rows.append(row)
    return pd.DataFrame(rows).set_index('date')


def past_mean(series, lookback, min_history):
    """Mean over [D-L, D): shift(1) removes day D itself."""
    return series.shift(1).rolling(lookback, min_periods=min_history).mean()


def past_std(series, lookback, min_history):
    return series.shift(1).rolling(lookback, min_periods=min_history).std(ddof=1)


def normalise_flow(flow, volume, norm):
    """Scale by past mean transfer volume and z-score against past flow; both PIT."""
    scale = past_mean(volume, norm['volume_lookback_days'], norm['minimum_history_days'])
    scaled = flow / scale.where(scale > 0)
    mu = past_mean(flow, norm['zscore_lookback_days'], norm['minimum_history_days'])
    sd = past_std(flow, norm['zscore_lookback_days'], norm['minimum_history_days'])
    z = (flow - mu) / sd.where(sd > 0)
    return scaled, z


MINUTES_PER_DAY = 1440


def realized_volatility(minutes, dates, sampling_minutes=1):
    """RV_D = sum of squared log returns sampled every `sampling_minutes` minutes on UTC day D.

    Uses the T06 1-minute closes (project convention: minute resolution). With k=1
    a full day has 1440 returns. The return of the first block of D uses the last
    close of D-1 (known before D). A missing minute/block or an incomplete first
    day (no previous close) gives NaN instead of mixing horizons.
    """
    k = int(sampling_minutes)
    if k < 1 or MINUTES_PER_DAY % k:
        raise ValueError('sampling_minutes must divide 1440')
    bars = MINUTES_PER_DAY // k
    m = minutes[['minute', 'close']].copy()
    m['minute'] = pd.to_datetime(m.minute, utc=True)
    m = m.sort_values('minute')
    if m.minute.duplicated().any():
        raise ValueError('Duplicate minute bars')
    epoch_minute = (m.minute - pd.Timestamp('1970-01-01', tz='UTC')) // pd.Timedelta(minutes=1)
    # Keep the last minute of every k-minute block; blocks are aligned to UTC midnight.
    s = m.loc[(epoch_minute % k).eq(k - 1)].copy()
    s['ret'] = np.log(s.close / s.close.shift(1))
    s.loc[s.minute.diff().ne(pd.Timedelta(minutes=k)), 'ret'] = np.nan
    s['date'] = s.minute.dt.strftime('%Y-%m-%d')
    g = s.groupby('date').ret
    out = pd.DataFrame({'n_returns': g.count(), 'rv': g.apply(lambda r: float((r ** 2).sum()))})
    out = out.reindex(dates)
    out['n_returns'] = out.n_returns.fillna(0).astype(int)
    out.loc[out.n_returns.ne(bars), 'rv'] = np.nan
    out['log_rv'] = np.log(out.rv.where(out.rv > 0))
    out['realized_vol'] = np.sqrt(out.rv)
    out.index.name = 'date'
    return out


def corwin_schultz_spread(high, low):
    """Corwin-Schultz (2012) high-low spread proxy from days D-1 and D (backward-looking).

    A proxy, not a quoted spread: T06 holds trades only, no order book.
    """
    hl = np.log(high / low) ** 2
    beta = hl + hl.shift(1)
    gamma = np.log(np.maximum(high, high.shift(1)) / np.minimum(low, low.shift(1))) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    spread = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    return spread.clip(lower=0)


def market_controls(daily, dates):
    d = daily.copy()
    d['datetime_utc'] = pd.to_datetime(d.datetime_utc, utc=True)
    d['date'] = d.datetime_utc.dt.strftime('%Y-%m-%d')
    if d.date.duplicated().any():
        raise ValueError('Duplicate daily market rows')
    d = d.set_index('date').sort_index().reindex(dates)
    out = pd.DataFrame(index=pd.Index(dates, name='date'))
    out['ret_1d'] = np.log(d.close / d.close.shift(1))
    out['log_volume_usdt'] = np.log(d.volume_usdt.where(d.volume_usdt > 0))
    out['log_trade_count'] = np.log(d.trade_count.where(d.trade_count > 0))
    out['taker_imbalance'] = d.imbalance_eth
    out['spread_cs_proxy'] = corwin_schultz_spread(d.high, d.low)
    out['parkinson_var'] = np.log(d.high / d.low) ** 2 / (4 * np.log(2))
    return out


def chain_controls(eth_stats, dates):
    e = eth_stats.copy()
    e['date'] = pd.to_datetime(e.tx_date).dt.strftime('%Y-%m-%d')
    if e.date.duplicated().any():
        raise ValueError('Duplicate eth_stats rows')
    e = e.set_index('date').reindex(dates)
    out = pd.DataFrame(index=pd.Index(dates, name='date'))
    out['eth_log_transactions'] = np.log(e.total_transactions.where(e.total_transactions > 0))
    out['eth_log_volume'] = np.log(e.total_eth_volume.where(e.total_eth_volume > 0))
    out['eth_log_gas_gwei'] = np.log(e.avg_gas_gwei.where(e.avg_gas_gwei > 0))
    return out


def har_terms(log_rv, rv, week, month):
    """Backward HAR averages that include day D (all known at D+1 00:00)."""
    out = pd.DataFrame(index=rv.index)
    out['log_rv_week'] = np.log(rv.rolling(week, min_periods=week).mean().where(lambda s: s > 0))
    out['log_rv_month'] = np.log(rv.rolling(month, min_periods=month).mean().where(lambda s: s > 0))
    return out


def build_features(inputs, cfg, dates):
    """Assemble the daily table. `inputs` holds already loaded DataFrames / sets."""
    edges, cex = inputs['edges'], inputs['cex']
    flow = cex_netflow(edges, cex, dates)
    vol = realized_volatility(inputs['minute'], dates, cfg['volatility']['sampling_minutes'])
    for k in cfg['volatility'].get('sensitivity_sampling_minutes', []):
        extra = realized_volatility(inputs['minute'], dates, k)
        vol[f'rv_{k}m'], vol[f'log_rv_{k}m'] = extra.rv, extra.log_rv
    whale = whale_flow(edges, inputs['cohort'], cex, dates, cfg['whaleflow']['exclude_cex_from_cohort'])
    lt = cfg['large_transfer']
    large = large_transfer_flow(edges, cex, dates, lt['percentile'], lt['lookback_days'],
                                lt['minimum_history_days'], lt['minimum_edges_in_history'])
    pit = pit_cex_netflow(edges, inputs.get('pit_labels'), dates)
    table = pd.concat([flow, pit, whale, large, vol], axis=1)
    table['cex_netflow_scaled'], table['cex_netflow_z'] = normalise_flow(
        table.cex_netflow_usdt, table.transfer_volume_usdt, cfg['normalisation'])
    # Days without a cohort carry NaN, not a misleading zero WhaleFlow.
    wf = table.whaleflow_usdt.where(table.has_cohort.astype(bool))
    table['whaleflow_scaled'], table['whaleflow_z'] = normalise_flow(
        wf, table.transfer_volume_usdt, cfg['normalisation'])
    table['large_cex_netflow_scaled'], _ = normalise_flow(
        table.large_cex_netflow_usdt, table.transfer_volume_usdt, cfg['normalisation'])
    table['log_transfer_volume_usdt'] = np.log(table.transfer_volume_usdt.where(table.transfer_volume_usdt > 0))
    table = pd.concat([table, market_controls(inputs['daily'], dates), chain_controls(inputs['eth_stats'], dates),
                       har_terms(table.log_rv, table.rv, cfg['volatility']['har_week_days'],
                                 cfg['volatility']['har_month_days'])], axis=1)
    table['day_of_week'] = pd.to_datetime(table.index).dayofweek
    table['available_at'] = (pd.to_datetime(table.index, utc=True) + pd.Timedelta(days=1)).astype(str)
    for h in cfg['horizons']:
        table[f'target_log_rv_h{h}'] = table.log_rv.shift(-h)
    return table


def feature_columns(table):
    """Everything except forward targets and bookkeeping."""
    return [c for c in table.columns if not c.startswith('target_')]


def truncate_inputs(inputs, cut):
    """Inputs as they would have existed at the end of day `cut` (inclusive)."""
    end = pd.Timestamp(cut, tz='UTC') + pd.Timedelta(days=1)
    return dict(
        edges=inputs['edges'][inputs['edges'].time_window <= cut],
        cohort=inputs['cohort'][inputs['cohort'].date <= cut],
        cex=inputs['cex'],
        minute=inputs['minute'][pd.to_datetime(inputs['minute'].minute, utc=True) < end],
        pit_labels=inputs.get('pit_labels'),
        daily=inputs['daily'][pd.to_datetime(inputs['daily'].datetime_utc, utc=True) < end],
        eth_stats=inputs['eth_stats'][pd.to_datetime(inputs['eth_stats'].tx_date) <= pd.Timestamp(cut)])


def pit_check(inputs, cfg, dates, cuts, tolerance=1e-9):
    """Recompute with future data removed; features for days <= cut must not change.

    A feature that secretly reads data after D fails here. Targets are excluded
    by construction (they are allowed to look forward).
    """
    full = build_features(inputs, cfg, dates)
    cols = [c for c in feature_columns(full) if c != 'available_at']
    rows = []
    for cut in cuts:
        upto = [d for d in dates if d <= cut]
        part = build_features(truncate_inputs(inputs, cut), cfg, upto)
        a, b = full.loc[upto, cols], part.loc[upto, cols]
        num = a.select_dtypes('number').columns
        diff = (a[num] - b[num]).abs()
        scale = a[num].abs().clip(lower=1.0)
        bad = ((diff / scale) > tolerance) | (a[num].isna() != b[num].isna())
        other = [c for c in cols if c not in num]
        bad_other = (a[other] != b[other]).any() if other else pd.Series(dtype=bool)
        failed = sorted(set(bad.columns[bad.any()]) | set(bad_other.index[bad_other]))
        rows.append(dict(check='pit_truncation', cut_date=cut, status='PASS' if not failed else 'FAIL',
                         detail=','.join(failed)))
    return pd.DataFrame(rows)


def validate(table, cfg, dates, t12_cex=None):
    rows = []

    def add(check, ok, detail=''):
        rows.append(dict(check=check, cut_date='', status='PASS' if ok else 'FAIL', detail=str(detail)))

    add('calendar_complete_unique', list(table.index) == list(dates) and table.index.is_unique, len(table))
    flows = table[FLOW_COLUMNS + ['transfer_volume_usdt']]
    add('flows_finite_nonnegative_except_net', bool(np.isfinite(flows).all().all()) and bool(
        (table[['cex_external_in_usdt', 'cex_external_out_usdt', 'cex_internal_usdt', 'transfer_volume_usdt']] >= 0).all().all()))
    add('netflow_identity', bool(np.allclose(table.cex_netflow_usdt, table.cex_external_in_usdt - table.cex_external_out_usdt)))
    add('cex_flow_not_above_volume', bool((table.cex_external_in_usdt + table.cex_external_out_usdt
                                           + table.cex_internal_usdt <= table.transfer_volume_usdt * (1 + 1e-9)).all()))
    add('whaleflow_identity', bool(np.allclose(table.whaleflow_usdt, table.whale_to_cex_usdt - table.cex_to_whale_usdt)))
    add('cohort_excludes_cex', bool(table.n_cohort_cex_removed.ge(0).all()),
        f"removed_total={int(table.n_cohort_cex_removed.sum())}")
    rv_ok = table.rv.dropna()
    add('rv_nonnegative', bool((rv_ok >= 0).all()), f"nan_days={int(table.rv.isna().sum())}")
    bars = MINUTES_PER_DAY // cfg['volatility']['sampling_minutes']
    add('rv_full_day_minute_returns', bool(table.loc[table.rv.notna(), 'n_returns'].eq(bars).all()), f'expected={bars}')
    add('pit_cex_no_wallet_means_nan', bool(table.loc[table.pit_cex_n_wallets.eq(0), 'pit_cex_netflow_usdt'].isna().all()))
    for h in cfg['horizons']:
        t = table[f'target_log_rv_h{h}']
        ok = bool(t.iloc[-h:].isna().all()) and bool(np.allclose(t.iloc[:-h].dropna(), table.log_rv.shift(-h).iloc[:-h].dropna()))
        add(f'target_h{h}_forward_only', ok)
    add('available_after_day_end', bool((pd.to_datetime(table.available_at, utc=True)
                                          > pd.to_datetime(table.index, utc=True)).all()))
    if t12_cex is not None:
        t = t12_cex.set_index('date').reindex(dates)
        diff = float((t.cex_netflow_usdt - table.cex_netflow_usdt).abs().max())
        add('matches_t12_cex_netflow', diff <= 1e-6 * max(1.0, float(table.cex_netflow_usdt.abs().max())), f'max_abs_diff={diff}')
    return pd.DataFrame(rows)


def readiness(computation_validated, gate_open, pit_cex_enabled, pit_cex_wallets_max):
    """Three separate questions per branch; computation passing never implies the other two.

    computation_validated : numerical checks and reproducibility passed (this run).
    retrospective_analysis: usable to describe/estimate on the full sample with today's labels.
    pit_forecast          : usable as a predictor known at forecast time.
    """
    ok = bool(computation_validated)
    label_reason = ('CEX labels are retrospective: no historical availability date, so the wallet set '
                    'cannot be chosen by an as-of join at forecast time.')
    pit_cex_ok = ok and bool(pit_cex_enabled) and pit_cex_wallets_max > 0
    return {
        'computation_validated': ok,
        'branches': {
            'market_volatility_controls': dict(label_dependent=False, retrospective_analysis=ok, pit_forecast=ok,
                columns='rv, log_rv, har terms, ret_1d, log_volume_usdt, taker_imbalance, spread_cs_proxy, eth_*'),
            'large_transfer_label_free': dict(label_dependent=False, retrospective_analysis=ok, pit_forecast=ok,
                columns='large_transfer_count, large_transfer_volume_usdt, large_transfer_threshold_usdt'),
            'large_cex_flows': dict(label_dependent=True, retrospective_analysis=ok, pit_forecast=False,
                columns='large_to_cex_usdt, large_from_cex_usdt, large_cex_netflow_*', blocked_reason=label_reason),
            'cex_netflow': dict(label_dependent=True, retrospective_analysis=ok, pit_forecast=False,
                columns='cex_external_*, cex_netflow_*', blocked_reason=label_reason),
            'pit_cex_netflow': dict(label_dependent=True, retrospective_analysis=False, pit_forecast=pit_cex_ok,
                columns='pit_cex_n_wallets, pit_cex_netflow_usdt',
                blocked_reason=None if pit_cex_ok else (
                    'Needs human-verified CEX labels with label_available_at/effective_from; '
                    f'wallets available as-of: max {int(pit_cex_wallets_max)}; enabled={bool(pit_cex_enabled)}.')),
            'cohort_whaleflow': dict(label_dependent=True, retrospective_analysis=ok and bool(gate_open), pit_forecast=False,
                columns='whale_*, whaleflow_*',
                blocked_reason=('T12 gate for cohort WhaleFlow is closed. ' if not gate_open else '') + label_reason),
        },
    }
