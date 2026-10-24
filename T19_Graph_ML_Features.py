"""T19: node-window feature matrix, T07 labels and a time-ordered split.

Run from the project root after T07, T09, T10 and T11 data are in data/processed:

    python T19_Graph_ML_Features.py

For each window type the tables are built twice (inputs re-read the second time) and their
content hashes compared; truncation and future-mutation tests then check that no feature of a
past window changes. t19_summary.json records computation_validated separately from
node_classification_ready; a point-in-time label forecast is never claimed (T07 labels are
retrospective). Output tables are Parquet only.
"""
import hashlib
import json
from datetime import datetime, timezone

import pandas as pd
import yaml

from src import graph_ml_features as gm
from src.graph_config import ROOT, project_path, relative_path

SETTINGS = ROOT / 'config/t19.yaml'


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False, default=str), encoding='utf-8')
    temporary.replace(path)


def input_paths(cfg, window):
    return {k: project_path(v.format(window=window)) for k, v in cfg['inputs'].items()}


def preflight(cfg):
    needed = [p for w in cfg['window_types'] for p in input_paths(cfg, w).values()]
    missing = sorted({relative_path(p) if p.is_relative_to(ROOT) else str(p) for p in needed if not p.is_file()})
    if missing:
        raise SystemExit('Thiếu dữ liệu đầu vào (tải từ Hugging Face: data/processed/t07, t09, t10, t11):\n  - ' + '\n  - '.join(missing))


def load_inputs(cfg, window):
    paths = input_paths(cfg, window)
    t09 = pd.read_parquet(paths['t09_nodes'])
    t10 = pd.read_parquet(paths['t10_nodes'])
    t11 = pd.read_parquet(paths['t11_nodes'])
    snapshot = pd.read_parquet(paths['t09_snapshot'])
    t11_snapshot = pd.read_parquet(paths['t11_snapshot'])
    labels = pd.read_parquet(paths['t07_labels'])
    for name, frame in (('t09', t09), ('t10', t10), ('t11', t11)):
        wrong = frame.window_type.ne(window)
        if wrong.any():
            raise SystemExit(f'{name} chứa window_type khác {window}')
    return dict(t09=t09, t10=t10, t11=t11, snapshot=snapshot, t11_snapshot=t11_snapshot, labels=labels, paths=paths)


def compute(cfg, window, inputs):
    """Everything derived from the inputs; pure, so the second run can be compared bit for bit."""
    merged, stats = gm.merge_nodes(inputs['t09'], inputs['t10'], inputs['t11'])
    bounds = gm.window_bounds(inputs['snapshot'], window)
    features, feature_columns = gm.build_features(merged, inputs['snapshot'], bounds, cfg)
    pre_hash = gm.frame_hash(features[feature_columns])
    with_labels, classes = gm.attach_labels(features, inputs['labels'], cfg)
    split_table = gm.split_windows(bounds, cfg['split']['fractions'], int(cfg['split']['gap_windows'][window]))
    table = gm.attach_split(with_labels, split_table)
    summary = gm.label_summary(table, cfg)
    return dict(merged=merged, stats=stats, bounds=bounds, features=table, feature_columns=feature_columns, classes=classes,
                split_table=split_table, label_summary=summary, pre_join_feature_hash=pre_hash)


def main():
    cfg = yaml.safe_load(SETTINGS.read_text(encoding='utf-8'))
    preflight(cfg)
    folder = project_path(cfg['output_dir'])
    folder.mkdir(parents=True, exist_ok=True)
    validation, report, hashes, files = [], {}, {}, {}
    dictionary = None
    for window in cfg['window_types']:
        inputs = load_inputs(cfg, window)
        run1 = compute(cfg, window, inputs)
        run2 = compute(cfg, window, load_inputs(cfg, window))
        outputs = {'features': run1['features'], 'split': run1['split_table'], 'labels': run1['label_summary']}
        hashes[window] = {name: dict(run1=gm.frame_hash(frame), run2=gm.frame_hash(run2[key]))
                          for name, frame, key in [('features', outputs['features'], 'features'),
                                                   ('split', outputs['split'], 'split_table'),
                                                   ('label_summary', outputs['labels'], 'label_summary')]}
        repro_same = all(h['run1'] == h['run2'] for h in hashes[window].values())
        rows = gm.validate(window, run1['features'], run1['feature_columns'], run1['merged'], run1['stats'], run1['bounds'],
                           inputs['snapshot'], run1['split_table'], inputs['t11_snapshot'], run1['classes'], cfg, run1['label_summary'])
        table_hash = gm.frame_hash(run1['features'][run1['feature_columns']])
        rows.append(dict(check='features_unchanged_after_label_and_split_join', scope=window,
                         status='PASS' if table_hash == run1['pre_join_feature_hash'] else 'FAIL', detail=''))
        rows.append(dict(check='two_runs_identical_content_hash', scope=window, status='PASS' if repro_same else 'FAIL', detail=''))
        leak = gm.leakage_checks(run1['merged'], inputs['snapshot'], run1['bounds'], cfg, run1['feature_columns'])
        for row in leak:
            row['scope'] = f'{window}:{row["scope"]}'
        rows.extend(leak)
        leak_ok = all(r['status'] == 'PASS' for r in leak)
        coverage_ok = bool(run1['label_summary'].meets_min_addresses.all())
        rows_window = [r for r in rows if r['scope'].split(':')[0] == window]
        ready = gm.readiness(window, [dict(r, scope=window) for r in rows_window], repro_same, leak_ok and table_hash == run1['pre_join_feature_hash'],
                             coverage_ok, len(run1['classes']))
        counts = run1['features'].groupby('split').agg(rows=('address', 'size'), addresses=('address', 'nunique'))
        report[window] = dict(
            readiness=ready, classes=run1['classes'], n_rows=len(run1['features']), n_features=len(run1['feature_columns']),
            n_windows=len(run1['bounds']), split_counts=counts.to_dict('index'),
            label_status_rows=run1['features'].label_status.value_counts().to_dict(),
            label_status_addresses=run1['features'].groupby('label_status').address.nunique().to_dict(),
            classes_below_min=run1['label_summary'][~run1['label_summary'].meets_min_addresses][['split', 'label_class', 'n_addresses']].to_dict('records'),
            gap_windows=int(cfg['split']['gap_windows'][window]))
        validation.extend(rows)
        dictionary = gm.feature_dictionary(run1['feature_columns']) if dictionary is None else dictionary
        for name, frame in (('node_features', run1['features']), ('split_windows', run1['split_table']), ('label_summary', run1['label_summary'])):
            path = folder / f't19_{name}_{window}.parquet'
            frame.to_parquet(path, index=False)
            files[path.name] = sha256(path)
    dictionary.to_parquet(folder / 't19_feature_dictionary.parquet', index=False)
    checks = pd.DataFrame(validation)
    checks.to_parquet(folder / 't19_validation.parquet', index=False)
    failed = checks[checks.status.eq('FAIL')]
    sources = {w: {k: sha256(p) for k, p in input_paths(cfg, w).items()} for w in cfg['window_types']}
    summary = dict(
        protocol_id=cfg['protocol_id'], generated_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        primary_window_type=cfg['primary_window_type'], windows=report, failed_checks=failed[['scope', 'check', 'detail']].to_dict('records'),
        label_policy='retrospective_static_t07_labels_not_point_in_time',
        config_sha256=sha256(SETTINGS), input_sha256=sources, output_file_sha256=files)
    write_json(folder / 't19_summary.json', summary)
    write_json(folder / 't19_repro.json', dict(protocol_id=cfg['protocol_id'], content_hashes=hashes))
    for window, info in report.items():
        r = info['readiness']
        print(f"{window}: rows={info['n_rows']:,} classes={len(info['classes'])} validated={r['computation_validated']} "
              f"node_classification_ready={r['node_classification_ready']}")
    if len(failed):
        print('FAILED CHECKS:\n' + failed[['scope', 'check', 'detail']].to_string())
        raise SystemExit(1)


if __name__ == '__main__':
    main()
