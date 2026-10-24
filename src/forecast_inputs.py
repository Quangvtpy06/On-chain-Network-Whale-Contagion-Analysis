"""Đọc release đã xác minh; không suy readiness từ cờ RQ3 upstream."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.validate_t14_release import validate_release
from src.graph_config import ROOT, project_path, relative_path, read_config
from src.t14_readiness import POLICY


def require(ok, message):
    if not ok:
        raise ValueError(message)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def hash_paths(paths):
    return {relative_path(p): file_hash(p) for p in paths}


def verify_hashes(hashes):
    for name, value in hashes.items():
        require(file_hash(local_path(name)) == value, 'Changed input/source/config: ' + name)


def local_path(value):
    require(not Path(value).is_absolute(), 'Paths must be project-relative')
    p = project_path(value).resolve()
    require(p.is_relative_to(ROOT.resolve()), 'Path escapes project root')
    return p


def json_write(path, value):
    # NumPy values get their actual JSON types; NaN/Infinity never become JSON numbers.
    def normalize(x):
        if isinstance(x, dict):
            return {str(k): normalize(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [normalize(v) for v in x]
        if isinstance(x, np.generic):
            return normalize(x.item())
        if isinstance(x, float) and not np.isfinite(x):
            return None
        return x
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(normalize(value), indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def utc_daily(frame, key='date'):
    require(key in frame, 'Missing calendar column: ' + key)
    out = frame.copy()
    stamps = pd.DatetimeIndex(pd.to_datetime(out[key], utc=True, errors='raise')).as_unit('ns')
    require(len(stamps) > 0 and not stamps.hasnans, 'Empty/NaT calendar')
    require(stamps.equals(stamps.normalize()), 'Calendar is not UTC midnight')
    require(not stamps.duplicated().any(), 'Duplicate UTC day')
    out[key] = stamps
    out = out.sort_values(key).reset_index(drop=True)
    expected = pd.date_range(out[key].iloc[0], out[key].iloc[-1], freq='D')
    require(pd.DatetimeIndex(out[key]).equals(expected), 'Missing UTC calendar day')
    return out


def bool_column(frame, column):
    require(column in frame and pd.api.types.is_bool_dtype(frame[column]) and not frame[column].isna().any(),
            'Missing/invalid boolean eligibility: ' + column)
    return frame[column]


def finite(frame, columns):
    require(set(columns) <= set(frame), 'Missing required columns: ' + str(sorted(set(columns) - set(frame))))
    a = frame[columns].to_numpy(float)
    require(not np.isinf(a).any(), 'Infinity in required inputs')
    return pd.Series(np.isfinite(a).all(axis=1), index=frame.index)


def allowed(summary, set_name, columns):
    candidates = summary.get('predictor_sets', {}).get(set_name, [])
    require(bool(candidates) and set(columns) <= set(candidates), 'Predictors outside T14 set: ' + set_name)
    require(not any(c.startswith('target_') or c in {'date', 'available_at'} for c in columns), 'Target/calendar leakage')


def load_t14(cfg):
    validated = validate_release()  # Full upstream source/config/input/output and predicate check.
    require(validated['contract_version'] == cfg['contract_version'] == 't14_inputs_v1', 'Unsupported contract')
    folder = local_path(cfg['t14_dir'])
    upstream = read_config(ROOT / 'config/t14.yaml')
    require(folder == local_path(upstream['output_dir']), 'Consumer T14 path differs from validated release')
    paths = [folder / n for n in ['t14_features_daily.parquet', 't14_sample_eligibility_daily.parquet',
                                  't14_summary.json', 't14_downstream_gate.json', 't14_release_manifest.json']]
    before = hash_paths(paths)
    gate = json.loads(paths[3].read_text(encoding='utf-8'))
    require(gate['policy'] == POLICY, 'Unsupported T14 information policy')
    summary = json.loads(paths[2].read_text(encoding='utf-8'))
    features = utc_daily(pd.read_parquet(paths[0]))
    eligibility = utc_daily(pd.read_parquet(paths[1]))
    require(features.date.equals(eligibility.date), 'Eligibility/calendar mismatch')
    available = pd.to_datetime(features.available_at, utc=True).dt.as_unit('ns')
    require(available.eq(features.date + pd.Timedelta(days=1)).all(), 'Incorrect feature availability cutoff')
    for name in ['t14_features_daily.parquet', 't14_sample_eligibility_daily.parquet']:
        require(file_hash(folder / name) == gate['output_sha256'][name], 'T14 artifact changed while loading')
    verify_hashes(before)
    return features, eligibility, summary, gate, before
