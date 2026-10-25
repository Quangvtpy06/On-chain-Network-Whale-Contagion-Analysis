"""Chuẩn bị manifest T18 đã kiểm định; không upload."""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.validate_t18_release import validate
from src.forecast_inputs import file_hash,json_write,read_config,local_path,relative_path


def main():
    review=validate();cfg=read_config(ROOT/'config/t18.yaml');folder=local_path(cfg['output_dir'])
    paths=[folder/n for n in review['output_sha256']]+[folder/'t18_summary.json',folder/'t18_independent_review.json',ROOT/'config/t18.yaml']
    records=[dict(task='t18',path=relative_path(p),bytes=p.stat().st_size,sha256=file_hash(p)) for p in paths]
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();committed=True
    for name,value in review['source_config_sha256'].items():
        try:
            blob=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT,stderr=subprocess.DEVNULL)
            committed=committed and hashlib.sha256(blob).hexdigest()==value
        except subprocess.CalledProcessError:committed=False
    manifest=dict(repo_id='team-crypto/Market-data-crypto-project',repo_type='dataset',
        manifest_file='data/hf_t18_release_manifest.json',code_git_base_commit=head,code_git_commit=head if committed else None,
        tasks_accepted={'t18':True},acceptance_scope=review['scope'],upload_files=records,blocked_upload_files=[],missing_files=[],
        remote_dependencies=[dict(path=p,sha256=h,revision='d3cc595be2d452467e823596749a63723dfa2e1d')
                             for p,h in sorted(review['input_sha256'].items())],upload_performed=False,remote_deletions=0)
    json_write(ROOT/manifest['manifest_file'],manifest)
    # Make the default uploader use only this scoped release; other HF files are not deleted.
    json_write(ROOT/'data/hf_release_manifest.json',dict(manifest,manifest_file='data/hf_release_manifest.json'))
    print(f'T18 manifests prepared: {len(records)} artifacts; upload not performed')


if __name__=='__main__':main()
