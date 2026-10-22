"""Independent real-data acceptance for T12 v2's limited activity-cohort scope."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.graph_config import ROOT, read_config, project_path, relative_path
from src.node_centrality import sha256, write_json
from src.whale_score_v2 import CONFIG, PRODUCTS, settings, inputs, infrastructure, closed_gate, scratch_directory
from scripts.validate_t12_cohort import independent_days, reference_scores


def controls(nodes, contracts, secondary, dates, base, cache):
    from src.whale_score_design import build_cohort
    results = []
    for name, population in [
        ('empty',pd.DataFrame(dict(value=[],weighted_degree=[],pagerank=[]))),
        ('single_std_zero',pd.DataFrame(dict(value=[10.],weighted_degree=[2.],pagerank=[1.]))),
        ('ties_std_zero',pd.DataFrame(dict(value=[10.,10.],weighted_degree=[2.,2.],pagerank=[.5,.5]))),
    ]:
        actual = reference_scores(population)
        if not np.array_equal(actual,np.zeros(len(population))):raise ValueError(name)
        results.append(dict(control=name,status='PASS'))
    # An analytic two-node result anchors log transforms + population ddof=0.
    p = pd.DataFrame(dict(value=[0.,3.],weighted_degree=[0.,3.],pagerank=[.25,.75]))
    if not np.allclose(reference_scores(p),[-3.,3.]):raise ValueError('Analytic z score control failed')
    results.append(dict(control='analytic_two_node_population_z',status='PASS'))
    short = dates[:base['minimum_history_days']+1]
    last = short[-1]
    altered = nodes.copy()
    columns = ['in_strength_usdt','out_strength_usdt','weighted_degree_tx','pagerank']
    altered.loc[altered.time_window.ge(last),columns] *= 13.
    with scratch_directory(cache,'t12_v2_controls_') as tmp:
        tmp = Path(tmp)
        for name,source in [('original',nodes),('future_mutation',altered)]:
            target=tmp/name;target.mkdir()
            build_cohort(source,contracts,secondary,short,base,target)
        a=pd.read_parquet(tmp/'original/cohort_members_daily.parquet')
        b=pd.read_parquet(tmp/'future_mutation/cohort_members_daily.parquet')
        if not a.equals(b):raise ValueError('Prediction-day/future mutation affected selection')
    results.append(dict(control='production_prediction_day_and_future_mutation',status='PASS',prediction_day=last))
    return results


def validate():
    cfg=read_config();protocol,base=settings();folder=project_path(protocol['output_dir'])
    # This gate is computed anew. Any exception leaves a closed gate on disk.
    write_json(folder/'t12_downstream_gate.json',closed_gate('V2 acceptance in progress or interrupted'))
    summary=json.loads((folder/'t12_summary.json').read_text(encoding='utf-8'))
    hashes=inputs(cfg,base)
    if summary['inputs']!=hashes:raise ValueError('V2 inputs/code changed; recompute both runs')
    freeze=json.loads((folder/'t12_protocol_freeze.json').read_text(encoding='utf-8'))
    if freeze['settings_sha256']!=sha256(CONFIG) or freeze['base_settings_sha256']!=sha256(ROOT/'config/t12_design.yaml'):
        raise ValueError('Frozen v1/v2 configuration mismatch')
    if freeze.get('regression_outcomes_read') is not False:raise ValueError('Missing pre-T15 declaration')
    proof=json.loads((folder/'t12_reproducibility.json').read_text(encoding='utf-8'))
    if not proof.get('all_match') or set(proof['hashes'])!=set(PRODUCTS):raise ValueError('Missing full reproducibility proof')
    for name in PRODUCTS:
        record=proof['hashes'][name]
        if sha256(folder/name)!=record['run1'] or record['run1']!=record['run2']:
            raise ValueError(f'V2 output hash mismatch: {name}')
    nodes=pd.read_parquet(project_path(cfg['data']['processed_t09_dir'])/'node_metrics_daily.parquet')
    contracts=pd.read_parquet(project_path(cfg['data']['contract_status_parquet']))
    secondary=pd.read_parquet(project_path(base['secondary_labels']))
    labels=pd.read_parquet(project_path(cfg['data']['processed_labels_parquet']))
    dates=pd.date_range(cfg['project']['start_date'],cfg['project']['end_date']).strftime('%Y-%m-%d').tolist()
    excluded=set(labels.loc[infrastructure(labels),'address'])
    checks=[];members={}
    for branch in ['primary','retrospective']:
        m=pd.read_parquet(folder/branch/'cohort_members_daily.parquet');members[branch]=m
        if m.duplicated(['date','address']).any() or not m.date.isin(dates).all():raise ValueError('Duplicate/out-of-calendar membership')
        opts=dict(base,protocol_id=protocol['protocol_id'])
        source=nodes if branch=='primary' else nodes.loc[~nodes.address.isin(excluded)]
        c=independent_days(source,m,contracts,secondary,opts,dates)
        c['analysis_branch']=branch;checks.append(c)
        s=pd.read_parquet(folder/branch/'cohort_snapshot_daily.parquet')
        if s.date.tolist()!=dates or not np.array_equal(s.n_selected,c.n_observed):raise ValueError('Incomplete snapshot calendar')
        if not c.status.eq('PASS').all():raise ValueError(f'Independent {branch} cohort mismatch')
    checks=pd.concat(checks,ignore_index=True)
    primary=members['primary'];retro=members['retrospective']
    original=pd.read_parquet(ROOT/'data/processed/t12/cohort_members_daily.parquet')
    exact=['date','address','cohort_rank','information_cutoff','window_start']
    numeric=['score','value_30d','large_edge_tx_30d','pagerank_calendar_mean_30d','net_to_gross_ratio_30d']
    if not primary[exact].equals(original[exact]) or not np.allclose(primary[numeric],original[numeric],rtol=1e-10,atol=1e-7):
        raise ValueError('V2 unexpectedly changed frozen primary scoring/membership')
    if set(retro.address)&excluded:raise ValueError('Retrospective branch still contains static infrastructure')
    diag=pd.read_parquet(folder/'cohort_label_diagnostics.parquet')
    comp=pd.read_parquet(folder/'cohort_sensitivity_daily.parquet')
    flows=pd.read_parquet(folder/'cohort_flows_daily.parquet')
    tagged=primary.merge(labels[['address','entity_type','is_contract','is_entity_attributed']],on='address',validate='many_to_one')
    infra=infrastructure(tagged)
    if len(diag)!=2*len(dates) or len(flows)!=2*len(dates) or comp.date.tolist()!=dates:raise ValueError('Incomplete diagnostic calendar')
    if diag.duplicated(['date','analysis_branch']).any() or flows.duplicated(['date','analysis_branch']).any():raise ValueError('Duplicate diagnostics')
    if not np.allclose(flows.net_to_current_cex_usdt,flows.cohort_to_current_cex_usdt-flows.current_cex_to_cohort_usdt):
        raise ValueError('Descriptive CEX flow sign mismatch')
    for b,m in members.items():
        lookup={d:set(g.address) for d,g in m.groupby('date')}
        d=diag.loc[diag.analysis_branch.eq(b)].set_index('date')
        if not np.array_equal(d.n_selected,[len(lookup.get(t,set())) for t in dates]):raise ValueError('Diagnostic member counts mismatch')
    pa={d:set(g.address) for d,g in primary.groupby('date')}
    ra={d:set(g.address) for d,g in retro.groupby('date')}
    for row in comp.itertuples():
        a,b=pa.get(row.date,set()),ra.get(row.date,set())
        if (row.n_overlap,row.n_removed,row.n_replacements)!=(len(a&b),len(a-b),len(b-a)):
            raise ValueError('Sensitivity membership reconciliation failed')
        if a|b and not np.isclose(row.jaccard,len(a&b)/len(a|b)):raise ValueError('Jaccard mismatch')
    # Independent flow conservation: cohort boundary net equals summed node strengths.
    # This uses node metrics rather than the production edge masks.
    by_day=dict(tuple(nodes.groupby('time_window')))
    for row in flows.itertuples():
        ids=(pa if row.analysis_branch=='primary' else ra).get(row.date,set())
        daily=by_day.get(row.date,nodes.iloc[:0]);daily=daily.loc[daily.address.isin(ids)]
        net=float(daily.in_strength_usdt.sum()-daily.out_strength_usdt.sum())
        if not np.isclose(net,row.cohort_inflow_usdt-row.cohort_outflow_usdt,rtol=1e-10,atol=.01):
            raise ValueError('Cohort boundary flow does not reconcile with T09 node net')
    source=pd.read_parquet(folder/'source_review_status.parquet')
    if len(source)!=40 or source.address.duplicated().any():raise ValueError('Incomplete source review handoff')
    if not source.source_url.fillna('').str.startswith('https://').all() or not source.evidence_note.fillna('').str.strip().ne('').all():
        raise ValueError('Missing source lookup evidence')
    # AI findings were never promoted to verified labels or historical evidence.
    if source[['human_verified','approved_for_t07','approved_for_pit']].any().any():raise ValueError('Source draft contains approvals; use T07 workflow')
    cache=ROOT/'.cache';cache.mkdir(exist_ok=True)
    control_results=controls(nodes,contracts,secondary,dates,dict(base,protocol_id=protocol['protocol_id']),cache)
    # Negative control: corrupt a real membership score; independent reference must reject it.
    day=dates[base['minimum_history_days']];bad=primary.loc[primary.date.eq(day)].copy()
    bad.loc[bad.index[0],'score']+=1.
    trial=independent_days(nodes,bad,contracts,secondary,dict(base,protocol_id=protocol['protocol_id']),dates[:base['minimum_history_days']+1])
    if trial.loc[trial.date.eq(day),'status'].iloc[0]!='FAIL':raise ValueError('Corrupted score not detected')
    control_results.append(dict(control='independent_reference_rejects_corrupted_real_score',status='PASS'))
    if inputs(cfg,base)!=hashes:raise ValueError('Inputs changed during acceptance')
    checks.to_parquet(folder/'t12_validation.parquet',index=False)
    pd.DataFrame(control_results).to_parquet(folder/'t12_controls.parquet',index=False)
    current=tagged.is_entity_attributed.fillna(False).astype(bool)
    weights=tagged.value_30d
    full=comp.loc[comp.n_primary.gt(0)]
    pivot=flows.pivot(index='date',columns='analysis_branch',values='net_to_current_cex_usdt').loc[full.date]
    metrics=dict(days_checked=len(dates),branch_days_checked=len(checks),primary_member_days=len(primary),
        retrospective_member_days=len(retro),max_score_error=float(checks.max_score_error.max()),
        retrospective_infrastructure_addresses=int(tagged.loc[infra,'address'].nunique()),
        retrospective_infrastructure_member_days=int(infra.sum()),
        attributed_trailing_endpoint_volume_share=float(weights.loc[current].sum()/weights.sum()),
        infrastructure_trailing_endpoint_volume_share=float(weights.loc[infra].sum()/weights.sum()),
        trailing_volume_denominator='Sum of rolling 30d node endpoint volumes across member-days; overlapping windows repeat volume, not unique USDT',
        median_primary_adjacent_jaccard=float(pd.read_parquet(folder/'primary/cohort_snapshot_daily.parquet').jaccard_previous.median()),
        median_retrospective_adjacent_jaccard=float(pd.read_parquet(folder/'retrospective/cohort_snapshot_daily.parquet').jaccard_previous.median()),
        median_between_branch_jaccard=float(full.jaccard.median()),
        total_replacements=int(full.n_replacements.sum()),
        descriptive_net_cex_flow_correlation=float(pivot.primary.corr(pivot.retrospective)),
        descriptive_net_cex_flow_mean_absolute_difference_usdt=float((pivot.primary-pivot.retrospective).abs().mean()),
        source_lookup_rows=40,pending_human_identity_review=int((~source.human_verified).sum()))
    gate=dict(protocol_id=protocol['protocol_id'],ready_for_cohort_whaleflow=True,
        ready_for_t14_t15=False,ready_for_individual_investor_inference=False,ready_for_rq3_pit_forecast=False,
        ready_for_descriptive_retrospective_sensitivity=True,
        eligibility_scope=protocol['primary_scope'],
        cohort_path=relative_path(folder/'primary/cohort_members_daily.parquet'),
        cohort_sha256=sha256(folder/'primary/cohort_members_daily.parquet'),
        retrospective_cohort_path=relative_path(folder/'retrospective/cohort_members_daily.parquet'),
        required_downstream_checks=['Revalidate input/output hashes using scripts/validate_t12_v2.py',
            'Bind this protocol_id and cohort_path; do not read v1 cohort by default',
            'Independently certify CEX endpoint labels as-of cutoff before any RQ3 PIT forecast',
            'Call the cohort unidentified high-activity addresses; no individual ownership inference'],
        blocking_reasons=[],nonblocking_limitations=[
            'Unknown ownership is allowed, not verified non-infrastructure or individual identity',
            'Retrospective infrastructure remains in primary when not known at cutoff',
            'AI source lookup is not human review; pending identity reviews are reported',
            'Current CEX endpoint flow outputs are retrospective descriptive sensitivity only',
            'Only transfers >=500000 USDT; frequency and centrality describe this truncated network'],
        validator=relative_path(Path(__file__)),validator_sha256=sha256(Path(__file__)),
        config_sha256=sha256(CONFIG),input_hashes=hashes,
        output_hashes={n:sha256(folder/n) for n in PRODUCTS},
        validation_sha256=sha256(folder/'t12_validation.parquet'),controls_sha256=sha256(folder/'t12_controls.parquet'))
    write_json(folder/'t12_acceptance.json',dict(all_pass=True,scope=protocol['primary_scope'],metrics=metrics,
        controls=control_results,gate=gate))
    summary.update(accepted=True,metrics=metrics,acceptance_sha256=sha256(folder/'t12_acceptance.json'))
    write_json(folder/'t12_summary.json',summary)
    write_json(folder/'t12_downstream_gate.json',gate)
    print(json.dumps(dict(accepted=True,metrics=metrics,ready_for_cohort_whaleflow=True,
        ready_for_rq3_pit_forecast=False),indent=2),flush=True)


if __name__=='__main__':validate()
