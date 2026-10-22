"""T14: build NetFlow, WhaleFlow, realized volatility and controls X_t (daily, point-in-time).

Run from the project root after T05-T07, T08 and T12 have been accepted:

    python T14_Flow_Volatility.py

The table is computed twice (second run in .cache/), hashes are compared, a
truncation test removes future data and checks that no feature changes, and only
then t14_summary.json records three separate levels per branch: computation validated,
retrospective analysis, point-in-time forecast. `--skip-reproducibility` is for
exploration and never marks the computation validated.
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


def minute_files(cfg, settings, dates):
    mm = settings['market_minute']
    return [project_path(mm['dir']) / mm['file_pattern'].format(date=d) for d in dates]


def dir_hash(paths):
    """One digest over many files: sha256 of sorted (name, sha256) pairs."""
    import hashlib
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode()); h.update(sha256(p).encode())
    return h.hexdigest()


def preflight(cfg, settings):
    """Fail early with the list of missing files instead of a deep traceback."""
    dates = list(fv.day_index(cfg['project']['start_date'], cfg['project']['end_date']))
    needed = [project_path(v) for v in settings['inputs'].values()]
    needed += [project_path(cfg['data']['summary_json'])]
    needed += minute_files(cfg, settings, dates)
    missing = [relative_path(p) if p.is_relative_to(ROOT) else str(p) for p in needed if not p.is_file()]
    if len(missing) > 12:
        missing = missing[:12] + [f'... và {len(missing) - 12} file khác']
    if missing:
        raise SystemExit('Thiếu dữ liệu đầu vào (tải từ Hugging Face, xem README bước 3):\n  - ' + '\n  - '.join(missing))


def load_inputs(cfg, settings, dates):
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
        minute=pd.concat([pd.read_parquet(p, columns=['minute', 'close']) for p in minute_files(cfg, settings, dates)],
                         ignore_index=True),
        pit_labels=secondary,
        daily=pd.read_parquet(paths['market_1d']),
        eth_stats=pd.read_csv(paths['eth_stats_csv']),
    ), paths


def compute(folder, cfg, settings, dates, gate_open):
    inputs, paths = load_inputs(cfg, settings, dates)
    table = fv.build_features(inputs, settings, dates)
    table['whaleflow_gate_open'] = bool(gate_open)
    # T07 labels are retrospective (no historical availability date); see T12 report and readiness.
    table['cex_labels_pit'] = False
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
    preflight(cfg, settings)
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
    pit_max = int(table.pit_cex_n_wallets.max())
    readiness = fv.readiness(passed and bool(same), gate_open, settings['pit_cex_labels']['enabled'], pit_max)
    feature_cols = fv.feature_columns(table)
    summary = dict(
        protocol_id=settings['protocol_id'],
        settings_sha256=sha256(SETTINGS),
        code_sha256={relative_path(p): sha256(p) for p in [ROOT / 'src/flow_volatility.py', ROOT / 'T14_Flow_Volatility.py']},
        input_sha256={**{k: sha256(project_path(v)) for k, v in settings['inputs'].items()},
                      'market_minute_files': dir_hash(minute_files(cfg, settings, dates))},
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
        validation_passed_note='Computation checks only; says nothing about label point-in-time validity.',
        readiness=readiness,
        t12_gate_ready_for_cohort_whaleflow=gate_open,
        sampling_minutes=settings['volatility']['sampling_minutes'],
        pit_cex_wallets_available_max=pit_max,
        caveats=[
            'CEX NetFlow and large_*_cex use retrospective T07 labels with no historical availability date; they are not point-in-time forecast evidence (RQ3). Label-free market and large-transfer columns are not affected.',
            'Known-CEX share is not CEX recall; Unknown addresses may be exchange wallets.',
            'Network covers netted USDT transfers >= 500000 only, not all Ethereum flows.',
            'spread_cs_proxy is a Corwin-Schultz high-low proxy, not a quoted spread; T06 has trades only.',
            'Cohort WhaleFlow is blocked until the T12 gate opens; the column is exploratory.',
            '1-minute realized volatility can contain microstructure noise; compare with rv_5m in robustness (T17).'])
    write_json(folder / 't14_summary.json', summary)
    write_json(folder / 't14_reproducibility.json', dict(all_match=same, hashes=hashes))
    print(json.dumps({k: summary[k] for k in summary if k not in ('feature_columns', 'input_sha256', 'code_sha256', 'upstream')},
                     indent=2, ensure_ascii=False), flush=True)
    if not passed:
        print(validation[validation.status.ne('PASS')].to_string())
        raise SystemExit('T14 validation failed')


if __name__ == '__main__':
    main()
