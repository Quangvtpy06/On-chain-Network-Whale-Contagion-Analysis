"""T14: NetFlow, WhaleFlow, realized volatility and controls X_t (point-in-time).

Conventions
-----------
* One row per UTC calendar day D = [D 00:00, D+1 00:00). Every feature in the row
  is computable at `available_at` = D+1 00:00 UTC; nothing later is read.
* Targets are named `target_*` and look forward. They start at or after the
  cutoff D+1 00:00 UTC, so they never contain a day that feeds the predictors.
* Any normaliser (scale, z-score, percentile) uses days strictly before D.
* Two branches are kept apart and never mixed:
    - retrospective: CEX set = current T07 labels (not point-in-time evidence);
    - pit: CEX set C_D = approved public-history registry, public_available_at < D.
* Pure functions only; file I/O and gate verification live in T14_Flow_Volatility.py.
"""
import numpy as np
import pandas as pd

RETRO_FLOW_COLUMNS = ['cex_external_in_usdt', 'cex_external_out_usdt', 'cex_internal_usdt', 'cex_netflow_usdt']
FLOW_COLUMNS = RETRO_FLOW_COLUMNS
PIT_FLOW_COLUMNS = ['pit_cex_external_in_usdt', 'pit_cex_external_out_usdt', 'pit_cex_internal_usdt', 'pit_cex_netflow_usdt']
RETRO_WHALE_COLUMNS = ['whale_to_cex_usdt', 'cex_to_whale_usdt', 'whaleflow_usdt']
PIT_WHALE_COLUMNS = ['whale_to_cex_pit_usdt', 'cex_to_whale_pit_usdt', 'whaleflow_pit_usdt']
WHALE_COLUMNS = RETRO_WHALE_COLUMNS

# --- explicit predictor sets: the regression never sees metadata/readiness flags or targets ---
CONTROL_COLUMNS = ['ret_1d', 'log_volume_usdt', 'log_trade_count', 'taker_imbalance', 'spread_cs_proxy',
                   'parkinson_var', 'eth_log_transactions', 'eth_log_volume', 'eth_log_gas_gwei',
                   'log_transfer_volume_usdt', 'log_rv', 'log_rv_week', 'log_rv_month', 'day_of_week']
RETRO_CEX_PREDICTORS = ['cex_netflow_scaled', 'cex_netflow_z', 'large_cex_netflow_scaled']
RETRO_WHALE_PREDICTORS = ['whaleflow_scaled', 'whaleflow_z']
PIT_CEX_PREDICTORS = ['pit_cex_netflow_scaled', 'pit_cex_netflow_z', 'pit_large_cex_netflow_scaled']
PIT_WHALE_PREDICTORS = ['whaleflow_pit_scaled', 'whaleflow_pit_z']
BOOKKEEPING_COLUMNS = ['available_at', 'protocol_id', 'whaleflow_gate_open', 'cex_labels_pit', 'has_cohort',
                       'n_hourly_returns']


def predictor_sets():
    return {
        'retrospective_cex': RETRO_CEX_PREDICTORS + CONTROL_COLUMNS,
        'retrospective_whaleflow': RETRO_WHALE_PREDICTORS + CONTROL_COLUMNS,
        'pit_cex': PIT_CEX_PREDICTORS + CONTROL_COLUMNS,
        'pit_whaleflow': PIT_WHALE_PREDICTORS + CONTROL_COLUMNS,
    }


def day_index(start, end):
    return pd.date_range(start, end, freq='D').strftime('%Y-%m-%d')


def cex_set(labels):
    """RETROSPECTIVE rule (same as T12 v1): entity_type == CEX and no unresolved label conflict."""
    conflict = labels.label_conflict_review.fillna(False).astype(bool) if 'label_conflict_review' in labels else False
    return set(labels.loc[labels.entity_type.eq('CEX') & ~conflict, 'address'])


def normalise_cohort(cohort):
    c = cohort[['date', 'address']].copy()
    c['date'] = pd.to_datetime(c.date).dt.strftime('%Y-%m-%d')
    return c.drop_duplicates().reset_index(drop=True)


# ----------------------------------------------------------------------------- CEX sets as-of D

def asof_cex_sets(history, dates, labeler=None):
    """C_D for every day: approved public-history labels with public_available_at < D 00:00 UTC.

    `labeler(history, cutoff)` defaults to src.cex_label_history.available_cex_labels, the
    function that load_cex_for_cutoff itself uses after its gate/hash checks. The caller must have
    verified the history file against the T07 gate before calling this.
    """
    if labeler is None:
        from src.cex_label_history import available_cex_labels as labeler
    sets = {}
    for day in dates:
        labels = labeler(history, pd.Timestamp(day, tz='UTC'))
        sets[day] = frozenset(labels.address)
    return sets


# ----------------------------------------------------------------------------- retrospective NetFlow

def cex_netflow(edges, cex, dates):
    """RETROSPECTIVE external NetFlow of the current known-CEX set: inflow - outflow.

    CEX->CEX moves are reported in cex_internal_usdt and are not part of NetFlow.
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
    return daily[RETRO_FLOW_COLUMNS + ['transfer_volume_usdt']]


def pit_cex_netflow(edges, cex_by_day, dates):
    """PIT NetFlow with the per-day set C_D.

    Inflow: from not in C_D, to in C_D.   Outflow: from in C_D, to not in C_D.
    NetFlow = Inflow - Outflow; CEX->CEX is reported separately (internal), not in NetFlow.
    No labels available on D  -> all flows NaN (evidence unavailable, not zero).
    Labels but no transfers   -> 0.0 (observed zero).
    """
    by_day = dict(tuple(edges.groupby('time_window', sort=True)))
    empty = edges.iloc[:0]
    rows = []
    for day in dates:
        c = cex_by_day.get(day, frozenset())
        row = dict(date=day, n_pit_cex_endpoints=len(c), n_pit_cex_active=0)
        if not c:
            row.update({k: np.nan for k in PIT_FLOW_COLUMNS})
            rows.append(row)
            continue
        g = by_day.get(day, empty)
        a, b, v = g.from_address.isin(c), g.to_address.isin(c), g.total_value
        ext_in, ext_out = float(v[~a & b].sum()), float(v[a & ~b].sum())
        row.update(pit_cex_external_in_usdt=ext_in, pit_cex_external_out_usdt=ext_out,
                   pit_cex_internal_usdt=float(v[a & b].sum()), pit_cex_netflow_usdt=ext_in - ext_out,
                   n_pit_cex_active=len(c & (set(g.from_address) | set(g.to_address))))
        rows.append(row)
    return pd.DataFrame(rows).set_index('date')


# ----------------------------------------------------------------------------- WhaleFlow

def _boundary(f, t, v, members, cex):
    """cohort -> CEX minus CEX -> cohort on one day, with an explicit boundary rule.

    Boundary rule (must be confirmed by the team, see whaleflow_scope):
      * membership/rank of the T12 cohort W is untouched; W is NOT replaced by a new top-50.
      * a node in W ∩ C is treated as CEX infrastructure on the flow boundary, so only
        core = W \\ C acts as the cohort side;
      * edges inside C (CEX->CEX) and inside core are not WhaleFlow;
      * volume of every edge touching W ∩ C is reported (overlap_edge_usdt), never hidden.
    """
    core = members - cex
    f_core, t_core = f.isin(core), t.isin(core)
    f_c, t_c = f.isin(cex), t.isin(cex)
    w2c = float(v[f_core & t_c].sum())
    c2w = float(v[f_c & t_core].sum())
    overlap = members & cex
    overlap_edge = float(v[f.isin(overlap) | t.isin(overlap)].sum()) if overlap else 0.0
    active = len(core & (set(f) | set(t)))
    return w2c, c2w, overlap_edge, active


def whale_flow(edges, cohort, dates, cex_by_day=None, retro_cex=None):
    """WhaleFlow_D = (cohort -> CEX) - (CEX -> cohort) on day D, for two separate branches.

    PIT branch   : C_D from the approved public-history registry (cex_by_day).
    Retrospective: current T07 CEX set (retro_cex); a sensitivity only, never called PIT.
    NaN (not 0) when D has no cohort, or (PIT branch) no CEX label available on D.
    """
    cohort = normalise_cohort(cohort)
    members = {d: frozenset(g.address) for d, g in cohort.groupby('date', sort=True)}
    by_day = dict(tuple(edges.groupby('time_window', sort=True)))
    empty = edges.iloc[:0]
    rows = []
    for day in dates:
        w = members.get(day, frozenset())
        row = dict(date=day, n_cohort_members=len(w), has_cohort=bool(w),
                   whale_to_cex_usdt=np.nan, cex_to_whale_usdt=np.nan, whaleflow_usdt=np.nan,
                   whale_to_cex_pit_usdt=np.nan, cex_to_whale_pit_usdt=np.nan, whaleflow_pit_usdt=np.nan,
                   n_cohort_cex_retro_overlap=0, cohort_cex_pit_overlap=0,
                   overlap_edge_retro_usdt=np.nan, overlap_edge_pit_usdt=np.nan,
                   n_cohort_members_active=0, n_cohort_members_active_pit=0)
        if w:
            g = by_day.get(day, empty)
            f, t, v = g.from_address, g.to_address, g.total_value
            if retro_cex is not None:
                w2c, c2w, ov, act = _boundary(f, t, v, w, retro_cex)
                row.update(whale_to_cex_usdt=w2c, cex_to_whale_usdt=c2w, whaleflow_usdt=w2c - c2w,
                           overlap_edge_retro_usdt=ov, n_cohort_members_active=act,
                           n_cohort_cex_retro_overlap=len(w & retro_cex))
            if cex_by_day is not None:
                c = cex_by_day.get(day, frozenset())
                row['cohort_cex_pit_overlap'] = len(w & c)
                if c:
                    w2c, c2w, ov, act = _boundary(f, t, v, w, c)
                    row.update(whale_to_cex_pit_usdt=w2c, cex_to_whale_pit_usdt=c2w,
                               whaleflow_pit_usdt=w2c - c2w, overlap_edge_pit_usdt=ov,
                               n_cohort_members_active_pit=act)
        rows.append(row)
    return pd.DataFrame(rows).set_index('date')


def overlap_addresses(cohort, cex_by_day):
    """Unique cohort addresses that are in C_D on at least one of their member-days, and member-days."""
    cohort = normalise_cohort(cohort)
    hit = cohort[[a in cex_by_day.get(d, frozenset()) for d, a in zip(cohort.date, cohort.address)]]
    return set(hit.address), int(len(hit))


# ----------------------------------------------------------------------------- large transfers

def large_transfer_flow(edges, cex, dates, percentile, lookback, min_history, min_edges):
    """Large-transfer events with a threshold estimated only on [D-L, D) (retrospective CEX set).

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


def pit_large_flow(edges, threshold, cex_by_day, dates):
    """Large-transfer CEX NetFlow with C_D, reusing the past-only threshold. NaN if no threshold or no labels."""
    by_day = dict(tuple(edges.groupby('time_window', sort=True)))
    empty = edges.iloc[:0]
    vals = []
    for day in dates:
        c, thr = cex_by_day.get(day, frozenset()), threshold.get(day, np.nan)
        if not c or not np.isfinite(thr):
            vals.append(np.nan)
            continue
        g = by_day.get(day, empty)
        big = g[g.total_value >= thr]
        a, b, v = big.from_address.isin(c), big.to_address.isin(c), big.total_value
        vals.append(float(v[~a & b].sum() - v[a & ~b].sum()))
    return pd.Series(vals, index=pd.Index(dates, name='date'), name='pit_large_cex_netflow_usdt')


# ----------------------------------------------------------------------------- normalisation, volatility, controls

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


def realized_volatility_minute(minute, dates, bars_per_day=1440, sensitivity_bars=288):
    """RV_D = sum of squared 1-minute log returns of UTC day D (baseline 1440 bars).
    Also computes 5-minute sensitivity RV_D_5m (288 bars).
    """
    m = minute[['datetime_utc', 'close']].copy()
    m['datetime_utc'] = pd.to_datetime(m.datetime_utc, utc=True)
    m = m.sort_values('datetime_utc')
    if m.datetime_utc.duplicated().any():
        raise ValueError('Duplicate minute bars')
    if m.close.isna().any() or not (m.close > 0).all():
        raise ValueError('Minute close must be present and > 0')

    ts = m.datetime_utc
    if not ((ts.dt.second == 0) & (ts.dt.microsecond == 0) & (ts.dt.nanosecond == 0)).all():
        raise ValueError('Minute bars are not aligned to UTC minute boundaries (second=0, microsecond=0); fix the input, do not round')

    m['ret_1m'] = np.log(m.close / m.close.shift(1))
    gap_1m = m.datetime_utc.diff().ne(pd.Timedelta(minutes=1))
    m.loc[gap_1m, 'ret_1m'] = np.nan
    m['date'] = m.datetime_utc.dt.strftime('%Y-%m-%d')

    g1 = m.groupby('date').ret_1m
    out = pd.DataFrame({'n_minute_returns': g1.count(), 'rv': g1.apply(lambda r: float((r ** 2).sum()))})
    out = out.reindex(dates)
    out['n_minute_returns'] = out.n_minute_returns.fillna(0).astype(int)
    out.loc[out.n_minute_returns.ne(bars_per_day), 'rv'] = np.nan
    out['log_rv'] = np.log(out.rv.where(out.rv > 0))
    out['realized_vol'] = np.sqrt(out.rv)

    # 5-minute sensitivity
    m_5m = m[m.datetime_utc.dt.minute % 5 == 0].copy()
    m_5m['ret_5m'] = np.log(m_5m.close / m_5m.close.shift(1))
    gap_5m = m_5m.datetime_utc.diff().ne(pd.Timedelta(minutes=5))
    m_5m.loc[gap_5m, 'ret_5m'] = np.nan
    g5 = m_5m.groupby('date').ret_5m
    out['rv_5m'] = g5.apply(lambda r: float((r ** 2).sum()))
    out['n_5m_returns'] = g5.count().reindex(dates).fillna(0).astype(int)
    out.loc[out.n_5m_returns.ne(sensitivity_bars), 'rv_5m'] = np.nan
    out['realized_vol_5m'] = np.sqrt(out.rv_5m)

    out.index.name = 'date'
    return out


def realized_volatility(hourly, dates, bars_per_day=24):
    """RV_D = sum of squared hourly log returns of UTC day D; NaN unless all bars exist.

    rv = sum(r^2) (variance scale, unitless); realized_vol = sqrt(rv); log_rv = log(rv) only if rv > 0
    (rv == 0 gives NaN, never a filled value). The return of the first hour of D uses the last close
    of D-1, so a day whose previous close is missing has fewer returns and is NaN, not rescaled.
    """
    h = hourly[['datetime_utc', 'close']].copy()
    h['datetime_utc'] = pd.to_datetime(h.datetime_utc, utc=True)
    h = h.sort_values('datetime_utc')
    if h.datetime_utc.duplicated().any():
        raise ValueError('Duplicate hourly bars')
    if h.close.isna().any() or not (h.close > 0).all():
        raise ValueError('Hourly close must be present and > 0')
    ts = h.datetime_utc
    if not ((ts.dt.minute == 0) & (ts.dt.second == 0) & (ts.dt.microsecond == 0) & (ts.dt.nanosecond == 0)).all():
        raise ValueError('Hourly bars are not aligned to UTC hour boundaries; fix the input, do not round')
    h['ret'] = np.log(h.close / h.close.shift(1))
    # A gap would turn one return into a multi-hour return; blank it instead of mixing horizons.
    gap = h.datetime_utc.diff().ne(pd.Timedelta(hours=1))
    h.loc[gap, 'ret'] = np.nan
    h['date'] = h.datetime_utc.dt.strftime('%Y-%m-%d')
    g = h.groupby('date').ret
    out = pd.DataFrame({'n_hourly_returns': g.count(), 'rv': g.apply(lambda r: float((r ** 2).sum()))})
    out = out.reindex(dates)
    out['n_hourly_returns'] = out.n_hourly_returns.fillna(0).astype(int)
    out.loc[out.n_hourly_returns.ne(bars_per_day), 'rv'] = np.nan
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


def forward_targets(rv, horizons, definition):
    """Targets start after the cutoff D+1 00:00 UTC.

    single_day: log RV of the one day D+h.
    sum_days  : log of sum of daily RV over D+1 ... D+h (needs all h days).
    """
    out = {}
    for h in horizons:
        if definition == 'single_day':
            value = rv.shift(-h)
        elif definition == 'sum_days':
            value = rv.iloc[::-1].rolling(h, min_periods=h).sum().iloc[::-1].shift(-1)
        else:
            raise ValueError(f'Unknown horizon_definition: {definition}')
        out[f'target_log_rv_h{h}'] = np.log(value.where(value > 0))
    return pd.DataFrame(out, index=rv.index)


# ----------------------------------------------------------------------------- feature table

def build_features(inputs, cfg, dates):
    """Assemble the daily table. `inputs` holds already loaded DataFrames / sets.

    `cex` (retrospective set) feeds the retrospective branch; `cex_history` (verified T07 registry)
    feeds the PIT branch. Each branch is normalised from its own flow, never from the other one.
    """
    edges, cex = inputs['edges'], inputs['cex']
    history = inputs.get('cex_history')
    cex_by_day = asof_cex_sets(history, dates, inputs.get('labeler')) if history is not None else None
    flow = cex_netflow(edges, cex, dates)
    if inputs.get('minute') is not None:
        bars = cfg['volatility'].get('bars_per_day', 1440)
        vol = realized_volatility_minute(inputs['minute'], dates, bars_per_day=bars,
                                         sensitivity_bars=cfg['volatility'].get('sensitivity_bars_per_day', 288))
    else:
        bars = cfg['volatility'].get('bars_per_day', 24)
        vol = realized_volatility(inputs['hourly'], dates, bars_per_day=bars)
    whale = whale_flow(edges, inputs['cohort'], dates, cex_by_day=cex_by_day, retro_cex=cex)
    lt = cfg['large_transfer']
    large = large_transfer_flow(edges, cex, dates, lt['percentile'], lt['lookback_days'],
                                lt['minimum_history_days'], lt['minimum_edges_in_history'])
    table = pd.concat([flow, whale, large, vol], axis=1)
    norm = cfg['normalisation']
    table['cex_netflow_scaled'], table['cex_netflow_z'] = normalise_flow(
        table.cex_netflow_usdt, table.transfer_volume_usdt, norm)
    table['whaleflow_scaled'], table['whaleflow_z'] = normalise_flow(
        table.whaleflow_usdt, table.transfer_volume_usdt, norm)
    table['large_cex_netflow_scaled'], _ = normalise_flow(
        table.large_cex_netflow_usdt, table.transfer_volume_usdt, norm)
    table['log_transfer_volume_usdt'] = np.log(table.transfer_volume_usdt.where(table.transfer_volume_usdt > 0))
    if cex_by_day is not None:
        pit = pit_cex_netflow(edges, cex_by_day, dates)
        table = pd.concat([table, pit], axis=1)
        table['pit_cex_netflow_scaled'], table['pit_cex_netflow_z'] = normalise_flow(
            table.pit_cex_netflow_usdt, table.transfer_volume_usdt, norm)
        table['whaleflow_pit_scaled'], table['whaleflow_pit_z'] = normalise_flow(
            table.whaleflow_pit_usdt, table.transfer_volume_usdt, norm)
        table['pit_large_cex_netflow_usdt'] = pit_large_flow(
            edges, table.large_transfer_threshold_usdt.to_dict(), cex_by_day, dates)
        table['pit_large_cex_netflow_scaled'], _ = normalise_flow(
            table.pit_large_cex_netflow_usdt, table.transfer_volume_usdt, norm)
    table = pd.concat([table, market_controls(inputs['daily'], dates), chain_controls(inputs['eth_stats'], dates),
                       har_terms(table.log_rv, table.rv, cfg['volatility']['har_week_days'],
                                 cfg['volatility']['har_month_days'])], axis=1)
    table['day_of_week'] = pd.to_datetime(table.index).dayofweek
    table['available_at'] = (pd.to_datetime(table.index, utc=True) + pd.Timedelta(days=1)).astype(str)
    targets = forward_targets(table.rv, cfg['horizons'], cfg['target']['horizon_definition'])
    return pd.concat([table, targets], axis=1)


def non_target_columns(table):
    return [c for c in table.columns if not c.startswith('target_')]


def feature_columns(table):
    """Union of the explicit predictor sets that exist in the table (no targets, no bookkeeping)."""
    wanted = {c for cols in predictor_sets().values() for c in cols}
    return [c for c in table.columns if c in wanted]


# ----------------------------------------------------------------------------- derived reporting tables

def coverage_tables(table, n_retrospective_cex=None):
    """Daily and monthly/overall coverage of the PIT CEX set (observed share, not CEX recall)."""
    t = table
    vol = t.transfer_volume_usdt
    incident = t.pit_cex_external_in_usdt + t.pit_cex_external_out_usdt + t.pit_cex_internal_usdt
    endpoint = t.pit_cex_external_in_usdt + t.pit_cex_external_out_usdt + 2 * t.pit_cex_internal_usdt
    daily = pd.DataFrame({
        'n_retrospective_cex_set': n_retrospective_cex, 'n_pit_cex_available': t.n_pit_cex_endpoints,
        'n_pit_cex_active': t.n_pit_cex_active, 'transfer_volume_usdt': vol,
        'pit_incident_usdt': incident, 'pit_endpoint_usdt': endpoint,
        'pit_incident_share': incident / vol.where(vol > 0),
        'pit_endpoint_volume_share': endpoint / (2 * vol.where(vol > 0)),
        'flow_available': t.pit_cex_netflow_usdt.notna()})
    daily.index.name = 'date'
    ok = daily[daily.flow_available].copy()
    ok['period'] = pd.to_datetime(ok.index).strftime('%Y-%m')

    def summarize(g, label):
        v = g.transfer_volume_usdt.sum()
        return dict(period=label, n_days_available=int(len(g)), transfer_volume_usdt=float(v),
                    pit_incident_usdt=float(g.pit_incident_usdt.sum()),
                    pit_endpoint_volume_share=float(g.pit_endpoint_usdt.sum() / (2 * v)) if v > 0 else np.nan,
                    pit_incident_share=float(g.pit_incident_usdt.sum() / v) if v > 0 else np.nan,
                    mean_n_pit_cex_available=float(g.n_pit_cex_available.mean()),
                    mean_n_pit_cex_active=float(g.n_pit_cex_active.mean()))
    rows = [summarize(g, p) for p, g in ok.groupby('period', sort=True)]
    rows.append(summarize(ok, 'ALL'))
    return daily.reset_index(), pd.DataFrame(rows)


def overlap_table(table):
    cols = ['n_cohort_members', 'has_cohort', 'n_cohort_cex_retro_overlap', 'cohort_cex_pit_overlap',
            'n_cohort_members_active', 'n_cohort_members_active_pit', 'overlap_edge_retro_usdt',
            'overlap_edge_pit_usdt', 'n_pit_cex_endpoints']
    out = table[cols].copy()
    out['pit_overlap_share_of_members'] = out.cohort_cex_pit_overlap / out.n_cohort_members.where(out.n_cohort_members > 0)
    return out.reset_index()


def flow_z_status(raw_flow, z_col, lookback=90, min_history=30, base_condition=None):
    """Phân loại trạng thái z-score theo đúng logic warm-up:
    1. Đếm số raw flow hợp lệ trong cửa sổ quá khứ [D-L, D).
    2. Nếu chưa đủ 30 ngày lịch sử -> insufficient_flow_history.
    3. Nếu đủ 30 ngày nhưng độ lệch chuẩn bằng 0 -> zero_variance.
    4. Nếu tính được z-score hợp lệ -> ok.
    """
    valid_past_count = raw_flow.notna().astype(int).shift(1).rolling(lookback, min_periods=0).sum()
    past_std = raw_flow.shift(1).rolling(lookback, min_periods=min_history).std(ddof=1)

    status = pd.Series('missing_input', index=raw_flow.index)
    if base_condition is not None:
        status[~base_condition] = 'no_cohort'

    has_flow = raw_flow.notna() if base_condition is None else (raw_flow.notna() & base_condition)
    status[has_flow & (valid_past_count < min_history)] = 'insufficient_flow_history'
    status[has_flow & (valid_past_count >= min_history) & (past_std == 0)] = 'zero_variance'
    status[z_col.notna()] = 'ok'
    return status


def eligibility_table(table, cfg):
    """Why each day is (not) usable: warm-up vs missing vs genuinely observed zero flow."""
    t = table
    norm = cfg['normalisation']
    lookback = norm['zscore_lookback_days']
    min_hist = norm['minimum_history_days']

    out = pd.DataFrame(index=t.index)
    out['has_cohort'] = t.has_cohort
    out['n_pit_cex_endpoints'] = t.n_pit_cex_endpoints
    out['pit_cex_flow_status'] = np.where(t.pit_cex_netflow_usdt.isna(), 'unavailable_no_labels',
                                          np.where(t.pit_cex_external_in_usdt.add(t.pit_cex_external_out_usdt)
                                                   .add(t.pit_cex_internal_usdt).eq(0), 'observed_zero', 'observed'))
    out['whaleflow_pit_status'] = np.where(~t.has_cohort, 'no_cohort',
                                           np.where(t.n_pit_cex_endpoints.eq(0), 'no_pit_labels',
                                                    np.where(t.whale_to_cex_pit_usdt.add(t.cex_to_whale_pit_usdt).eq(0),
                                                             'observed_zero', 'observed')))
    out['pit_cex_z_status'] = flow_z_status(t.pit_cex_netflow_usdt, t.pit_cex_netflow_z, lookback, min_hist)
    out['whaleflow_pit_z_status'] = flow_z_status(t.whaleflow_pit_usdt, t.whaleflow_pit_z, lookback, min_hist, base_condition=t.has_cohort)
    out['rv_available'] = t.rv.notna()
    for branch, sets in [('retro_cex', RETRO_CEX_PREDICTORS), ('retro_whale', RETRO_WHALE_PREDICTORS),
                         ('pit_cex', PIT_CEX_PREDICTORS), ('pit_whale', PIT_WHALE_PREDICTORS)]:
        ready = t[sets + CONTROL_COLUMNS].notna().all(axis=1)
        out[f'predictors_ready_{branch}'] = ready
        for h in cfg['horizons']:
            out[f'eligible_{branch}_h{h}'] = ready & t[f'target_log_rv_h{h}'].notna()
    out.index.name = 'date'
    return out.reset_index()


# ----------------------------------------------------------------------------- PIT checks (truncation/mutation)

def truncate_history(history, cut):
    """Registry as it would be known when day `cut` starts: later claims removed, later end dates unknown."""
    last = pd.Timestamp(cut, tz='UTC')
    h = history.copy()
    avail = pd.to_datetime(h.public_available_at, utc=True)
    start = pd.to_datetime(h.effective_from, utc=True)
    h = h.loc[avail.lt(last) & start.lt(last)].copy()
    end = pd.to_datetime(h.effective_to, utc=True)
    h.loc[end.gt(last).to_numpy(), 'effective_to'] = pd.NaT
    return h


def truncate_inputs(inputs, cut):
    """Inputs as they would have existed at the end of day `cut` (inclusive); labels truncated too."""
    end = pd.Timestamp(cut, tz='UTC') + pd.Timedelta(days=1)
    cohort = normalise_cohort(inputs['cohort'])
    result = dict(
        edges=inputs['edges'][inputs['edges'].time_window <= cut],
        cohort=cohort[cohort.date <= cut],
        cex=inputs['cex'],
        daily=inputs['daily'][pd.to_datetime(inputs['daily'].datetime_utc, utc=True) < end],
        eth_stats=inputs['eth_stats'][pd.to_datetime(inputs['eth_stats'].tx_date) <= pd.Timestamp(cut)])
    if 'minute' in inputs:
        result['minute'] = inputs['minute'][pd.to_datetime(inputs['minute'].datetime_utc, utc=True) < end]
    if 'hourly' in inputs:
        result['hourly'] = inputs['hourly'][pd.to_datetime(inputs['hourly'].datetime_utc, utc=True) < end]
    if 'cex_history' in inputs:
        result['cex_history'] = truncate_history(inputs['cex_history'], cut)
    if 'labeler' in inputs:
        result['labeler'] = inputs['labeler']
    return result


def _compare(full, part, upto, cols):
    a, b = full.loc[upto, cols], part.loc[upto, cols]
    num = a.select_dtypes('number').columns
    diff = (a[num] - b[num]).abs()
    scale = a[num].abs().clip(lower=1.0)
    bad = ((diff / scale) > 1e-9) | (a[num].isna() != b[num].isna())
    other = [c for c in cols if c not in num]
    bad_other = (a[other] != b[other]).any() if other else pd.Series(dtype=bool)
    return sorted(set(bad.columns[bad.any()]) | set(bad_other.index[bad_other]))


def _future_label_rows(history, edges, cut, n=20):
    """Synthetic approved CEX claims that become public exactly at/after the cutoff of day `cut`."""
    known = set(history.address)
    volume = pd.concat([edges.groupby('from_address').total_value.sum(),
                        edges.groupby('to_address').total_value.sum()]).groupby(level=0).sum()
    picks = [a for a in volume.sort_values(ascending=False).index if a not in known][:n]
    if not picks or history.empty:
        return history.iloc[:0]
    last = pd.Timestamp(cut, tz='UTC')
    rows = []
    for i, address in enumerate(picks):
        r = history.iloc[[0]].copy()
        when = last if i % 2 == 0 else last + pd.Timedelta(days=30)
        r['address'] = address
        r['claim_id'] = f'synthetic_future_{i}'
        r['public_available_at'] = when
        r['effective_from'] = when
        r['effective_to'] = pd.NaT
        rows.append(r)
    return pd.concat(rows, ignore_index=True)


def pit_check(inputs, cfg, dates, cuts):
    """Recompute with future data AND future-only labels removed/added; features for days <= cut must not change."""
    full = build_features(inputs, cfg, dates)
    cols = [c for c in non_target_columns(full) if c != 'available_at']
    rows = []
    for cut in cuts:
        upto = [d for d in dates if d <= cut]
        part = build_features(truncate_inputs(inputs, cut), cfg, upto)
        failed = _compare(full, part, upto, cols)
        rows.append(dict(check='pit_truncation', cut_date=cut, status='PASS' if not failed else 'FAIL',
                         detail=','.join(failed)))
        if inputs.get('cex_history') is not None and len(inputs['cex_history']):
            history = inputs['cex_history']
            extra = _future_label_rows(history, inputs['edges'], cut)
            mutated = dict(inputs, cex_history=pd.concat([history, extra], ignore_index=True))
            base = build_features(dict(inputs), cfg, upto)
            alt = build_features(mutated, cfg, upto)
            failed = _compare(base, alt, upto, cols)
            rows.append(dict(check='pit_future_label_mutation', cut_date=cut,
                             status='PASS' if not failed else 'FAIL',
                             detail=f'n_future_labels={len(extra)};' + ','.join(failed)))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- validation

def label_boundary_checks(history, labeler=None):
    """Labels whose availability / start / end sit exactly on the cutoff D (strict inequality, 1 µs resolution)."""
    if labeler is None:
        from src.cex_label_history import available_cex_labels as labeler
    if history.empty:
        return [('label_boundary_checks', False, 'empty history')]
    day = pd.Timestamp('2025-06-15', tz='UTC')
    eps = pd.Timedelta(microseconds=1)

    def included(avail, start, end):
        r = history.iloc[[0]].copy()
        r['address'] = '0x' + 'ab' * 20
        r['public_available_at'], r['effective_from'], r['effective_to'] = avail, start, end
        return len(labeler(r, day)) == 1
    far = day - pd.Timedelta(days=100)
    cases = [
        ('available_at == D excluded', not included(day, far, pd.NaT)),
        ('available_at == D-1us included', included(day - eps, far, pd.NaT)),
        ('effective_from == D excluded', not included(far, day, pd.NaT)),
        ('effective_from == D-1us included', included(far, day - eps, pd.NaT)),
        ('effective_to == D excluded', not included(far, far, day)),
        ('effective_to == D+1us included', included(far, far, day + eps)),
        ('effective_to null included', included(far, far, pd.NaT)),
    ]
    return [(f'label_boundary: {name}', ok, '') for name, ok in cases]


def independent_asof_check(history, cex_by_day, dates):
    """Recompute every C_D with a separate numpy implementation of the same published rule."""
    if history.empty:
        return all(not v for v in cex_by_day.values()), 0
    avail = pd.to_datetime(history.public_available_at, utc=True).to_numpy('datetime64[ns]')
    start = pd.to_datetime(history.effective_from, utc=True).to_numpy('datetime64[ns]')
    end = pd.to_datetime(history.effective_to, utc=True).to_numpy('datetime64[ns]')
    ok_row = (history.review_status.eq('approved') & history.human_verified.eq(True)
              & history.entity_type.eq('CEX') & history.chain.eq('ethereum')).to_numpy()
    address = history.address.to_numpy()
    mismatches = 0
    for day in dates:
        t = np.datetime64(pd.Timestamp(day, tz='UTC').tz_convert(None), 'ns')
        keep = ok_row & (avail < t) & (start < t) & (np.isnat(end) | (end > t))
        if frozenset(address[keep]) != cex_by_day[day]:
            mismatches += 1
    return mismatches == 0, mismatches


def known_example_checks():
    """Hand-computed flows on a tiny graph: direction, internal/external split, conservation, NaN vs 0."""
    day, empty_day, no_label_day = '2025-01-02', '2025-01-03', '2025-01-04'
    dates = [day, empty_day, no_label_day]
    edges = pd.DataFrame([
        ('A', 'X', 100.0), ('X', 'B', 40.0), ('X', 'Y', 7.0), ('W1', 'X', 30.0), ('Y', 'W1', 10.0), ('Z', 'W1', 5.0),
    ], columns=['from_address', 'to_address', 'total_value'])
    edges['time_window'] = day
    c = frozenset({'X', 'Y', 'Z'})
    cex_by_day = {day: c, empty_day: c, no_label_day: frozenset()}
    flow = pit_cex_netflow(edges, cex_by_day, dates)
    cohort = pd.DataFrame({'date': [day, day, empty_day, no_label_day], 'address': ['W1', 'Z', 'W1', 'W1']})
    whale = whale_flow(edges, cohort, dates, cex_by_day=cex_by_day)
    row, w = flow.loc[day], whale.loc[day]
    rev = edges.rename(columns={'from_address': 'to_address', 'to_address': 'from_address'})
    flow_rev = pit_cex_netflow(rev, cex_by_day, dates).loc[day]
    close = lambda a, b: bool(np.isclose(a, b))
    return [
        ('example_inflow', close(row.pit_cex_external_in_usdt, 130.0), ''),
        ('example_outflow', close(row.pit_cex_external_out_usdt, 55.0), ''),
        ('example_internal', close(row.pit_cex_internal_usdt, 7.0), ''),
        ('example_netflow', close(row.pit_cex_netflow_usdt, 75.0), ''),
        ('example_direction_reversal', close(flow_rev.pit_cex_netflow_usdt, -75.0), ''),
        ('example_conservation', close(row.pit_cex_external_in_usdt + row.pit_cex_external_out_usdt
                                       + row.pit_cex_internal_usdt, 192.0), ''),
        ('example_labels_no_edges_is_zero', close(flow.loc[empty_day, 'pit_cex_netflow_usdt'], 0.0), ''),
        ('example_no_labels_is_nan', bool(np.isnan(flow.loc[no_label_day, 'pit_cex_netflow_usdt'])), ''),
        ('example_whale_to_cex', close(w.whale_to_cex_pit_usdt, 30.0), ''),
        ('example_cex_to_whale_includes_overlap_node_as_cex', close(w.cex_to_whale_pit_usdt, 15.0), ''),
        ('example_whaleflow', close(w.whaleflow_pit_usdt, 15.0), ''),
        ('example_overlap_count_and_volume', int(w.cohort_cex_pit_overlap) == 1 and close(w.overlap_edge_pit_usdt, 5.0), ''),
        ('example_cohort_no_edges_is_zero', close(whale.loc[empty_day, 'whaleflow_pit_usdt'], 0.0), ''),
        ('example_cohort_no_labels_is_nan', bool(np.isnan(whale.loc[no_label_day, 'whaleflow_pit_usdt'])), ''),
    ]


def _expected_target(rv, h, definition):
    values, n = rv.to_numpy(), len(rv)
    out = np.full(n, np.nan)
    for i in range(n):
        if definition == 'single_day':
            v = values[i + h] if i + h < n else np.nan
        else:
            w = values[i + 1:i + h + 1]
            v = w.sum() if len(w) == h and np.isfinite(w).all() else np.nan
        out[i] = np.log(v) if np.isfinite(v) and v > 0 else np.nan
    return out


def validate(table, cfg, dates, t12_cex=None, expected_days=None):
    rows = []

    def add(check, ok, detail=''):
        rows.append(dict(check=check, cut_date='', status='PASS' if ok else 'FAIL', detail=str(detail)))

    def same(a, b):
        return bool(np.allclose(a, b, equal_nan=True))

    add('calendar_complete_unique', list(table.index) == list(dates) and table.index.is_unique, len(table))
    if expected_days is not None:
        add('calendar_expected_days', len(table) == expected_days, f'{len(table)} vs {expected_days}')
    flows = table[RETRO_FLOW_COLUMNS + ['transfer_volume_usdt']]
    add('flows_finite_nonnegative_except_net', bool(np.isfinite(flows).all().all()) and bool(
        (table[['cex_external_in_usdt', 'cex_external_out_usdt', 'cex_internal_usdt', 'transfer_volume_usdt']] >= 0).all().all()))
    add('netflow_identity', same(table.cex_netflow_usdt, table.cex_external_in_usdt - table.cex_external_out_usdt))
    add('cex_flow_not_above_volume', bool((table.cex_external_in_usdt + table.cex_external_out_usdt
                                           + table.cex_internal_usdt <= table.transfer_volume_usdt * (1 + 1e-9)).all()))
    if 'pit_cex_netflow_usdt' in table:
        no_label = table.n_pit_cex_endpoints.eq(0)
        add('pit_netflow_identity', same(table.pit_cex_netflow_usdt,
                                         table.pit_cex_external_in_usdt - table.pit_cex_external_out_usdt))
        add('pit_flow_nan_iff_no_labels', bool((table.pit_cex_netflow_usdt.isna() == no_label).all()),
            f'days_without_labels={int(no_label.sum())}')
        total = table.pit_cex_external_in_usdt + table.pit_cex_external_out_usdt + table.pit_cex_internal_usdt
        add('pit_flow_not_above_volume', bool((total.dropna() <= table.transfer_volume_usdt[total.notna()] * (1 + 1e-9)).all()))
        scaled, z = normalise_flow(table.pit_cex_netflow_usdt, table.transfer_volume_usdt, cfg['normalisation'])
        add('pit_scaled_z_use_pit_flow', same(scaled, table.pit_cex_netflow_scaled) and same(z, table.pit_cex_netflow_z))
        scaled, z = normalise_flow(table.whaleflow_pit_usdt, table.transfer_volume_usdt, cfg['normalisation'])
        add('whaleflow_pit_scaled_z_use_pit_flow', same(scaled, table.whaleflow_pit_scaled) and same(z, table.whaleflow_pit_z))
        add('whaleflow_pit_identity', same(table.whaleflow_pit_usdt, table.whale_to_cex_pit_usdt - table.cex_to_whale_pit_usdt))
        expect_nan = ~(table.has_cohort.astype(bool) & table.n_pit_cex_endpoints.gt(0))
        add('whaleflow_pit_nan_iff_no_cohort_or_no_labels', bool((table.whaleflow_pit_usdt.isna() == expect_nan).all()),
            f'nan_days={int(expect_nan.sum())}')
        add('cohort_overlap_nonnegative', bool((table.cohort_cex_pit_overlap >= 0).all()
                                                 and (table.cohort_cex_pit_overlap <= table.n_cohort_members).all()),
            f"member_days={int(table.cohort_cex_pit_overlap.sum())}")
    add('whaleflow_identity', same(table.whaleflow_usdt, table.whale_to_cex_usdt - table.cex_to_whale_usdt))
    add('whaleflow_nan_without_cohort', bool(table.loc[~table.has_cohort.astype(bool), 'whaleflow_usdt'].isna().all()),
        f"days_without_cohort={int((~table.has_cohort.astype(bool)).sum())}")
    rv_ok = table.rv.dropna()
    min_expected_rv_days = int(0.9 * len(table))
    add('rv_sufficient_coverage', len(rv_ok) >= min_expected_rv_days,
        f"valid_days={len(rv_ok)}/{len(table)} (min required: {min_expected_rv_days})")
    add('rv_nonnegative', bool(len(rv_ok) > 0 and (rv_ok >= 0).all()), f"nan_days={int(table.rv.isna().sum())}")
    add('rv_sqrt_relation', bool(len(rv_ok) > 0) and same(table.realized_vol ** 2, table.rv))
    bars_col = 'n_minute_returns' if 'n_minute_returns' in table.columns else 'n_hourly_returns'
    add('rv_full_day_bars', bool(len(rv_ok) > 0 and table.loc[table.rv.notna(), bars_col].eq(cfg['volatility']['bars_per_day']).all()))
    definition = cfg['target']['horizon_definition']
    for h in cfg['horizons']:
        t = table[f'target_log_rv_h{h}']
        expected = _expected_target(table.rv, h, definition)
        valid_targets = int(t.iloc[:-h].notna().sum())
        add(f'target_h{h}_sufficient_coverage', valid_targets >= int(0.9 * (len(table) - h)),
            f"valid_targets={valid_targets}/{len(table) - h}")
        add(f'target_h{h}_matches_definition_{definition}', bool(t.iloc[-h:].isna().all()) and same(t.to_numpy(), expected))
    add('available_after_day_end', bool((pd.to_datetime(table.available_at, utc=True)
                                          > pd.to_datetime(table.index, utc=True)).all()))
    sets = predictor_sets()
    union = {c for cols in sets.values() for c in cols}
    add('predictor_sets_clean', bool(not any(c.startswith('target_') or c in BOOKKEEPING_COLUMNS for c in union)
                                     and union <= set(table.columns)),
        ','.join(sorted(union - set(table.columns))))
    add('pit_and_retro_predictors_disjoint', not (set(PIT_CEX_PREDICTORS + PIT_WHALE_PREDICTORS)
                                                   & set(RETRO_CEX_PREDICTORS + RETRO_WHALE_PREDICTORS)))
    if t12_cex is not None:
        t = t12_cex.set_index('date').reindex(dates)
        diff = float((t.cex_netflow_usdt - table.cex_netflow_usdt).abs().max())
        add('retrospective_matches_t12_cex_netflow', diff <= 1e-6 * max(1.0, float(table.cex_netflow_usdt.abs().max())),
            f'max_abs_diff={diff}')
    return pd.DataFrame(rows)