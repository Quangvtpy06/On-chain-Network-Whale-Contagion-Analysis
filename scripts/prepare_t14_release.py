"""Prepare a scoped T14 release from t14_inputs_v1; never uploads data."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_t14_release import validate_release
from src.t14_readiness import file_hash
from src.graph_config import read_config, project_path, relative_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-revision', help='Immutable HF revision for the accepted upstream inputs')
    args = parser.parse_args()
    verified = validate_release()
    settings_path = ROOT / 'config/t14.yaml'
    settings = read_config(settings_path)
    folder = project_path(settings['output_dir'])
    local_path = folder / 't14_release_manifest.json'
    local = json.loads(local_path.read_text(encoding='utf-8'))
    gate = json.loads((folder / 't14_downstream_gate.json').read_text(encoding='utf-8'))
    if not local['tasks_accepted'].get('t14_computation'):
        raise ValueError('T14 computation has not passed acceptance')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    for rel, expected in {**gate['source_sha256'], **gate['config_sha256']}.items():
        committed = subprocess.check_output(['git', 'show', f'{commit}:{rel}'], cwd=ROOT)
        if hashlib.sha256(committed).hexdigest() != expected:
            raise ValueError('Commit the accepted code/config before releasing: ' + rel)
    local.update(release_code_commit=commit, publication_state='prepared_for_hf_upload', upload_performed=False)
    local_path.write_text(json.dumps(local, indent=2) + '\n', encoding='utf-8')
    verified = validate_release()
    uploads = list(local['upload_files'])
    for path in [local_path, settings_path]:
        uploads.append(dict(path=relative_path(path), sha256=file_hash(path), bytes=path.stat().st_size))
    dependencies = [dict(row, **({'revision': args.input_revision} if args.input_revision else {}))
                    for row in local['remote_dependencies']]
    manifest = dict(repo_id=local['repo_id'], repo_type='dataset',
        manifest_file='data/hf_t14_release_manifest.json',
        code_repository='https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis',
        code_git_commit=commit, source_sha256=gate['source_sha256'], config_sha256=gate['config_sha256'],
        tasks_accepted={'t14': True}, readiness_contract_version=verified['contract_version'],
        acceptance_scope=verified['policy'],
        downstream_eligibility={key: verified[key] for key in
            ['forecast_inputs_ready_cex', 'forecast_inputs_ready_activity_cohort']},
        upload_files=uploads, blocked_upload_files=[], missing_files=[],
        remote_dependencies=dependencies, upload_performed=False, remote_deletions=0,
        note='Prepared manifest, not an upload receipt. Resolve each input at its recorded HF revision. '
             'Only scoped input readiness is certified; individual ownership and answered RQ3 are not.')
    destination = ROOT / 'data/hf_t14_release_manifest.json'
    destination.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(manifest=relative_path(destination), files_to_upload=len(uploads),
                         code_git_commit=commit, input_revision=args.input_revision), indent=2))


if __name__ == '__main__':
    main()
