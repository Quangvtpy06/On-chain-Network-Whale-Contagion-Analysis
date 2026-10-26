"""Chuẩn bị manifest dữ liệu RQ4 đã kiểm định; không upload."""
import hashlib
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.validate_rq4_stress_lead import validate
from src.forecast_inputs import file_hash,json_write,local_path,read_config,relative_path


def main():
    review=validate()
    cfg=read_config(ROOT/'config/rq4_stress_lead.yaml')
    folder=local_path(cfg['output_dir'])
    names=sorted(review['output_sha256'])+['rq4_stress_lead_summary.json','rq4_stress_lead_independent_review.json']
    paths=[folder/n for n in names]+[ROOT/'config/rq4_stress_lead.yaml']
    records=[dict(task='rq4_stress_lead',path=relative_path(p),bytes=p.stat().st_size,sha256=file_hash(p)) for p in paths]
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    committed=True
    for name,value in review['source_config_sha256'].items():
        try:
            blob=subprocess.check_output(['git','show',head+':'+name],cwd=ROOT,stderr=subprocess.DEVNULL)
            committed=committed and hashlib.sha256(blob).hexdigest()==value
        except subprocess.CalledProcessError:committed=False
    dependencies=[]
    for path,sha256 in sorted(review['input_sha256'].items()):
        if not path.startswith('data/'):
            continue  # Manifest T13 nằm trong code GitHub, không phải artifact HF.
        revision=('ad3d2603bb3ff1e15033d1f98cd2520151d64dbb' if path.startswith('data/processed/t13/')
                  else '3bfb61848e1ac9bcfb0809d3aef334d1885a84a1')
        dependencies.append(dict(path=path,sha256=sha256,revision=revision))
    manifest=dict(repo_id='team-crypto/Market-data-crypto-project',repo_type='dataset',
        manifest_file='data/hf_rq4_stress_lead_release_manifest.json',
        code_git_base_commit=head,code_git_commit=head if committed else None,
        tasks_accepted={'rq4_stress_lead':True},acceptance_scope='USDT community concentration before retrospective ETH market-stress onsets',
        upload_files=records,blocked_upload_files=[],missing_files=[],remote_dependencies=dependencies,
        upload_performed=False,remote_deletions=0)
    json_write(ROOT/manifest['manifest_file'],manifest)
    json_write(ROOT/'data/hf_release_manifest.json',dict(manifest,manifest_file='data/hf_release_manifest.json'))
    print(f'RQ4 release prepared: {len(records)} records; upload not performed')


if __name__=='__main__':main()
