"""Scoped, hash-checked T14 v2 release manifest preparation."""
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
    t14_dir = ROOT / 'data/processed/t14'
    t14_summary = read_json(t14_dir / 't14_summary.json')
    t14_repro = read_json(t14_dir / 't14_reproducibility.json')
    require(t14_summary.get('validation_passed') is True, 'T14 validation not passed')
    require(t14_summary.get('reproducible') is True, 'T14 not reproducible')
    require(t14_repro.get('all_match') is True, 'T14 reproducibility all_match not True')

    t14_files = [
        'data/processed/t14/t14_features_daily.parquet',
        'data/processed/t14/t14_sample_eligibility_daily.parquet',
        'data/processed/t14/t14_cohort_cex_overlap_daily.parquet',
        'data/processed/t14/t14_cex_coverage_daily.parquet',
        'data/processed/t14/t14_cex_coverage_monthly.parquet',
        'data/processed/t14/t14_validation.parquet',
        'data/processed/t14/t14_summary.json',
        'data/processed/t14/t14_reproducibility.json',
        'config/t14.yaml',
    ]

    uploads = []
    for rel in sorted(t14_files):
        p = ROOT / rel
        require(p.is_file(), f'Missing T14 file: {rel}')
        uploads.append(dict(
            task='t14',
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
        manifest_file='data/hf_t14_release_manifest.json',
        code_repository='https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis',
        code_git_commit=git_commit,
        tasks_accepted={'t14': True},
        acceptance_scope=(
            'T14 v2 protocol: Realized Volatility 1m baseline (1440 bars) and 5m sensitivity (288 bars), '
            'PIT CEX NetFlow, WhaleFlow PIT (v2 activity cohort scope), and control variables.'
        ),
        downstream_eligibility=dict(
            protocol_id='t14_v2',
            features_path='data/processed/t14/t14_features_daily.parquet',
            whaleflow_scope='v2_activity_cohort',
            ready_for_t15=True
        ),
        upload_files=uploads,
        blocked_upload_files=[],
        missing_files=[],
        remote_dependencies=[],
        upload_performed=False,
        remote_deletions=0,
        note='Scoped release for T14 v2. Uploads validated T14 tables and frozen config.'
    )

    dest = ROOT / 'data/hf_t14_release_manifest.json'
    dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(
        manifest=str(dest.relative_to(ROOT)),
        files_to_upload=len(uploads),
        git_commit=git_commit
    ), indent=2))


if __name__ == '__main__':
    main()
