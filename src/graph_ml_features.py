"""T19: node-window feature matrix (T09, T10, T11), T07 labels and a time-ordered split.

Conventions
-----------
* One row per (window_type, time_window, address): a node that has at least one thresholded edge
  in that window. The row's features come only from that window's graph, plus past windows
  (lag / history columns). They are available at `available_at` = end of the window (UTC).
* Features are never computed from T07 labels, T12 cohorts or T14 columns. Labels enter only after
  the feature table is final, in `label_*` columns, and never change a feature value.
* Window cross-section ranks use rows of the same window only. Lag features use earlier windows only.
  No scaler or encoder is fitted here: T20 fits those on the train split.
* The T07 labels are retrospective (collected 2026-10-20). A node keeps its label in every window,
  so this is node classification on contemporaneous features, not a point-in-time label forecast.
* Pure functions only; file I/O lives in T19_Graph_ML_Features.py.
"""
import hashlib
from datetime import date

import numpy as np
import pandas as pd

KEY = ['window_type', 'time_window', 'address']
T09_RAW = ['in_degree', 'out_degree', 'degree', 'in_strength_usdt', 'out_strength_usdt',
           'weighted_degree_usdt', 'in_tx_count', 'out_tx_count', 'weighted_degree_tx',
           'net_inflow_usdt', 'pagerank']
T10_RAW = ['betweenness', 'eigenvector', 'clustering', 'clustering_weighted']
T11_RAW = ['community_size', 'community_volume_usdt', 'is_giant_community']
T11_DUPLICATES = {'node_volume_usdt': 'weighted_degree_usdt', 'node_degree': 'degree'}
WINDOW_META = ['days_in_window', 'is_partial_week', 'eligible_for_regression']
LOG1P = ['in_strength_usdt', 'out_strength_usdt', 'weighted_degree_usdt', 'weighted_degree_tx',
         'community_volume_usdt', 'community_size', 'degree', 'mean_edge_value_usdt']
SPLITS = ['train', 'validation', 'test']
# Columns that may never be predictors: ids, calendar, labels, split, and every T07 column.
T07_COLUMNS = ['entity_name', 'entity_type', 'class', 'source', 'source_url', 'evidence', 'confidence',
               'date_downloaded', 'incoming_usdt', 'outgoing_usdt', 'gross_flow_usdt',
               'incoming_transfers', 'outgoing_transfers', 'total_transfers', 'public_entity', 'public_label',
               'public_category', 'is_contract', 'first_contract_timestamp', 'is_entity_attributed',
               'is_zero_address', 'label_conflict_review']
NON_PREDICTORS = set(KEY) | {'widx', 'window_start', 'window_end', 'available_at', 'community_id', 'split',
                             'address_seen_in_train', 'eligible_for_regression', 'is_partial_week',
                             'days_in_window'} | set(T07_COLUMNS)


# ----------------------------------------------------------------------------- windows
def window_bounds(windows, window_type):
    """UTC [start, end) per window and its chronological index.

    Weekly windows are ISO weeks (`YYYY-Www`, Monday start); the first week is partial (starts at the
    study start) and the last week ends after `days_in_window` days. Availability = window end.
    """
    w = windows[['time_window', 'days_in_window', 'is_partial_week', 'eligible_for_regression']].drop_duplicates('time_window').copy()
    days = pd.to_timedelta(w.days_in_window.astype(int), unit='D')
    if window_type == 'daily':
        start = pd.to_datetime(w.time_window, utc=True).dt.as_unit('ns')
        end = start + pd.Timedelta(days=1)
    elif window_type == 'weekly':
        monday = pd.Series([pd.Timestamp(date.fromisocalendar(int(s[:4]), int(s[6:]), 1), tz='UTC') for s in w.time_window],
                           index=w.index).dt.as_unit('ns')
        first = monday.eq(monday.min())
        end = (monday + days).where(~first, monday + pd.Timedelta(days=7))
        start = end - days
    else:
        raise ValueError(f'unknown window_type {window_type}')
    w['window_start'], w['window_end'] = start, end
    w = w.sort_values('window_start', kind='mergesort').reset_index(drop=True)
    w['widx'] = np.arange(len(w))
    return w


def split_windows(bounds, fractions, gap):
    """Chronological train/validation/test over eligible windows with `gap` windows left out between them."""
    if abs(sum(fractions.values()) - 1) > 1e-9:
        raise ValueError('split fractions must sum to 1')
    eligible = bounds[bounds.eligible_for_regression.astype(bool)].sort_values('widx')
    usable = len(eligible) - 2 * gap
    n_tr = int(round(usable * fractions['train']))
    n_va = int(round(usable * fractions['validation']))
    n_te = usable - n_tr - n_va
    if min(n_tr, n_va, n_te) < 1:
        raise ValueError(f'too few windows for the split: {len(eligible)} eligible, gap={gap}')
    labels = ['train'] * n_tr + ['gap'] * gap + ['validation'] * n_va + ['gap'] * gap + ['test'] * n_te
    out = bounds.copy()
    out['split'] = 'excluded_partial_window'
    out.loc[eligible.index, 'split'] = labels
    return out


# ----------------------------------------------------------------------------- source tables
def merge_nodes(t09, t10, t11):
    """Inner join of the three node tables on (window_type, time_window, address) with row accounting."""
    stats = dict(n_t09=len(t09), n_t10=len(t10), n_t11=len(t11))
    for name, frame in (('t09', t09), ('t10', t10), ('t11', t11)):
        if frame.duplicated(KEY).any():
            raise ValueError(f'{name} has duplicate (window_type, time_window, address) keys')
    a = t09[KEY + T09_RAW + WINDOW_META]
    b = t10[KEY + T10_RAW]
    c = t11[KEY + T11_RAW + list(T11_DUPLICATES)]
    merged = a.merge(b, on=KEY, how='inner', validate='one_to_one').merge(c, on=KEY, how='inner', validate='one_to_one')
    stats['n_merged'] = len(merged)
    return merged, stats


# ----------------------------------------------------------------------------- features
def _ratio(num, den):
    return num / den.where(den > 0)


def build_features(nodes, snapshot, bounds, cfg):
    """Node-window features. No label, cohort or T14 input: the signature itself guarantees it."""
    opts = cfg['features']
    if int(opts.get('lag_windows', 1)) != 1:
        raise ValueError('only lag_windows=1 is implemented')
    df = nodes.merge(bounds[['time_window', 'widx', 'window_start', 'window_end']], on='time_window', how='left',
                     validate='many_to_one')
    if df.widx.isna().any():
        raise ValueError('node rows without a calendar window')
    df = df.merge(snapshot[['time_window', 'total_volume_usdt']], on='time_window', how='left', validate='many_to_one')
    if df.total_volume_usdt.isna().any():
        raise ValueError('node rows without a snapshot total volume')
    df = df.sort_values(['address', 'widx'], kind='mergesort').reset_index(drop=True)

    f = {c: df[c].astype(float) for c in T09_RAW + T10_RAW + ['community_size', 'community_volume_usdt']}
    f['is_giant_community'] = df.is_giant_community.astype(float)
    f['in_share'] = _ratio(f['in_strength_usdt'], f['weighted_degree_usdt'])
    f['mean_edge_value_usdt'] = _ratio(f['weighted_degree_usdt'], f['degree'])
    f['mean_tx_value_usdt'] = _ratio(f['weighted_degree_usdt'], f['weighted_degree_tx'])
    total2 = 2.0 * df.total_volume_usdt
    f['volume_share_of_window'] = _ratio(f['weighted_degree_usdt'], total2)
    f['community_volume_share'] = _ratio(f['community_volume_usdt'], total2)
    for c in LOG1P:
        f[f'log1p_{c}'] = np.log1p(f[c])
    f['slog1p_net_inflow_usdt'] = np.sign(f['net_inflow_usdt']) * np.log1p(f['net_inflow_usdt'].abs())
    tmp = pd.DataFrame(f)
    tmp['time_window'] = df.time_window
    for c in opts['rank_columns']:
        f[f'rank_{c}_pct'] = tmp.groupby('time_window')[c].rank(pct=True, method='average')
    # history: earlier windows only; a node absent in the previous window had no edge above the threshold
    g = df.groupby('address')
    prev_widx = g.widx.shift(1)
    seen_prev = prev_widx.eq(df.widx - 1)
    f['windows_seen_before'] = g.cumcount().astype(float)
    f['seen_prev_window'] = seen_prev.astype(float)
    f['lag1_degree'] = f['degree'].groupby(df.address).shift(1).where(seen_prev, 0.0)
    f['lag1_weighted_degree_usdt'] = f['weighted_degree_usdt'].groupby(df.address).shift(1).where(seen_prev, 0.0)
    for c in opts.get('window_context', []):
        f[c] = df[c].astype(float)

    out = df[KEY + ['widx', 'window_start', 'window_end'] + WINDOW_META].copy()
    out['available_at'] = out.window_end
    feats = pd.DataFrame(f)
    out = pd.concat([out, feats], axis=1)
    out = out.sort_values(['widx', 'address'], kind='mergesort').reset_index(drop=True)
    return out, list(feats.columns)


def feature_dictionary(columns):
    """Name, source table and meaning of every predictor column."""
    desc = {}
    for c in T09_RAW:
        desc[c] = ('T09', 'node metric of the window graph')
    for c in T10_RAW:
        desc[c] = ('T10', 'node metric of the window graph (betweenness may be pivot-sampled)')
    desc['community_size'] = ('T11', 'size of the node community in this window; community_id is not a feature')
    desc['community_volume_usdt'] = ('T11', 'endpoint volume of the node community in this window')
    desc['is_giant_community'] = ('T11', '1 if the node is in the giant community of this window')
    rows = []
    for c in columns:
        if c in desc:
            src, text = desc[c]
        elif c.startswith('log1p_') or c.startswith('slog1p_'):
            src, text = 'derived', 'log1p transform; fitted scaling happens in T20 on train only'
        elif c.startswith('rank_'):
            src, text = 'derived', 'percentile rank among nodes of the same window only'
        elif c in ('lag1_degree', 'lag1_weighted_degree_usdt', 'windows_seen_before', 'seen_prev_window'):
            src, text = 'derived_history', 'uses earlier windows only; absent previous window = 0 (no edge above threshold)'
        else:
            src, text = 'derived', 'ratio of same-window quantities'
        rows.append(dict(feature=c, source=src, description=text))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- labels
def attach_labels(features, labels, cfg):
    """Join T07 labels after the features are final. Returns the table and the chosen classes."""
    lab = cfg['label']
    if labels.address.duplicated().any():
        raise ValueError('T07 labels have duplicate addresses')
    cols = ['address', 'entity_type', 'confidence', 'label_conflict_review', 'is_zero_address', 'is_entity_attributed']
    l = labels[cols].rename(columns={'entity_type': 'label_entity_type', 'confidence': 'label_confidence'})
    df = features.merge(l, on='address', how='left', validate='many_to_one')
    status = pd.Series('labeled', index=df.index, dtype=object)
    excluded_type = df.label_entity_type.isin(lab['exclude_entity_types']) | ~df.is_entity_attributed.fillna(False).astype(bool)
    status[excluded_type] = 'unattributed_or_excluded_type'
    if lab.get('exclude_label_conflict', True):
        status[df.label_conflict_review.fillna(False).astype(bool)] = 'label_conflict'
    if lab.get('exclude_zero_address', True):
        status[df.is_zero_address.fillna(False).astype(bool)] = 'zero_address'
    status[df.label_entity_type.isna()] = 'no_t07_row'
    counts = df.loc[status.eq('labeled')].groupby('label_entity_type').address.nunique()
    keep = sorted(counts[counts >= lab['min_addresses_per_class']].index)
    rare = status.eq('labeled') & ~df.label_entity_type.isin(keep)
    status[rare] = 'rare_class'
    df['label_status'] = status
    df['label_class'] = df.label_entity_type.where(status.eq('labeled'))
    df = df.drop(columns=['label_conflict_review', 'is_zero_address', 'is_entity_attributed'])
    return df, keep


def attach_split(df, split_table):
    out = df.merge(split_table[['time_window', 'split']], on='time_window', how='left', validate='many_to_one')
    train_addresses = set(out.loc[out.split.eq('train'), 'address'])
    out['address_seen_in_train'] = out.address.isin(train_addresses)
    return out


def label_summary(df, cfg):
    """Rows and distinct addresses per split and class, with a coverage flag per class."""
    lab = df[df.label_status.eq('labeled') & df.split.isin(SPLITS)]
    long = lab.groupby(['split', 'label_class']).agg(n_rows=('address', 'size'), n_addresses=('address', 'nunique')).reset_index()
    minimum = cfg['label']['min_addresses_per_class_per_split']
    classes = sorted(lab.label_class.unique())
    full = pd.MultiIndex.from_product([SPLITS, classes], names=['split', 'label_class'])
    long = long.set_index(['split', 'label_class']).reindex(full, fill_value=0).reset_index()
    long['meets_min_addresses'] = long.n_addresses >= minimum
    seen = lab[lab.split.isin(['validation', 'test'])].groupby(['split', 'label_class']).address_seen_in_train.mean().rename('share_rows_address_seen_in_train')
    return long.merge(seen.reset_index(), on=['split', 'label_class'], how='left')


# ----------------------------------------------------------------------------- hashing / comparison
def frame_hash(df):
    h = hashlib.sha256()
    h.update('|'.join(f'{c}:{t}' for c, t in zip(df.columns, df.dtypes.astype(str))).encode())
    h.update(pd.util.hash_pandas_object(df.reset_index(drop=True), index=False).to_numpy().tobytes())
    return h.hexdigest()


def _compare(a, b, columns, tolerance):
    a = a.sort_values(KEY).reset_index(drop=True)
    b = b.sort_values(KEY).reset_index(drop=True)
    if len(a) != len(b) or not a[KEY].equals(b[KEY]):
        return ['<rows>']
    bad = []
    for c in columns:
        x, y = a[c].to_numpy(float), b[c].to_numpy(float)
        same = (np.isnan(x) & np.isnan(y)) | (np.abs(x - y) <= tolerance * np.maximum(1.0, np.abs(x)))
        if not same.all():
            bad.append(c)
    return bad


# ----------------------------------------------------------------------------- leakage tests
def _truncate(nodes, snapshot, bounds, cut_widx):
    keep = set(bounds.loc[bounds.widx <= cut_widx, 'time_window'])
    return nodes[nodes.time_window.isin(keep)], snapshot[snapshot.time_window.isin(keep)], bounds[bounds.widx <= cut_widx]


def _mutate_future(nodes, snapshot, bounds, cut_widx, factor=7.3):
    future = set(bounds.loc[bounds.widx > cut_widx, 'time_window'])
    n, s = nodes.copy(), snapshot.copy()
    rows = n.time_window.isin(future)
    for c in T09_RAW + T10_RAW + ['community_size', 'community_volume_usdt']:
        n[c] = np.where(rows, n[c].astype(float) * factor, n[c].astype(float))
    n['is_giant_community'] = np.where(rows, ~n['is_giant_community'].astype(bool), n['is_giant_community'].astype(bool))
    s.loc[s.time_window.isin(future), 'total_volume_usdt'] *= factor
    return n, s


def leakage_checks(nodes, snapshot, bounds, cfg, feature_columns):
    """Truncation (drop the future) and mutation (change the future) at several cutoffs."""
    full, _ = build_features(nodes, snapshot, bounds, cfg)
    eligible = sorted(bounds.loc[bounds.eligible_for_regression.astype(bool), 'widx'])
    tol = cfg['leakage_checks']['tolerance']
    rows = []
    for frac in cfg['leakage_checks']['cut_fractions']:
        cut = eligible[int(frac * (len(eligible) - 1))]
        past = full[full.widx <= cut]
        n, s, b = _truncate(nodes, snapshot, bounds, cut)
        part, _ = build_features(n, s, b, cfg)
        bad = _compare(past, part, feature_columns, tol)
        rows.append(dict(check='truncation_future_windows_removed', scope=f'cut_widx={cut}', status='PASS' if not bad else 'FAIL',
                         detail=','.join(bad)))
        n, s = _mutate_future(nodes, snapshot, bounds, cut)
        mutated, _ = build_features(n, s, bounds, cfg)
        bad = _compare(past, mutated[mutated.widx <= cut], feature_columns, tol)
        rows.append(dict(check='mutation_future_windows_changed', scope=f'cut_widx={cut}', status='PASS' if not bad else 'FAIL',
                         detail=','.join(bad)))
    return rows


# ----------------------------------------------------------------------------- validation
def _row(rows, name, ok, detail='', scope='features', level='FAIL'):
    rows.append(dict(check=name, scope=scope, status='PASS' if ok else level, detail=str(detail)))


def validate(window_type, table, feature_columns, merged, stats, bounds, snapshot, split_table, t11_snapshot, chosen_classes, cfg,
             summary):
    """Hard invariants of the final table (FAIL) plus coverage notes (WARN/INFO)."""
    rows = []
    add = lambda *a, **k: _row(rows, *a, scope=window_type, **k)
    add('source_row_counts_equal_and_nothing_lost', len({stats['n_t09'], stats['n_t10'], stats['n_t11'], stats['n_merged']}) == 1, stats)
    add('keys_unique', not table.duplicated(KEY).any())
    dup_ok = all(np.allclose(merged[a].astype(float), merged[b].astype(float), rtol=1e-6, atol=1e-6) for a, b in T11_DUPLICATES.items())
    add('t11_node_volume_and_degree_equal_t09', dup_ok)
    contiguous = bool((bounds.window_start.iloc[1:].to_numpy() == bounds.window_end.iloc[:-1].to_numpy()).all())
    add('calendar_contiguous_non_overlapping', contiguous, f'{len(bounds)} windows')
    add('node_windows_covered_by_snapshot', set(table.time_window) <= set(snapshot.time_window))
    sums = merged.groupby('time_window').pagerank.sum()
    add('pagerank_sums_to_one_per_window', bool(np.allclose(sums, 1.0, atol=1e-6)), f'max_abs_dev={float((sums - 1).abs().max()):.2e}')
    nonneg = ['in_degree', 'out_degree', 'degree', 'in_strength_usdt', 'out_strength_usdt', 'weighted_degree_usdt', 'in_tx_count',
              'out_tx_count', 'weighted_degree_tx', 'pagerank', 'betweenness', 'eigenvector', 'clustering', 'clustering_weighted']
    add('metrics_nonnegative', bool((table[nonneg].dropna() >= 0).all().all()))
    add('clustering_at_most_one', bool((table[['clustering', 'clustering_weighted']].dropna() <= 1 + 1e-9).all().all()))
    add('weighted_degree_equals_in_plus_out', bool(np.allclose(table.weighted_degree_usdt, table.in_strength_usdt + table.out_strength_usdt, rtol=1e-6)))
    diff = (table.net_inflow_usdt - (table.in_strength_usdt - table.out_strength_usdt)).abs()
    add('net_inflow_equals_in_minus_out', bool((diff <= 1e-6 * table.weighted_degree_usdt.clip(lower=1.0)).all()))
    add('in_share_within_0_1', bool(table.in_share.dropna().between(-1e-9, 1 + 1e-9).all()))
    check = table.loc[table.is_giant_community.eq(1.0)].groupby('time_window').community_volume_share.max()
    ref = t11_snapshot.set_index('time_window').giant_community_volume_ratio.reindex(check.index)
    add('community_volume_share_matches_t11_giant_ratio', bool(np.allclose(check, ref, rtol=1e-6, atol=1e-9)))
    values = table[feature_columns].to_numpy(float)
    add('features_have_no_infinity', bool(np.isfinite(values[~np.isnan(values)]).all()))
    nan_rate = table[feature_columns].isna().mean()
    add('feature_missing_rates_reported', True, nan_rate[nan_rate > 0].round(6).to_dict(), level='INFO')
    bad = sorted(set(feature_columns) & NON_PREDICTORS)
    add('feature_columns_exclude_ids_labels_split_and_t07', not bad, bad)
    add('available_at_equals_window_end', bool((table.available_at == table.window_end).all()) and bool((table.window_end > table.window_start).all()))
    # split
    sp = split_table
    ok_windows = sp[sp.split.isin(SPLITS)].groupby('split').widx.agg(['min', 'max'])
    ordered = bool(ok_windows.loc['train', 'max'] < ok_windows.loc['validation', 'min'] and ok_windows.loc['validation', 'max'] < ok_windows.loc['test', 'min'])
    gap = int(cfg['split']['gap_windows'][window_type])
    gaps = (ok_windows.loc['validation', 'min'] - ok_windows.loc['train', 'max'] - 1 >= gap) and (ok_windows.loc['test', 'min'] - ok_windows.loc['validation', 'max'] - 1 >= gap)
    add('split_windows_chronological_with_gap', ordered and bool(gaps), ok_windows.to_dict('index'))
    add('train_ends_before_validation_starts_and_validation_before_test',
        bool(sp[sp.split == 'train'].window_end.max() <= sp[sp.split == 'validation'].window_start.min()
             and sp[sp.split == 'validation'].window_end.max() <= sp[sp.split == 'test'].window_start.min()))
    add('partial_windows_excluded_from_split', bool(table.loc[~table.eligible_for_regression.astype(bool), 'split'].eq('excluded_partial_window').all()))
    add('every_row_has_split_state', bool(table.split.notna().all()))
    train_addr = set(table.loc[table.split == 'train', 'address'])
    non_train = table[table.split.isin(['validation', 'test'])]
    add('address_seen_in_train_matches_train_rows', bool(non_train.address.isin(train_addr).eq(non_train.address_seen_in_train).all()))
    # labels
    labeled = table[table.label_status.eq('labeled')]
    add('label_class_present_iff_labeled', bool(table.label_class.notna().eq(table.label_status.eq('labeled')).all()))
    add('one_label_per_address', not labeled.groupby('address').label_class.nunique().gt(1).any())
    add('labeled_classes_are_the_chosen_classes', set(labeled.label_class.unique()) <= set(chosen_classes), chosen_classes)
    add('no_excluded_type_in_labels', not set(labeled.label_entity_type) & set(cfg['label']['exclude_entity_types']))
    shares = table.label_status.value_counts(normalize=True).round(6).to_dict()
    add('label_status_share_of_rows', True, shares, level='INFO')
    lab_sum = summary
    low = lab_sum[~lab_sum.meets_min_addresses]
    add('every_class_has_enough_addresses_in_every_split', low.empty,
        low[['split', 'label_class', 'n_addresses']].to_dict('records'), level='WARN')
    return rows


def readiness(window_type, rows, repro_same, hash_checks_ok, class_coverage_ok, n_classes):
    """computation_validated never implies a PIT label forecast."""
    own = [r for r in rows if r['scope'] == window_type]
    hard_ok = all(r['status'] != 'FAIL' for r in own)
    validated = bool(hard_ok and repro_same and hash_checks_ok)
    return dict(
        computation_validated=validated,
        node_classification_ready=bool(validated and class_coverage_ok and n_classes >= 2),
        class_coverage_ok=bool(class_coverage_ok),
        n_classes=int(n_classes),
        pit_label_forecast=False,
        pit_label_forecast_note='T07 labels are retrospective (collected 2026-10-20): no historical availability date. '
                                'This table supports node classification on same-window features, not label forecasting.',
        split_note='Time-ordered split with a gap; same address may appear in several splits: report metrics on all test rows '
                   'and on rows with address_seen_in_train == False.',
    )
