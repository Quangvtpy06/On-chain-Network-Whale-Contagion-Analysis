"""Upload exactly the accepted manifest, then verify every remote file.

Authentication uses hf auth login / HF_TOKEN. Never prints credentials.
No remote deletion is performed.
"""
import hashlib
import json
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
    manifest_path = ROOT / 'data/hf_release_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['blocked_upload_files'] or manifest['missing_files'] or not all(manifest['tasks_accepted'].values()):
        raise ValueError('Manifest contains blocked, missing or unaccepted artifacts.')
    records = list(manifest['upload_files'])
    records.append(dict(path='data/hf_release_manifest.json', sha256=digest(manifest_path)))
    seen = set()
    for record in records:
        rel = record['path']; path = (ROOT / rel).resolve()
        if not path.is_relative_to(ROOT.resolve()) or rel in seen or not path.is_file():
            raise ValueError(f'Invalid release path: {rel}')
        if path.suffix not in {'.parquet', '.json', '.yaml'} and rel != 'eth_stats_from_2025.csv':
            raise ValueError(f'Unexpected release file type: {rel}')
        if digest(path) != record['sha256']:
            raise ValueError(f'Artifact changed after acceptance: {rel}')
        seen.add(rel)
    api = HfApi()
    api.whoami()  # fail before upload if no authentication is configured
    repo = manifest['repo_id']; kind = manifest['repo_type']
    parent = api.repo_info(repo, repo_type=kind).sha
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
            commit_message='Publish validated graph metrics and exploratory T12 with downstream gate')
    revision = commit.oid if commit else parent
    remote = {item.path: item for item in api.get_paths_info(repo, sorted(seen), repo_type=kind, revision=revision)}
    if any(r['path'] not in remote or not remote_matches(remote[r['path']], ROOT/r['path'], r['sha256']) for r in records):
        raise ValueError('Remote verification failed after upload.')
    destination = ROOT/'.release'; destination.mkdir(exist_ok=True)
    receipt = dict(repo_id=repo, revision=revision, verified_files=len(records), changed_files=len(changed),
        manifest_sha256=digest(manifest_path), commit_url=commit.commit_url if commit else
        f'https://huggingface.co/datasets/{repo}/tree/{revision}', remote_deletions=0)
    (destination/'hf_publish_receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == '__main__':
    main()
