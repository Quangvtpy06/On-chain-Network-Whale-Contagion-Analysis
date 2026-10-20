"""Lập manifest bàn giao dataset; không copy dữ liệu, không tự upload.

Chỉ liệt kê artifact chuẩn đã được nghiệm thu. Test/cache và output stale bị loại.
"""
import hashlib
import json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]


def file_hash(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}


def main():
    config=yaml.safe_load((ROOT/'config/config.yaml').read_text(encoding='utf-8'))
    t07=read_json(ROOT/'data/processed/t07/t07_complete_summary.json')
    t08=read_json(ROOT/'data/processed/graphs/t08_summary.json')
    t09=read_json(ROOT/'data/processed/t09/t09_review.json')
    t10_settings=yaml.safe_load((ROOT/'config/t10.yaml').read_text(encoding='utf-8'))
    t10_dir=ROOT/t10_settings['output_dir']
    t10=read_json(t10_dir/'t10_summary.json')
    standard={
      't07': ['data/processed/t07/'+name for name in [
        't07_all_wallet_labels.parquet','t07_public_enriched_wallet_labels.parquet',
        't07_complete_wallet_labels.parquet','t07_contract_status.parquet',
        't07_complete_summary.json','t07_public_enrichment_summary.json']],
      't08': [config['data']['interim_raw_transfers'],'data/interim/usdt_transfers_netted.parquet']+['data/processed/graphs/'+name for name in [
        'dynamic_edges_daily.parquet','dynamic_edges_weekly.parquet',
        'graph_metrics_daily.parquet','graph_metrics_weekly.parquet','t08_validation.parquet',
        't08_acceptance_checks.parquet','t08_topology_comparison.parquet','t08_monthly_retention.parquet',
        't08_top10_days.parquet','t08_top20_nodes.parquet','t08_direction_samples.parquet',
        't08_multistep_cycle_audit.parquet','t08_summary.json','t08_reproducibility.json',
        't08_independent_review.json']],
      't09': ['data/processed/t09/'+name for name in [
        'node_metrics_daily.parquet','node_metrics_weekly.parquet',
        'snapshot_metrics_daily.parquet','snapshot_metrics_weekly.parquet','t09_summary.json']],
    }
    standard['t10']=[(t10_dir/name).relative_to(ROOT).as_posix() for name in [
        'node_metrics_daily.parquet','node_metrics_weekly.parquet',
        'snapshot_metrics_daily.parquet','snapshot_metrics_weekly.parquet',
        't10_validation.parquet','t10_sampling_quality.parquet',
        't10_summary.json','t10_reproducibility.json','t10_review.json']]
    accepted={'t07':t07.get('complete',False), 't08':t08.get('ready_for_t09_t12',False),
              't09':t09.get('ready_for_downstream',False)}
    t08_hashes=read_json(ROOT/'data/processed/graphs/t08_reproducibility.json').get('hashes',{})
    accepted['t08']=bool(accepted['t08'] and t08_hashes and all(
        (ROOT/'data/processed/graphs'/name).is_file() and
        file_hash(ROOT/'data/processed/graphs'/name)==hashes['run1']==hashes['run2']
        for name,hashes in t08_hashes.items()))
    raw_path=ROOT/config['data']['interim_raw_transfers']
    raw_sha256=t08.get('netting_results',{}).get('raw_sha256')
    accepted['t08']=bool(accepted['t08'] and raw_path.is_file() and raw_sha256 and
        file_hash(raw_path)==raw_sha256)
    t09_summary=read_json(ROOT/'data/processed/t09/t09_summary.json')
    t09_repro=read_json(ROOT/'data/processed/t09/t09_reproducibility.json')
    accepted['t09']=bool(accepted['t09'] and accepted['t08'] and
        t09_summary.get('ready_for_downstream') and t09_summary.get('is_complete_run') and
        file_hash(ROOT/'config/config.yaml')==t09_summary.get('config_sha256') and
        file_hash(ROOT/t09_summary.get('code_file','src/node_centrality.py'))==t09_summary.get('code_sha256') and
        t09_repro.get('all_match') and t09.get('reproducibility_pass') and
        len(t09.get('output_hashes',{}))==4 and all(
            (ROOT/'data/processed/t09'/name).is_file() and
            file_hash(ROOT/'data/processed/t09'/name)==expected and
            expected==t09_repro.get('hashes',{}).get(name,{}).get('run1')==t09_repro.get('hashes',{}).get(name,{}).get('run2')
            for name,expected in t09.get('output_hashes',{}).items()) and all(
            (ROOT/path).is_file() and file_hash(ROOT/path)==expected
            for path,expected in t09.get('input_hashes',{}).items()))
    t10_repro=read_json(t10_dir/'t10_reproducibility.json')
    t10_review=read_json(t10_dir/'t10_review.json')
    accepted['t10']=bool(accepted['t08'] and t10.get('ready_for_downstream') and
        t10.get('python_hash_seed')=='0' and
        t10_review.get('all_pass') and t10_repro.get('all_match') and
        t10_review.get('validator_sha256')==file_hash(ROOT/'scripts/validate_t10_current.py') and
        t10.get('config_sha256')==file_hash(ROOT/'config/config.yaml') and
        t10.get('settings_sha256')==file_hash(ROOT/'config/t10.yaml') and
        t10.get('code_sha256')==file_hash(ROOT/'src/heavy_graph_metrics.py') and
        len(t10_repro.get('hashes',{}))==6 and all(
            (t10_dir/name).is_file() and file_hash(t10_dir/name)==proof.get('run1')==proof.get('run2')
            for name,proof in t10_repro.get('hashes',{}).items()) and
        len(t10_review.get('output_hashes',{}))==6 and all(
            expected==t10_repro.get('hashes',{}).get(name,{}).get('run1')
            for name,expected in t10_review.get('output_hashes',{}).items()) and
        len(t10.get('inputs',{}))==4 and all(
            (ROOT/item['path']).is_file() and file_hash(ROOT/item['path'])==item['sha256']
            for item in t10.get('inputs',{}).values()))
    upload=[];blocked=[];missing=[]
    for task,files in standard.items():
        for rel in files:
            path=ROOT/rel
            if not path.is_file():
                missing.append(dict(task=task,path=rel));continue
            row=dict(task=task,path=rel,bytes=path.stat().st_size,sha256=file_hash(path))
            (upload if accepted[task] else blocked).append(row)
    for rel in ['config/config.yaml','config/t10.yaml','eth_stats_from_2025.csv']:
        path=ROOT/rel
        if path.is_file():
            upload.append(dict(task='shared',path=rel,bytes=path.stat().st_size,sha256=file_hash(path)))
    # Bằng chứng review có thể bàn giao ngay cả khi bảng chỉ số T09 bị chặn.
    for name in ['t09_review.json','t09_validation.parquet','t09_reproducibility.json']:
        rel='data/processed/t09/'+name
        path=ROOT/rel
        if path.is_file():
            upload.append(dict(task='t09_review_evidence',path=rel,bytes=path.stat().st_size,sha256=file_hash(path)))
    summary=dict(repo_id=config['huggingface']['repo_id'],repo_type='dataset',
        tasks_accepted=accepted,manifest_file='data/hf_release_manifest.json',
        upload_files=upload,blocked_upload_files=blocked,missing_files=missing,
        raw_input=dict(path=config['data']['interim_raw_transfers'],sha256=raw_sha256),
        excluded=['.cache/**','**/__pycache__/**','**/test_tmp*/**','**/repro_run*/**',
                  '**/*.csv except eth_stats_from_2025.csv','generated graph HTML/PNG'],
        upload_performed=False,
        note='Use exactly upload_files when publishing. Blocked tasks must be regenerated/reviewed before release. No automatic deletion of remote files.')
    destination=ROOT/'data/hf_release_manifest.json'
    destination.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(manifest='data/hf_release_manifest.json',upload_files=len(upload),
                         blocked_files=len(blocked),missing_files=len(missing),tasks_accepted=accepted),indent=2),flush=True)


if __name__=='__main__':
    main()
