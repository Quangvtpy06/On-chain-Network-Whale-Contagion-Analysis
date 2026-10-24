"""Chuẩn bị manifest T15/T16 sau kiểm định; không upload hoặc sửa gate upstream."""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_t15_t16_release import validate
from src.forecast_inputs import file_hash, local_path, read_config, json_write, relative_path


def main():
    records, inputs, sources = [], {}, {}
    for task in ['t15', 't16']:
        review = validate(task)
        cfg = read_config(ROOT / f'config/{task}.yaml')
        folder = local_path(cfg['output_dir'])
        names = list(review['output_sha256']) + [f'{task}_summary.json', f'{task}_independent_review.json']
        for path in [folder / n for n in names] + [ROOT / f'config/{task}.yaml']:
            records.append(dict(task=task, path=relative_path(path), bytes=path.stat().st_size, sha256=file_hash(path)))
        inputs.update(review['input_sha256'])
        sources.update(review['source_config_sha256'])
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    committed = True
    for name, expected in sources.items():
        try:
            blob = subprocess.check_output(['git', 'show', head + ':' + name], cwd=ROOT, stderr=subprocess.DEVNULL)
            committed = committed and hashlib.sha256(blob).hexdigest() == expected
        except subprocess.CalledProcessError:
            committed = False
    manifest = dict(repo_id='team-crypto/Market-data-crypto-project', repo_type='dataset',
        manifest_file='data/hf_t15_t16_release_manifest.json',
        code_git_base_commit=head, code_git_commit=head if committed else None,
        source_identity='Exact source/config hashes in summaries; code_git_commit is set only when those files match that commit.',
        tasks_accepted={'t15': True, 't16': True},
        acceptance_scope='Validated in-sample associations and descriptive event responses, not individual ownership or causal/OOS evidence.',
        upload_files=records, blocked_upload_files=[], missing_files=[],
        remote_dependencies=[dict(path=p, sha256=h, revision='87bfe944925467fa74083ec0377c6b2579692bf0')
                             for p, h in sorted(inputs.items())],
        upload_performed=False, remote_deletions=0)
    path = ROOT / manifest['manifest_file']
    json_write(path, manifest)
    print(f'Prepared {relative_path(path)}: {len(records)} files; no upload performed')


if __name__ == '__main__':
    main()
