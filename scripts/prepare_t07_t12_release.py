"""Scoped, hash-checked T07/T12 release; no rebuild or publication of other tasks."""
import json
import subprocess
from pathlib import Path

from prepare_hf_manifest import ROOT, file_hash, read_json


def require(condition,message):
    if not condition:raise ValueError(message)


def check_inputs(mapping):
    require(bool(mapping),'Missing provenance')
    for name,h in mapping.items():
        p=(ROOT/name).resolve()
        require(p.is_relative_to(ROOT.resolve()) and p.is_file() and file_hash(p)==h,'Changed input: '+name)


def repro(folder,name,count):
    proof=read_json(folder/name)
    require(proof.get('all_match') and len(proof.get('hashes',{}))==count,'Incomplete reproducibility: '+str(folder/name))
    for n,v in proof['hashes'].items():
        require(file_hash(folder/n)==v['run1']==v['run2'],'Changed reproduced artifact: '+n)


def main():
    history=ROOT/'data/processed/t07/cex_history';t12=ROOT/'data/processed/t12';v2=t12/'v2'
    hg=read_json(history/'t07_cex_history_gate.json');hr=read_json(history/'t07_cex_history_review.json')
    require(hr.get('all_pass') and hr.get('gate')==hg and hg.get('ready_for_t14_endpoint_lookup') and
        hg.get('approved_addresses')==306 and hg.get('pending_claims')==0,'CEX history is not fully reviewed for this release')
    check_inputs(hg['input_hashes']);repro(history,'t07_cex_history_reproducibility.json',8)
    for n,h in hg['output_hashes'].items():require(file_hash(history/n)==h,'Changed history output: '+n)
    raw=read_json(t12/'t12_summary.json');review=read_json(t12/'t12_review.json')
    audit=read_json(t12/'t12_audit_summary.json');design=read_json(t12/'t12_design_summary.json')
    cohort=read_json(t12/'t12_cohort_review.json')
    require(review.get('all_pass') and audit.get('audit_complete') and design.get('complete') and cohort.get('all_pass'),'Incomplete T12 validation')
    repro(t12,'t12_reproducibility.json',6);repro(t12,'t12_audit_reproducibility.json',11);repro(t12,'t12_design_reproducibility.json',7)
    for n,h in review['output_hashes'].items():require(file_hash(t12/n)==h,'Changed raw T12 output')
    mappings=[hg['input_hashes'],raw['inputs'],audit['inputs'],design['inputs'],cohort['input_hashes']]
    for m in mappings:check_inputs(m)
    require(cohort['gate']==read_json(t12/'t12_downstream_gate.json')==audit['downstream_gate'],'V1 gate mismatch')
    require(file_hash(t12/'t12_cohort_validation.parquet')==cohort['validation_sha256'] and
        file_hash(t12/'t12_cohort_review_queue.parquet')==cohort['queue_sha256'] and
        file_hash(t12/'t12_audit_summary.json')==design['current_audit_sha256'] and
        file_hash(t12/'t12_cohort_review.json')==design['cohort_validation_sha256'],'V1 evidence mismatch')
    vs=read_json(v2/'t12_summary.json');vg=read_json(v2/'t12_downstream_gate.json');va=read_json(v2/'t12_acceptance.json')
    require(vs.get('accepted') and va.get('all_pass') and va['gate']==vg and vg.get('ready_for_cohort_whaleflow'),'V2 not accepted')
    require(file_hash(v2/'t12_acceptance.json')==vs['acceptance_sha256'],'V2 acceptance changed')
    check_inputs(vg['input_hashes']);mappings.append(vg['input_hashes']);repro(v2,'t12_reproducibility.json',12)
    for n,h in vg['output_hashes'].items():require(file_hash(v2/n)==h,'Changed V2 output')
    require(file_hash(v2/'t12_validation.parquet')==vg['validation_sha256'] and
        file_hash(v2/'t12_controls.parquet')==vg['controls_sha256'],'Changed V2 checks')
    selected=set()
    for folder in [ROOT/'data/processed/t07',t12]:
        selected.update(p.relative_to(ROOT).as_posix() for p in folder.rglob('*') if p.is_file() and p.suffix in ['.parquet','.json'])
    configs=['config/config.yaml','config/t07_cex_history.yaml','config/t12.yaml','config/t12_audit.yaml','config/t12_design.yaml','config/t12_v2.yaml']
    selected.update(configs)
    uploads=[dict(task='t07_cex_history' if '/t07/' in n else 't12',path=n,sha256=file_hash(ROOT/n),bytes=(ROOT/n).stat().st_size) for n in sorted(selected)]
    dependencies={}
    for mapping in mappings+[raw.get('t08_inputs',{})]:
        for path,h in mapping.items():
            if path.startswith(('data/','market/')) and path not in selected:
                require(path not in dependencies or dependencies[path]==h,'Conflicting dependency hashes')
                dependencies[path]=h
    require(bool(dependencies),'No upstream dependencies bound')
    release=dict(repo_id='team-crypto/Market-data-crypto-project',repo_type='dataset',
        manifest_file='data/hf_t07_t12_release_manifest.json',
        code_repository='https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis',
        code_git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        tasks_accepted={'t07_cex_history':True,'t12_validated_exploration_and_v1':True,'t12_activity_cohort_v2':True},
        acceptance_scope='306 approved historical Ethereum CEX labels and validated T12 activity cohorts; not full T14/T15/RQ3 certification',
        downstream_eligibility=dict(t07_endpoint_lookup=True,cohort_whaleflow_v2=True,rq3_pit_forecast=False,
            t07_history_path=hg['history_path'],t12_cohort_path=vg['cohort_path']),
        upload_files=uploads,blocked_upload_files=[],missing_files=[],
        remote_dependencies=[dict(path=n,sha256=h) for n,h in sorted(dependencies.items())],
        upload_performed=False,remote_deletions=0,
        excluded=['temporary tests/fixtures/caches','CSV outputs','unreviewed outputs of other tasks'],
        note='Verify upstream files already on HF before commit; never replace another task through this scoped release.')
    destination=ROOT/release['manifest_file'];destination.write_text(json.dumps(release,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(manifest=release['manifest_file'],files=len(uploads),remote_dependencies=len(dependencies),code_git_commit=release['code_git_commit']),indent=2))


if __name__=='__main__':main()
