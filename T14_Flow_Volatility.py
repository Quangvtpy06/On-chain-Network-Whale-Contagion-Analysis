"""T14: build NetFlow, WhaleFlow, realized volatility and controls X_t (daily, point-in-time).

Run from the project root after T05-T07, T08 and T12 have been accepted:

    python T14_Flow_Volatility.py

The table is computed twice (second run in .cache/), hashes are compared, a
truncation test removes future data and checks that no feature changes, and only
then is `ready_for_t15` written. `--skip-reproducibility` is for exploration and
never marks the output ready.
"""
import argparse
import json
import shutil
import uuid

import pandas as pd

from src import flow_volatility as fv
from src.graph_config import ROOT, project_path, read_config, relative_path
from src.node_centrality import sha256, verified_t08_inputs, write_json

SETTINGS = ROOT / 'config/t14.yaml'
FEATURES = 't14_features_daily.parquet'
PIT_CUTS = [0.25, 0.5, 0.75, 0.95]


def load_inputs(cfg, settings):
    paths = {k: project_path(v) for k, v in settings['inputs'].items()}
    labels = pd.read_parquet(paths['labels_parquet'])
    secondary = pd.read_parquet(paths['secondary_labels'])
    # Same overlay as T12 build_cex so both CEX tables reconcile; secondary labels can only
    # re-type addresses already present in T07 and never silently resolve a conflict.
    labels = labels.copy()
    for row in secondary.itertuples():
        present = labels.address.eq(row.address)
        if present.any() and labels.loc[present, 'is_entity_attributed'].any() \
                and not labels.loc[present, 'entity_type'].eq(row.entity_type).all():
            raise ValueError('Secondary label conflicts with attributed T07')
        for column in ['entity_name', 'entity_type', 'confidence', 'source_url']:
            labels.loc[present, column] = getattr(row, column)
    cohort = pd.read_parquet(paths['cohort_members'], columns=['date', 'address'])
    return dict(
        edges=pd.read_parquet(paths['daily_edges_parquet'],
                              columns=['time_window', 'from_address', 'to_address', 'total_value']),
        cohort=cohort, cex=fv.cex_set(labels),
        hourly=pd.read_parquet(paths['market_1h'], columns=['datetime_utc', 'close']),
        daily=pd.read_parquet(paths['market_1d']),
        eth_stats=pd.read_csv(paths['eth_stats_csv']),
    ), paths


def compute(folder, cfg, settings, dates, gate_open):
    inputs, paths = load_inputs(cfg, settings)
    table = fv.build_features(inputs, settings, dates)
    table['whaleflow_gate_open'] = bool(gate_open)
    table['cex_labels_pit'] = False  # T07 labels are retrospective; see T12 report.
    table['protocol_id'] = settings['protocol_id']
    folder.mkdir(parents=True, exist_ok=True)
    table.reset_index().to_parquet(folder / FEATURES, index=False)
    return inputs, table


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-reproducibility', action='store_true')
    args = parser.parse_args()

    cfg = read_config()
    settings = read_config(SETTINGS)
    folder = project_path(settings['output_dir'])
    provenance = verified_t08_inputs(cfg)
    dates = list(fv.day_index(cfg['project']['start_date'], cfg['project']['end_date']))
    if len(dates) != cfg['project']['total_days']:
        raise ValueError('Calendar length does not match config')

    gate = json.loads(project_path(settings['inputs']['t12_gate']).read_text(encoding='utf-8'))
    gate_open = bool(gate.get('ready_for_cohort_whaleflow', False))

    inputs, table = compute(folder, cfg, settings, dates, gate_open)
    hashes = {FEATURES: dict(run1=sha256(folder / FEATURES))}

    cuts = [dates[int(len(dates) * q)] for q in PIT_CUTS]
    pit = fv.pit_check(inputs, settings, dates, cuts)
    t12_cex = pd.read_parquet(project_path(settings['inputs']['t12_cex_netflow']))
    validation = pd.concat([fv.validate(table, settings, dates, t12_cex), pit], ignore_index=True)
    validation.to_parquet(folder / 't14_validation.parquet', index=False)

    same = None
    if not args.skip_reproducibility:
        cache = ROOT / '.cache'
        cache.mkdir(exist_ok=True)
        temporary = cache / f't14_{uuid.uuid4().hex}'
        try:
            compute(temporary, cfg, settings, dates, gate_open)
            hashes[FEATURES]['run2'] = sha256(temporary / FEATURES)
        finally:
            if temporary.exists():
                if not temporary.resolve().is_relative_to(cache.resolve()):
                    raise ValueError('Unsafe cleanup')
                shutil.rmtree(temporary)
        same = hashes[FEATURES]['run1'] == hashes[FEATURES]['run2']
    after = verified_t08_inputs(cfg)
    if after != provenance:
        raise ValueError('T08 inputs changed during T14')

    passed = bool(validation.status.eq('PASS').all())
    feature_cols = fv.feature_columns(table)
    summary = dict(
        protocol_id=settings['protocol_id'],
        settings_sha256=sha256(SETTINGS),
        code_sha256={relative_path(p): sha256(p) for p in [ROOT / 'src/flow_volatility.py', ROOT / 'T14_Flow_Volatility.py']},
        input_sha256={k: sha256(project_path(v)) for k, v in settings['inputs'].items()},
        upstream=provenance,
        days=len(dates), horizons=settings['horizons'],
        validation_passed=passed, reproducible=same,
        rows_with_all_controls=int(table[['ret_1d', 'log_volume_usdt', 'log_rv_month']].notna().all(axis=1).sum()),
        rows_with_cex_netflow_z=int(table.cex_netflow_z.notna().sum()),
        rows_with_whaleflow_z=int(table.whaleflow_z.notna().sum()),
        rows_with_large_transfer=int(table.large_transfer_count.notna().sum()),
        cohort_cex_addresses_removed_total=int(table.n_cohort_cex_removed.sum()),
        feature_columns=feature_cols,
        target_columns=[c for c in table.columns if c.startswith('target_')],
        ready_for_t15_cex_netflow=bool(passed and same),
        ready_for_t15_large_transfer=bool(passed and same),
        ready_for_t15_cohort_whaleflow=bool(passed and same and gate_open),
        t12_gate_ready_for_cohort_whaleflow=gate_open,
        caveats=[
            'CEX NetFlow uses retrospective T07 labels; it is not point-in-time label evidence for RQ3 forecasts.',
            'Known-CEX share is not CEX recall; Unknown addresses may be exchange wallets.',
            'Network covers netted USDT transfers >= 500000 only, not all Ethereum flows.',
            'spread_cs_proxy is a Corwin-Schultz high-low proxy, not a quoted spread; T06 has trades only.',
            'WhaleFlow is blocked for regression until the T12 gate opens; the column is exploratory.'])
    write_json(folder / 't14_summary.json', summary)
    write_json(folder / 't14_reproducibility.json', dict(all_match=same, hashes=hashes))
    print(json.dumps({k: summary[k] for k in summary if k not in ('feature_columns', 'input_sha256', 'code_sha256', 'upstream')},
                     indent=2, ensure_ascii=False), flush=True)
    if not passed:
        print(validation[validation.status.ne('PASS')].to_string())
        raise SystemExit('T14 validation failed')


if __name__ == '__main__':
    main()
