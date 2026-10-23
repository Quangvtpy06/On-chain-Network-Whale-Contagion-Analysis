"""Verify a local T14 release before downstream use. Never uploads or edits gates."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import T14_Flow_Volatility as pipeline
from src import t14_readiness as readiness
from src.graph_config import read_config, project_path, relative_path


def validate_release():
    settings = read_config(pipeline.SETTINGS)
    folder = project_path(settings['output_dir'])
    gate = json.loads((folder / 't14_downstream_gate.json').read_text(encoding='utf-8'))
    manifest = json.loads((folder / 't14_release_manifest.json').read_text(encoding='utf-8'))
    if gate.get('contract_version') != readiness.VERSION or manifest.get('readiness_contract_version') != readiness.VERSION:
        raise ValueError('Unsupported readiness contract')
    if gate.get('protocol_id') != settings['protocol_id']:
        raise ValueError('T14 protocol mismatch')
    expected_sources = {'T14_Flow_Volatility.py', 'src/flow_volatility.py', 'src/cex_label_history.py',
                        'src/t14_readiness.py', 'scripts/validate_t14_release.py'}
    expected_inputs = {relative_path(project_path(p)) for p in settings['inputs'].values()}
    expected_outputs = set(readiness.PRODUCTS + ['t14_validation.parquet', 't14_summary.json',
                                               't14_reproducibility.json'])
    if set(gate.get('source_sha256', {})) != expected_sources or set(gate.get('input_sha256', {})) != expected_inputs:
        raise ValueError('Incomplete source/input provenance')
    if set(gate.get('config_sha256', {})) != {relative_path(pipeline.SETTINGS)}:
        raise ValueError('Missing config provenance')
    if set(gate.get('output_sha256', {})) != expected_outputs:
        raise ValueError('Incomplete output provenance')
    for key in ['source_sha256', 'config_sha256', 'input_sha256']:
        readiness.verify_hash_map(ROOT, gate[key], key)
        if manifest.get(key) != gate[key]:
            raise ValueError('Manifest and gate disagree: ' + key)
    readiness.verify_hash_map(folder, gate['output_sha256'], 'T14 outputs')
    accepted = {row['path']: row['sha256'] for row in manifest.get('upload_files', [])}
    if set(accepted) != {relative_path(folder / name) for name in expected_outputs | {'t14_downstream_gate.json'}}:
        raise ValueError('Incomplete release artifact list')
    readiness.verify_hash_map(ROOT, accepted, 'Release artifact hashes')
    t12, t07 = pipeline.load_verified_gates(settings)
    validation = pd.read_parquet(folder / 't14_validation.parquet')
    repro = json.loads((folder / 't14_reproducibility.json').read_text(encoding='utf-8'))
    if repro.get('all_match') is not True:
        raise ValueError('Reproducibility not certified')
    for name, row in repro.get('hashes', {}).items():
        if row.get('run1') != row.get('run2') or row.get('run1') != readiness.file_hash(folder / name):
            raise ValueError('Reproduced output changed: ' + name)
    expected = readiness.build_readiness(settings, {'t07': t07, 't12': t12}, validation, repro['hashes'])
    for key, value in expected.items():
        if gate.get(key) != value:
            raise ValueError('Gate predicate mismatch: ' + key)
    if manifest.get('tasks_accepted') != {'t14_computation': expected['conditions']['computation_validated']}:
        raise ValueError('Manifest computation status mismatch')
    summary = json.loads((folder / 't14_summary.json').read_text(encoding='utf-8'))
    for key in ['forecast_inputs_ready_cex', 'forecast_inputs_ready_activity_cohort']:
        if summary.get(key) != expected[key] or manifest.get(key) != expected[key]:
            raise ValueError('Readiness status mismatch: ' + key)
    if gate['rq3_answered'] or gate['ready_for_individual_investor_inference']:
        raise ValueError('Input contract cannot certify RQ3 or individual ownership')
    return dict(contract_version=readiness.VERSION, artifacts_verified=len(accepted),
                forecast_inputs_ready_cex=expected['forecast_inputs_ready_cex'],
                forecast_inputs_ready_activity_cohort=expected['forecast_inputs_ready_activity_cohort'],
                policy=expected['policy'], publication_state=manifest['publication_state'])


if __name__ == '__main__':
    print(json.dumps(validate_release(), indent=2))
