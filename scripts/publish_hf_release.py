"""Upload exactly the accepted manifest, then verify every remote file.

Authentication uses hf auth login / HF_TOKEN. Never prints credentials.
No remote deletion is performed.
"""
import hashlib
import json
import argparse
from pathlib import Path

from huggingface_hub import HfApi, CommitOperationAdd

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def remote_matches(remote, path, expected):
    if remote.lfs:
        value = remote.lfs.get('sha256') if isinstance(remote.lfs, dict) else remote.lfs.sha256
        return value == expected
    data = path.read_bytes()
    return remote.blob_id == hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',default='data/hf_release_manifest.json')
    parser.add_argument('--commit-message')
    parser.add_argument('--receipt-name',default='hf_publish_receipt.json')
    parser.add_argument('--direct',action='store_true',help='Use a direct HTTPS client instead of environment proxies')
    args=parser.parse_args()
    if args.direct:
        import httpx
        from huggingface_hub import set_client_factory
        set_client_factory(lambda:httpx.Client(trust_env=False,follow_redirects=True,timeout=120))
    manifest_path = (ROOT / args.manifest).resolve()
    if not manifest_path.is_relative_to(ROOT.resolve()):raise ValueError('Manifest must be inside the project')
    if Path(args.receipt_name).name!=args.receipt_name:raise ValueError('Receipt must be a filename')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['blocked_upload_files'] or manifest['missing_files'] or not all(manifest['tasks_accepted'].values()):
        raise ValueError('Manifest contains blocked, missing or unaccepted artifacts.')
    records = list(manifest['upload_files'])
    records.append(dict(path=manifest_path.relative_to(ROOT).as_posix(), sha256=digest(manifest_path)))
    seen = set()
    for record in records:
        rel = record['path']; path = (ROOT / rel).resolve()
        if not path.is_relative_to(ROOT.resolve()) or rel in seen or not path.is_file():
            raise ValueError(f'Invalid release path: {rel}')
        t11_figures={'data/figures/t11/'+name for name in [
            't11_modularity_timeseries.png','t11_concentration_timeseries.png',
            't11_rq4_stress_comparison.png','t11_community_map_2026-10-17.png']}
        analysis_assets = set()
        if manifest.get('tasks_accepted', {}).get('t15') is True:
            analysis_assets.update({'data/processed/t15/t15_flow_coefficients.png', 'data/processed/t15/t15_report.md'})
        if manifest.get('tasks_accepted', {}).get('t16') is True:
            analysis_assets.add('data/processed/t16/t16_report.md')
            analysis_assets.update('data/processed/t16/t16_'+name+'_response.png' for name in
                                   ['large_transfer', 'cex_net_inflow', 'activity_cohort_net_inflow', 'concentration'])
        if manifest.get('tasks_accepted', {}).get('t18') is True:
            analysis_assets.update('data/processed/t18/'+name for name in
                                   ['t18_report.md','t18_oos_rmse.png','t18_event_holdout_counts.png'])
        if manifest.get('tasks_accepted', {}).get('t17') is True:
            analysis_assets.update('data/processed/t17/'+name for name in
                                   ['t17_report.md','t17_regression_robustness.png'])
        if manifest.get('tasks_accepted', {}).get('rq4_stress_lead') is True:
            analysis_assets.update('data/processed/rq4_stress_lead/'+name for name in
                                   ['rq4_stress_lead_report.md','rq4_stress_lead.png'])
        if manifest.get('tasks_accepted', {}).get('t23') is True:
            analysis_assets.add('data/processed/t23/t23_timeline.png')
        if (path.suffix not in {'.parquet', '.json', '.yaml'} and rel != 'eth_stats_from_2025.csv'
                and rel not in t11_figures and rel not in analysis_assets):
            raise ValueError(f'Unexpected release file type: {rel}')
        if digest(path) != record['sha256']:
            raise ValueError(f'Artifact changed after acceptance: {rel}')
        seen.add(rel)
    api = HfApi()
    api.whoami()  # fail before upload if no authentication is configured
    repo = manifest['repo_id']; kind = manifest['repo_type']
    parent = api.repo_info(repo, repo_type=kind).sha
    # Scoped releases bind already-published upstream data without replacing it.
    dependencies=manifest.get('remote_dependencies',[])
    upstream = {}
    for dependency_revision in {row.get('revision', parent) for row in dependencies}:
        paths = [row['path'] for row in dependencies if row.get('revision', parent) == dependency_revision]
        upstream.update({(dependency_revision, item.path): item for item in
                         api.get_paths_info(repo, paths, repo_type=kind, revision=dependency_revision)})
    for row in dependencies:
        path=ROOT/row['path']
        key = (row.get('revision', parent), row['path'])
        if not path.is_file() or digest(path)!=row['sha256'] or key not in upstream or not remote_matches(upstream[key],path,row['sha256']):
            raise ValueError('Remote upstream differs from accepted input: '+row['path'])
    raw = manifest.get('raw_input', manifest.get('raw_input_already_on_remote', {}))
    if raw.get('path') and raw.get('sha256') and raw['path'] not in seen:
        found = api.get_paths_info(repo, [raw['path']], repo_type=kind, revision=parent)
        if not found or not found[0].lfs:
            raise ValueError('Cannot verify the raw input already stored on Hugging Face.')
        lfs = found[0].lfs
        actual = lfs.get('sha256') if isinstance(lfs, dict) else lfs.sha256
        if actual != raw['sha256']:
            raise ValueError('Remote raw input differs from the accepted source.')
    current = {item.path: item for item in api.get_paths_info(repo, sorted(seen), repo_type=kind, revision=parent)}
    changed = [r for r in records if r['path'] not in current or
        not remote_matches(current[r['path']], ROOT/r['path'], r['sha256'])]
    commit = None
    if changed:
        commit = api.create_commit(repo, repo_type=kind, parent_commit=parent,
            operations=[CommitOperationAdd(path_in_repo=r['path'], path_or_fileobj=ROOT/r['path']) for r in changed],
            commit_message=args.commit_message or 'Publish validated dataset release: '+', '.join(sorted(manifest['tasks_accepted'])))
    revision = commit.oid if commit else parent
    remote = {item.path: item for item in api.get_paths_info(repo, sorted(seen), repo_type=kind, revision=revision)}
    if any(r['path'] not in remote or not remote_matches(remote[r['path']], ROOT/r['path'], r['sha256']) for r in records):
        raise ValueError('Remote verification failed after upload.')
    destination = ROOT/'.release'; destination.mkdir(exist_ok=True)
    receipt = dict(repo_id=repo, revision=revision, verified_files=len(records), changed_files=len(changed),
        manifest_sha256=digest(manifest_path), commit_url=commit.commit_url if commit else
        f'https://huggingface.co/datasets/{repo}/tree/{revision}', remote_deletions=0,
        code_git_commit=manifest.get('code_git_commit'), remote_dependencies=dependencies)
    (destination/args.receipt_name).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == '__main__':
    main()
