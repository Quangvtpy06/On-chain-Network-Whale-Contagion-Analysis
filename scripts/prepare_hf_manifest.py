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
    gate={}
    v2_gate={}
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
    t11_settings_path=ROOT/'config/t11.yaml'
    if t11_settings_path.is_file():
        t11_settings=yaml.safe_load(t11_settings_path.read_text(encoding='utf-8'))
        t11_dir=ROOT/t11_settings['output_dir']
        t11=read_json(t11_dir/'t11_summary.json')
        t11_repro=read_json(t11_dir/'t11_reproducibility.json')
        t11_review=read_json(t11_dir/'t11_review.json')
        standard['t11']=[(t11_dir/name).relative_to(ROOT).as_posix() for name in [
            'community_nodes_daily.parquet','community_nodes_weekly.parquet',
            'snapshot_metrics_daily.parquet','snapshot_metrics_weekly.parquet',
            't11_validation.parquet','top_communities_summary.parquet','rq4_daily_regimes.parquet','rq4_comparison.parquet',
            't11_summary.json','t11_reproducibility.json','t11_review.json']]
        standard['t11'] += ['data/figures/t11/'+name for name in [
            't11_modularity_timeseries.png','t11_concentration_timeseries.png',
            't11_rq4_stress_comparison.png','t11_community_map_2026-10-17.png']]
        accepted['t11']=bool(accepted['t08'] and t11.get('ready_for_downstream') and
            t11.get('independent_review_pass') and t11.get('is_complete_run') and t11.get('reproducibility_pass') and
            t11_repro.get('all_match') and t11_repro.get('separate_processes') and t11.get('python_hash_seed')=='0' and
            t11_review.get('all_pass') and t11_review.get('windows_checked')==749 and
            t11_review.get('validator_sha256')==file_hash(ROOT/'scripts/validate_t11_current.py') and
            len(t11.get('source_code_hashes',{}))==4 and all((ROOT/path).is_file() and file_hash(ROOT/path)==expected
                for path,expected in t11.get('source_code_hashes',{}).items()) and
            t11.get('config_sha256')==file_hash(ROOT/'config/config.yaml') and
            t11.get('settings_sha256')==file_hash(t11_settings_path) and
            t11.get('code_sha256')==file_hash(ROOT/'src/community_concentration.py') and
            len(t11_review.get('output_hashes',{}))==8 and all(t11_review['output_hashes'].get(name)==proof.get('run1')
                for name,proof in t11_repro.get('hashes',{}).items()) and
            len(t11_repro.get('hashes',{}))==8 and all(
                (t11_dir/name).is_file() and file_hash(t11_dir/name)==proof.get('run1')==proof.get('run2')
                for name,proof in t11_repro.get('hashes',{}).items()) and
            len(t11.get('inputs',{}))==4 and all(
                (ROOT/item['path']).is_file() and file_hash(ROOT/item['path'])==item['sha256']
                for item in t11.get('inputs',{}).values()))
    t12_settings_path=ROOT/'config/t12.yaml'
    if t12_settings_path.is_file():
        t12_settings=yaml.safe_load(t12_settings_path.read_text(encoding='utf-8'))
        t12_dir=ROOT/t12_settings['output_dir']
        t12=read_json(t12_dir/'t12_summary.json')
        t12_review=read_json(t12_dir/'t12_review.json')
        t12_repro=read_json(t12_dir/'t12_reproducibility.json')
        audit=read_json(t12_dir/'t12_audit_summary.json')
        audit_repro=read_json(t12_dir/'t12_audit_reproducibility.json')
        tests=read_json(t12_dir/'t12_tests.json')
        gate=read_json(t12_dir/'t12_downstream_gate.json')
        design=read_json(t12_dir/'t12_design_summary.json')
        design_repro=read_json(t12_dir/'t12_design_reproducibility.json')
        frozen=read_json(t12_dir/'t12_protocol_freeze.json')
        standard['t12']=[(t12_dir/name).relative_to(ROOT).as_posix() for name in [
            'whale_scores_daily.parquet','whale_scores_weekly.parquet',
            'snapshot_metrics_daily.parquet','snapshot_metrics_weekly.parquet',
            't12_standardization.parquet','t12_validation.parquet',
            't12_summary.json','t12_review.json','t12_reproducibility.json',
            'exploratory_scores_daily.parquet','exploratory_scores_weekly.parquet',
            't12_label_coverage.parquet','t12_transfer_coverage.parquet','t12_rank_sensitivity.parquet',
            't12_component_correlations.parquet','t12_top50_stability.parquet','t12_address_behavior.parquet',
            't12_behavior_sensitivity.parquet','t12_address_review.parquet','t12_audit_validation.parquet',
            't12_audit_summary.json','t12_audit_reproducibility.json','t12_tests.json','t12_downstream_gate.json']]
        standard['t12'] += [(t12_dir/name).relative_to(ROOT).as_posix() for name in [
            'cohort_members_daily.parquet','cohort_snapshot_daily.parquet','cohort_filter_sensitivity.parquet',
            'cex_coverage.parquet','cex_netflow_daily.parquet','cex_wallet_inventory.parquet',
            't12_design_validation.parquet','t12_design_summary.json','t12_design_reproducibility.json','t12_protocol_freeze.json',
            't12_cohort_validation.parquet','t12_cohort_review_queue.parquet','t12_cohort_review.json','t12_cohort_controls.json']]
        standard['t07'] += ['data/processed/t07/t07_label_review_candidates.parquet',
                            'data/processed/t07/t07_secondary_verified_labels.parquet']
        accepted['t12']=bool(accepted['t07'] and accepted['t09'] and
            t12.get('ready_for_exploration') and t12_review.get('all_pass') and
            t12.get('settings_sha256')==file_hash(t12_settings_path) and
            t12.get('code_sha256')==file_hash(ROOT/'src/whale_score.py') and
            t12_review.get('validator_sha256')==file_hash(ROOT/'scripts/validate_t12_current.py') and
            t12_repro.get('all_match') and len(t12_repro.get('hashes',{}))==6 and all(
                (t12_dir/name).is_file() and file_hash(t12_dir/name)==proof.get('run1')==proof.get('run2')
                for name,proof in t12_repro.get('hashes',{}).items()) and
            len(t12_review.get('output_hashes',{}))==6 and all(
                expected==t12_repro.get('hashes',{}).get(name,{}).get('run1')
                for name,expected in t12_review.get('output_hashes',{}).items()) and
            bool(t12.get('inputs')) and all((ROOT/path).is_file() and file_hash(ROOT/path)==expected
                for path,expected in t12.get('inputs',{}).items()))
        # Publishing exploratory results does not authorize investor/WhaleFlow inference.
        accepted['t12']=bool(accepted['t12'] and audit.get('audit_complete') and
            audit.get('ready_for_exploration') and audit_repro.get('all_match') and
            tests.get('passed') and tests.get('execution_scope')=='historical_before_source_cleanup' and
            tests.get('source_files_retained') is False and bool(tests.get('test_files')) and
            all(not (ROOT/path).exists() for path in tests.get('test_files',{})) and
            bool(audit.get('inputs')) and all((ROOT/path).is_file() and file_hash(ROOT/path)==expected
                for path,expected in audit.get('inputs',{}).items()) and
            len(audit_repro.get('hashes',{}))==11 and all(
                (t12_dir/name).is_file() and file_hash(t12_dir/name)==proof.get('run1')==proof.get('run2')
                for name,proof in audit_repro.get('hashes',{}).items()) and
            gate==audit.get('downstream_gate') and
            gate.get('ready_for_t14_t15')==t12.get('ready_for_t14_t15'))
        accepted['t12']=bool(accepted['t12'] and design.get('complete') and design_repro.get('all_match') and
            frozen.get('settings_sha256')==file_hash(ROOT/'config/t12_design.yaml') and
            design.get('current_audit_sha256')==file_hash(t12_dir/'t12_audit_summary.json') and
            bool(design.get('inputs')) and all((ROOT/path).is_file() and file_hash(ROOT/path)==expected
                for path,expected in design.get('inputs',{}).items()) and
            len(design_repro.get('hashes',{}))==7 and all((t12_dir/name).is_file() and
                file_hash(t12_dir/name)==proof.get('run1')==proof.get('run2')
                for name,proof in design_repro.get('hashes',{}).items()))
        cohort_review=read_json(t12_dir/'t12_cohort_review.json')
        accepted['t12']=bool(accepted['t12'] and cohort_review.get('all_pass') and
            cohort_review.get('gate')==gate and
            gate.get('acceptance_validator_sha256')==file_hash(ROOT/'scripts/validate_t12_cohort.py') and
            design.get('cohort_validation_sha256')==file_hash(t12_dir/'t12_cohort_review.json') and
            bool(cohort_review.get('input_hashes')) and all((ROOT/path).is_file() and
                file_hash(ROOT/path)==expected for path,expected in cohort_review.get('input_hashes',{}).items()) and
            all((t12_dir/name).is_file() and file_hash(t12_dir/name)==expected
                for name,expected in cohort_review.get('output_hashes',{}).items()) and
            file_hash(t12_dir/'t12_cohort_validation.parquet')==cohort_review.get('validation_sha256') and
            file_hash(t12_dir/'t12_cohort_review_queue.parquet')==cohort_review.get('queue_sha256'))
    v2_dir=ROOT/'data/processed/t12/v2'
    if (v2_dir/'t12_summary.json').exists():
        v2=read_json(v2_dir/'t12_summary.json')
        v2_gate=read_json(v2_dir/'t12_downstream_gate.json')
        v2_accept=read_json(v2_dir/'t12_acceptance.json')
        v2_repro=read_json(v2_dir/'t12_reproducibility.json')
        v2_freeze=read_json(v2_dir/'t12_protocol_freeze.json')
        v2_products=[f'{branch}/{name}.parquet' for branch in ['primary','retrospective'] for name in [
            'cohort_members_daily','cohort_snapshot_daily','cohort_filter_sensitivity','t12_design_validation']]
        v2_products+=['cohort_label_diagnostics.parquet','cohort_sensitivity_daily.parquet',
            'cohort_flows_daily.parquet','source_review_status.parquet']
        standard['t12_v2']=[(v2_dir/n).relative_to(ROOT).as_posix() for n in v2_products+[
            't12_summary.json','t12_acceptance.json','t12_reproducibility.json',
            't12_protocol_freeze.json','t12_downstream_gate.json','t12_validation.parquet','t12_controls.parquet',
            't12_integrity_control.json']]
        accepted['t12_v2']=bool(accepted.get('t12') and v2.get('accepted') and
            v2_accept.get('all_pass') and v2_accept.get('gate')==v2_gate and
            v2.get('acceptance_sha256')==file_hash(v2_dir/'t12_acceptance.json') and
            v2_gate.get('protocol_id')=='t12_unidentified_activity_v2' and
            v2_gate.get('ready_for_cohort_whaleflow') and
            v2_freeze.get('settings_sha256')==file_hash(ROOT/'config/t12_v2.yaml') and
            v2_gate.get('validator_sha256')==file_hash(ROOT/'scripts/validate_t12_v2.py') and
            bool(v2.get('inputs')) and v2.get('inputs')==v2_gate.get('input_hashes') and
            all((ROOT/p).is_file() and file_hash(ROOT/p)==h for p,h in v2['inputs'].items()) and
            v2_repro.get('all_match') and set(v2_repro.get('hashes',{}))==set(v2_products) and
            all((v2_dir/n).is_file() and file_hash(v2_dir/n)==v2_repro['hashes'][n].get('run1')==
                v2_repro['hashes'][n].get('run2')==v2_gate.get('output_hashes',{}).get(n) for n in v2_products) and
            file_hash(v2_dir/'t12_validation.parquet')==v2_gate.get('validation_sha256') and
            file_hash(v2_dir/'t12_controls.parquet')==v2_gate.get('controls_sha256'))
    t14_settings_path=ROOT/'config/t14.yaml'
    if t14_settings_path.is_file():
        t14_settings=yaml.safe_load(t14_settings_path.read_text(encoding='utf-8'))
        t14_dir=ROOT/t14_settings['output_dir']
        t14=read_json(t14_dir/'t14_summary.json')
        t14_repro=read_json(t14_dir/'t14_reproducibility.json')
        standard['t14']=[(t14_dir/name).relative_to(ROOT).as_posix() for name in [
            't14_features_daily.parquet','t14_validation.parquet','t14_summary.json','t14_reproducibility.json']]
        # Cohort WhaleFlow columns are exploratory while the T12 gate is closed; see t14_summary.json.
        accepted['t14']=bool(accepted.get('t12') and t14.get('validation_passed') and t14.get('reproducible') and
            t14_repro.get('all_match') and t14.get('settings_sha256')==file_hash(t14_settings_path) and
            bool(t14.get('code_sha256')) and all((ROOT/path).is_file() and file_hash(ROOT/path)==expected
                for path,expected in t14.get('code_sha256',{}).items()) and
            len(t14_repro.get('hashes',{}))==1 and all(
                (t14_dir/name).is_file() and file_hash(t14_dir/name)==proof.get('run1')==proof.get('run2')
                for name,proof in t14_repro.get('hashes',{}).items()))
    upload=[];blocked=[];missing=[]
    for task,files in standard.items():
        for rel in files:
            path=ROOT/rel
            if not path.is_file():
                missing.append(dict(task=task,path=rel));continue
            row=dict(task=task,path=rel,bytes=path.stat().st_size,sha256=file_hash(path))
            (upload if accepted[task] else blocked).append(row)
    for rel in ['config/config.yaml','config/t10.yaml','config/t11.yaml','config/t12.yaml','config/t12_audit.yaml','config/t12_design.yaml','config/t12_v2.yaml','config/t14.yaml','eth_stats_from_2025.csv']:
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
        acceptance_scope={'t12':'V1 unchanged; exploration and lagged-cohort prototype',
                          't12_v2':'Unidentified high-activity cohort only; retrospective sensitivity and ownership limits explicit'},
        downstream_eligibility=dict(cohort_whaleflow=bool(accepted.get('t12_v2') and v2_gate.get('ready_for_cohort_whaleflow')),
            cohort_protocol_id=v2_gate.get('protocol_id') if accepted.get('t12_v2') else None,
            cohort_path=v2_gate.get('cohort_path') if accepted.get('t12_v2') else None,
            t14_independent_branches_allowed=['cex_netflow','lagged_large_transfer_events','network_concentration'],
            rq3_cex_pit_forecast=False),
        upload_files=upload,blocked_upload_files=blocked,missing_files=missing,
        raw_input=dict(path=config['data']['interim_raw_transfers'],sha256=raw_sha256),
        excluded=['.cache/**','**/__pycache__/**','**/test_tmp*/**','**/repro_run*/**',
                  '**/*.csv except eth_stats_from_2025.csv','generated graph HTML/PNG except four canonical T11 PNGs'],
        upload_performed=False,
        note='Use exactly upload_files when publishing. Blocked tasks must be regenerated/reviewed before release. No automatic deletion of remote files.')
    destination=ROOT/'data/hf_release_manifest.json'
    destination.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(manifest='data/hf_release_manifest.json',upload_files=len(upload),
                         blocked_files=len(blocked),missing_files=len(missing),tasks_accepted=accepted),indent=2),flush=True)


if __name__=='__main__':
    main()
