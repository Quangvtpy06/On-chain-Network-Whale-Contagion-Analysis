"""Scoped, hash-checked T19 release manifest preparation."""
import hashlib
import json
import subprocess
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    t19_dir = ROOT / 'data/processed/t19'
    t19_summary = read_json(t19_dir / 't19_summary.json')
    t19_repro = read_json(t19_dir / 't19_repro.json')

    require(len(t19_summary.get('failed_checks', [])) == 0, 'T19 has failed checks')
    require(t19_summary.get('windows', {}).get('weekly', {}).get('readiness', {}).get('computation_validated') is True,
            'Weekly computation not validated')
    require(t19_summary.get('windows', {}).get('daily', {}).get('readiness', {}).get('computation_validated') is True,
            'Daily computation not validated')

    t19_files = [
        'config/t19.yaml',
        'data/processed/t19/t19_node_features_weekly.parquet',
        'data/processed/t19/t19_node_features_daily.parquet',
        'data/processed/t19/t19_feature_dictionary.parquet',
        'data/processed/t19/t19_label_summary_weekly.parquet',
        'data/processed/t19/t19_label_summary_daily.parquet',
        'data/processed/t19/t19_split_windows_weekly.parquet',
        'data/processed/t19/t19_split_windows_daily.parquet',
        'data/processed/t19/t19_validation.parquet',
        'data/processed/t19/t19_summary.json',
        'data/processed/t19/t19_repro.json',
    ]

    uploads = []
    for rel in sorted(t19_files):
        p = ROOT / rel
        require(p.is_file(), f'Missing T19 file: {rel}')
        uploads.append(dict(
            task='t19',
            path=rel,
            sha256=file_hash(p),
            bytes=p.stat().st_size
        ))

    try:
        git_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    except Exception:
        git_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=Path('C:/repo'), text=True).strip()

    manifest = dict(
        repo_id='team-crypto/Market-data-crypto-project',
        repo_type='dataset',
        manifest_file='data/hf_t19_release_manifest.json',
        code_repository='https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis',
        code_git_commit=git_commit,
        tasks_accepted={'t19': True},
        acceptance_scope=(
            'T19 protocol t19_v1: Node-window feature matrix (T09 centrality, T10 betweenness/eigenvector/clustering, '
            'T11 community features), contemporaneous retrospective T07 labels, time-ordered train/val/test split with gaps.'
        ),
        downstream_eligibility=dict(
            protocol_id='t19_v1',
            primary_window='weekly',
            features_weekly_path='data/processed/t19/t19_node_features_weekly.parquet',
            features_daily_path='data/processed/t19/t19_node_features_daily.parquet',
            ready_for_t20=True,
            pit_label_forecast=False
        ),
        upload_files=uploads,
        blocked_upload_files=[],
        missing_files=[],
        remote_dependencies=[],
        upload_performed=False,
        remote_deletions=0,
        note='Scoped release for T19 Graph ML node-window feature tables and time-ordered split.'
    )

    dest = ROOT / 'data/hf_t19_release_manifest.json'
    dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(
        manifest=str(dest.relative_to(ROOT)),
        files_to_upload=len(uploads),
        git_commit=git_commit
    ), indent=2))


if __name__ == '__main__':
    main()
