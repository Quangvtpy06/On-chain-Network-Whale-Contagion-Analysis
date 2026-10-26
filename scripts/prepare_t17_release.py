"""Kiểm định rồi chuẩn bị manifest T17; không upload."""
import hashlib
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.validate_t17_release import validate
from src.forecast_inputs import file_hash,json_write,read_config,local_path,relative_path


def main():
    review=validate();cfg=read_config(ROOT/'config/t17.yaml');folder=local_path(cfg['output_dir'])
    paths=[folder/n for n in sorted(review['output_sha256'])]+[
        folder/'t17_summary.json',folder/'t17_independent_review.json',ROOT/'config/t17.yaml']
    records=[dict(task='t17',path=relative_path(p),bytes=p.stat().st_size,sha256=file_hash(p)) for p in paths]
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();committed=True
    for name,value in review['source_config_sha256'].items():
        try:
            blob=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT,stderr=subprocess.DEVNULL)
            committed=committed and hashlib.sha256(blob).hexdigest()==value
        except subprocess.CalledProcessError:committed=False
    manifest=dict(repo_id='team-crypto/Market-data-crypto-project',repo_type='dataset',
        manifest_file='data/hf_t17_release_manifest.json',code_git_base_commit=head,code_git_commit=head if committed else None,
        tasks_accepted={'t17':True},acceptance_scope=review['scope'],upload_files=records,blocked_upload_files=[],missing_files=[],
        remote_dependencies=[dict(path=p,sha256=h,revision='3bfb61848e1ac9bcfb0809d3aef334d1885a84a1')
                             for p,h in sorted(review['input_sha256'].items()) if p.startswith(('data/','market/'))],
        upload_performed=False,remote_deletions=0)
    json_write(ROOT/manifest['manifest_file'],manifest)
    json_write(ROOT/'data/hf_release_manifest.json',dict(manifest,manifest_file='data/hf_release_manifest.json'))
    print(f'T17 manifest prepared: {len(records)} artifacts; upload not performed')


if __name__=='__main__':main()
