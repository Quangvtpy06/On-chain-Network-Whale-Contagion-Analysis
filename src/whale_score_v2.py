"""Versioned T12 activity cohort; retrospective labels never enter primary ranking."""
import json
import sys
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

from src.graph_config import ROOT, read_config, project_path, relative_path
from src.node_centrality import sha256, write_json
from src.whale_score import verify_inputs
from src.whale_score_design import build_cohort

CONFIG = ROOT / 'config/t12_v2.yaml'
INFRA = ['CEX', 'DEX', 'Bridge', 'Contract', 'Other', 'DeFi']
PRODUCTS = [f'{branch}/{name}.parquet' for branch in ['primary', 'retrospective']
    for name in ['cohort_members_daily', 'cohort_snapshot_daily', 'cohort_filter_sensitivity', 't12_design_validation']]
PRODUCTS += ['cohort_label_diagnostics.parquet', 'cohort_sensitivity_daily.parquet',
             'cohort_flows_daily.parquet', 'source_review_status.parquet']


@contextmanager
def scratch_directory(cache, prefix):
    # Ordinary inherited Windows ACLs; tempfile's private 0700 ACL can be
    # inaccessible to the sandbox's restricted token on this machine.
    path = cache/(prefix+uuid.uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        if not path.resolve().is_relative_to(cache.resolve()):raise ValueError('Unsafe cleanup')
        shutil.rmtree(path)


def settings():
    protocol = read_config(CONFIG)
    base = read_config(project_path(protocol['base_config']))
    return protocol, base


def closed_gate(reason):
    return dict(protocol_id=read_config(CONFIG)['protocol_id'],
        ready_for_cohort_whaleflow=False, ready_for_t14_t15=False,
        ready_for_individual_investor_inference=False, ready_for_rq3_pit_forecast=False,
        blocking_reasons=[reason])


def inputs(cfg, base):
    paths = [CONFIG, ROOT/'config/t12_design.yaml', ROOT/'src/whale_score_v2.py',
        ROOT/'scripts/run_t12_v2.py', ROOT/'scripts/validate_t12_v2.py',
        ROOT/'src/whale_score_design.py', ROOT/'src/whale_score_audit.py',
        ROOT/'src/secondary_labels.py', ROOT/'scripts/validate_t12_cohort.py',
        ROOT/'src/whale_score.py', ROOT/'src/node_centrality.py', ROOT/'src/graph_config.py',
        ROOT/'config/config.yaml', ROOT/'docs/T12_protocol_v2.md',
        project_path(cfg['data']['processed_t09_dir'])/'node_metrics_daily.parquet',
        project_path(cfg['data']['contract_status_parquet']),
        project_path(cfg['data']['processed_labels_parquet']),
        project_path(cfg['data']['daily_edges_parquet']), project_path(base['secondary_labels']),
        ROOT/'data/processed/t12/cohort_members_daily.parquet',
        ROOT/'data/processed/t12/t12_protocol_freeze.json',
        ROOT/'data/processed/t12/t12_cohort_review.json',
        ROOT/'data/processed/t12/t12_source_review_draft.parquet']
    return {relative_path(p): sha256(p) for p in paths}


def infrastructure(labels):
    return labels.entity_type.isin(INFRA) | labels.is_contract.fillna(False).astype(bool)


def compute(folder, cfg, protocol, base):
    folder.mkdir(parents=True, exist_ok=True)
    nodes = pd.read_parquet(project_path(cfg['data']['processed_t09_dir'])/'node_metrics_daily.parquet')
    labels = pd.read_parquet(project_path(cfg['data']['processed_labels_parquet']))
    contracts = pd.read_parquet(project_path(cfg['data']['contract_status_parquet']))
    secondary = pd.read_parquet(project_path(base['secondary_labels']))
    dates = pd.date_range(cfg['project']['start_date'], cfg['project']['end_date']).strftime('%Y-%m-%d').tolist()
    excluded = set(labels.loc[infrastructure(labels), 'address'])
    cohorts = {}
    for branch in ['primary', 'retrospective']:
        target = folder/branch; target.mkdir()
        opts = dict(base, protocol_id=protocol['protocol_id'], entity_label_policy=(
            protocol['primary_label_policy'] if branch == 'primary' else protocol['retrospective_scope']))
        frame = nodes if branch == 'primary' else nodes.loc[~nodes.address.isin(excluded)]
        # Filtering the node universe here precedes the forwarding quantile and z scores.
        # No retrospective address is presented as a historical contract or verified label.
        build_cohort(frame, contracts, secondary, dates, opts, target)
        cohorts[branch] = pd.read_parquet(target/'cohort_members_daily.parquet')
        snap = pd.read_parquet(target/'cohort_snapshot_daily.parquet').drop(columns='ready_for_cohort_whaleflow')
        snap['protocol_id'] = protocol['protocol_id']; snap['analysis_branch'] = branch
        snap.to_parquet(target/'cohort_snapshot_daily.parquet', index=False)
        print(f'V2 computed {branch}: {len(cohorts[branch])} member-days', flush=True)
    diagnostics = []; comparisons = []; flows = []
    label_lookup = labels.set_index('address')
    node_groups = dict(tuple(nodes.groupby('time_window', sort=True)))
    edges = pd.read_parquet(project_path(cfg['data']['daily_edges_parquet']))
    edge_groups = dict(tuple(edges.groupby('time_window', sort=True)))
    cex = set(labels.loc[labels.entity_type.eq('CEX') & ~labels.label_conflict_review.fillna(False).astype(bool), 'address'])
    groups = {b: dict(tuple(m.groupby('date'))) for b, m in cohorts.items()}
    for day in dates:
        populations = {}
        daily_nodes = node_groups.get(day, nodes.iloc[:0]).set_index('address')
        edge = edge_groups.get(day, edges.iloc[:0])
        for branch in cohorts:
            m = groups[branch].get(day, cohorts[branch].iloc[:0])
            selected = set(m.address); populations[branch] = selected
            tags = label_lookup.reindex(m.address)
            known = tags.is_entity_attributed.fillna(False).astype(bool)
            infra = infrastructure(tags)
            weights = m.value_30d.to_numpy(); total = float(weights.sum())
            def share(mask):
                return float(weights[np.asarray(mask, bool)].sum()/total) if total else np.nan
            today = daily_nodes.reindex(m.address)
            today_value = (today.in_strength_usdt.fillna(0)+today.out_strength_usdt.fillna(0)).to_numpy()
            current_total = float(today_value.sum())
            diagnostics.append(dict(date=day,analysis_branch=branch,n_selected=len(m),
                n_current_T07_attributed=int(known.sum()),n_current_T07_unattributed=int((~known).sum()),
                n_retrospective_infrastructure=int(infra.sum()),
                trailing_30d_endpoint_volume_usdt=total,
                retrospective_attributed_trailing_volume_share=share(known),
                retrospective_infrastructure_trailing_volume_share=share(infra),
                current_day_endpoint_volume_usdt=current_total,
                retrospective_attributed_current_volume_share=float(today_value[known.to_numpy()].sum()/current_total) if current_total else np.nan,
                interpretation='Current T07 attribution diagnostic; not as-of identity verification or true label recall'))
            a = edge.from_address.isin(selected); b = edge.to_address.isin(selected)
            # Current CEX identities are deliberately confined to descriptive sensitivity flows.
            to_cex = a & ~b & edge.to_address.isin(cex)
            from_cex = b & ~a & edge.from_address.isin(cex)
            cex_in = float(edge.loc[to_cex,'total_value'].sum())
            cex_out = float(edge.loc[from_cex,'total_value'].sum())
            flows.append(dict(date=day,analysis_branch=branch,
                cohort_inflow_usdt=float(edge.loc[~a & b,'total_value'].sum()),
                cohort_outflow_usdt=float(edge.loc[a & ~b,'total_value'].sum()),
                cohort_internal_usdt=float(edge.loc[a & b,'total_value'].sum()),
                cohort_to_current_cex_usdt=cex_in,current_cex_to_cohort_usdt=cex_out,
                net_to_current_cex_usdt=cex_in-cex_out,
                has_full_history=bool(len(m)),cex_endpoint_policy='retrospective_T07_not_PIT',
                permitted_use='descriptive_sensitivity_only_not_RQ3_PIT_forecast'))
        a,b = populations['primary'],populations['retrospective']
        comparisons.append(dict(date=day,n_primary=len(a),n_retrospective=len(b),
            n_overlap=len(a&b),n_removed=len(a-b),n_replacements=len(b-a),
            jaccard=len(a&b)/len(a|b) if a|b else np.nan))
    pd.DataFrame(diagnostics).to_parquet(folder/'cohort_label_diagnostics.parquet',index=False)
    pd.DataFrame(comparisons).to_parquet(folder/'cohort_sensitivity_daily.parquet',index=False)
    pd.DataFrame(flows).to_parquet(folder/'cohort_flows_daily.parquet',index=False)
    draft = pd.read_parquet(ROOT/'data/processed/t12/t12_source_review_draft.parquet')
    draft['v2_disposition'] = 'AI_lookup_only_identity_unverified_no_primary_label_change'
    draft.to_parquet(folder/'source_review_status.parquet',index=False)


def main():
    cfg = read_config(); protocol,base = settings(); folder = project_path(protocol['output_dir'])
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder/'t12_downstream_gate.json', closed_gate('V2 run in progress or interrupted'))
    freeze = folder/'t12_protocol_freeze.json'
    fingerprint = sha256(CONFIG)
    v1_freeze = json.loads((ROOT/'data/processed/t12/t12_protocol_freeze.json').read_text(encoding='utf-8'))
    if v1_freeze['settings_sha256'] != sha256(ROOT/'config/t12_design.yaml'):
        raise ValueError('V1 frozen thresholds changed')
    if protocol['regression_results_used_for_selection'] is not False:
        raise ValueError('Outcome-based selection is forbidden')
    if freeze.exists():
        if json.loads(freeze.read_text(encoding='utf-8'))['settings_sha256'] != fingerprint:
            raise ValueError('V2 frozen config changed; issue a new version')
    else:
        if any((ROOT/'data/processed/t15').rglob('*.parquet')):
            raise ValueError('Cannot issue a pre-T15 protocol after T15 outputs exist')
        write_json(freeze,dict(protocol_id=protocol['protocol_id'],settings_sha256=fingerprint,
            settings=protocol,base_settings_sha256=v1_freeze['settings_sha256'],
            issued_at=pd.Timestamp.now(tz='UTC').isoformat(),no_local_T15_parquet_at_initial_freeze=True,
            regression_outcomes_read=False,
            limitation='No local T15 output found; this does not certify external team members have not seen results.'))
    provenance,_ = verify_inputs(cfg)
    before = inputs(cfg,base)
    # Both full computations are isolated. Only successful products are promoted.
    cache = ROOT/'.cache'; cache.mkdir(exist_ok=True)
    with scratch_directory(cache, 't12_v2_') as scratch:
        scratch = Path(scratch)
        for name in ['run1','run2']:
            compute(scratch/name,cfg,protocol,base)
        hashes = {name:dict(run1=sha256(scratch/'run1'/name),run2=sha256(scratch/'run2'/name)) for name in PRODUCTS}
        if not all(v['run1']==v['run2'] for v in hashes.values()):
            raise ValueError('V2 non-reproducible outputs')
        if before != inputs(cfg,base): raise ValueError('V2 inputs changed during computation')
        for name in PRODUCTS:
            target = folder/name; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(scratch/'run1'/name,target)
    write_json(folder/'t12_reproducibility.json',dict(all_match=True,hashes=hashes))
    write_json(folder/'t12_summary.json',dict(protocol_id=protocol['protocol_id'],
        computation_complete=True,accepted=False,inputs=before,upstream=provenance,
        output_hashes={n:v['run1'] for n,v in hashes.items()},
        scope=protocol['primary_scope'],unknown_is_not_verified_individual=True))
    from scripts.validate_t12_v2 import validate
    validate()


if __name__ == '__main__': main()
