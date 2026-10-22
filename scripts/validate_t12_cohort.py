"""Independent real-data cohort validation and fail-closed T12 acceptance gate.

Does not assign identities, approve AI findings, change the frozen protocol or
read T15 outcomes. Human source review is a separate input.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.graph_config import ROOT, read_config, project_path, relative_path
from src.node_centrality import sha256, write_json

DESIGN_FILES = ['cohort_members_daily.parquet', 'cohort_snapshot_daily.parquet',
    'cohort_filter_sensitivity.parquet', 'cex_coverage.parquet', 'cex_netflow_daily.parquet',
    'cex_wallet_inventory.parquet', 't12_design_validation.parquet']


def reference_scores(population):
    """Population moments via math.fsum, independent of production z_matrix."""
    values = np.column_stack([np.log1p(population.value),
        np.log1p(population.weighted_degree),
        np.log(np.maximum(population.pagerank, np.finfo(float).tiny))])
    scores = np.zeros(len(values))
    for column in values.T:
        mean = math.fsum(column) / len(column) if len(column) else 0.0
        sd = math.sqrt(math.fsum((float(v)-mean)**2 for v in column) / len(column)) if len(column) else 0.0
        if sd > 0:
            scores += (column-mean)/sd
    return scores


def independent_days(nodes, members, contracts, secondary, settings, dates):
    groups = {d:g for d,g in nodes.groupby('time_window', sort=True)}
    selected = {d:g.sort_values('cohort_rank') for d,g in members.groupby('date')}
    creation = pd.to_datetime(contracts.set_index('address').first_contract_timestamp, utc=True)
    rows = []
    for i, day in enumerate(dates):
        t = pd.Timestamp(day, tz='UTC'); start = t-pd.Timedelta(days=settings['lookback_days'])
        observed = selected.get(day, members.iloc[:0])
        if i < settings['minimum_history_days']:
            rows.append(dict(date=day,status='PASS' if observed.empty else 'FAIL',
                n_reference=0,n_observed=len(observed),max_score_error=0.0))
            continue
        history = [groups[d] for d in dates[max(0,i-settings['lookback_days']):i] if d in groups]
        source = pd.concat(history)
        p = source.groupby('address',sort=True)[['in_strength_usdt','out_strength_usdt','weighted_degree_tx','pagerank']].sum()
        p = p.loc[p.weighted_degree_tx.gt(.5)].copy()
        exclusion = set(creation.index[creation.lt(t)]) | {'0x'+'0'*40}
        if not secondary.empty:
            available = secondary.verification_status.eq('human_verified') & pd.to_datetime(secondary.label_available_at,utc=True).lt(t) & pd.to_datetime(secondary.effective_from,utc=True).lt(t)
            exclusion |= set(secondary.loc[available & secondary.entity_type.isin(['CEX','DEX','Bridge','Contract','Other']), 'address'])
        p = p.loc[~p.index.isin(exclusion)]
        p['value'] = p.in_strength_usdt+p.out_strength_usdt
        p['weighted_degree'] = p.weighted_degree_tx
        p['pagerank'] /= settings['lookback_days']
        p['ratio'] = (p.in_strength_usdt-p.out_strength_usdt).abs()/p.value.where(p.value.gt(0))
        p['ratio'] = p.ratio.fillna(0)
        threshold = max(settings['minimum_large_edge_transactions'],p.weighted_degree.quantile(settings['frequency_quantile'])) if len(p) else np.inf
        p = p.loc[~(p.ratio.le(settings['forwarding_net_ratio']) & p.weighted_degree.ge(threshold))].copy()
        p['score'] = reference_scores(p)
        expected = p.reset_index().sort_values(['score','address'],ascending=[False,True]).head(settings['cohort_size'])
        ok = observed.address.tolist()==expected.address.tolist() and observed.cohort_rank.tolist()==list(range(1,len(expected)+1))
        error = float(np.max(abs(observed.score.to_numpy()-expected.score.to_numpy()))) if ok and len(expected) else (0.0 if ok else float('inf'))
        if ok:
            ok &= bool(np.allclose(observed.value_30d,expected.value,rtol=1e-10,atol=1e-4))
            ok &= bool(np.allclose(observed.large_edge_tx_30d,expected.weighted_degree,rtol=0,atol=1e-6))
            ok &= bool(np.allclose(observed.pagerank_calendar_mean_30d,expected.pagerank,rtol=1e-8,atol=1e-12))
            ok &= bool(np.allclose(observed.net_to_gross_ratio_30d,expected.ratio,rtol=1e-8,atol=1e-10))
            ok &= bool(observed.information_cutoff.eq((t-pd.Timedelta(days=1)).strftime('%Y-%m-%d')).all())
            ok &= bool(observed.window_start.eq(start.strftime('%Y-%m-%d')).all())
            ok &= bool(observed.protocol_id.eq(settings['protocol_id']).all()) and error<=1e-7
        rows.append(dict(date=day,status='PASS' if ok else 'FAIL',n_reference=len(expected),
            n_observed=len(observed),max_score_error=error if np.isfinite(error) else None))
        if (i+1)%100==0: print(f'T12 independent trailing-window check {i+1}/{len(dates)}',flush=True)
    return pd.DataFrame(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--human-review',type=Path,help='Completed source review Parquet, never generated by AI')
    args=parser.parse_args()
    cfg=read_config();settings=read_config(ROOT/'config/t12_design.yaml');folder=project_path(settings['output_dir'])
    gate_path=folder/'t12_downstream_gate.json'
    previous=json.loads(gate_path.read_text(encoding='utf-8'))
    # Invalidate first: a failed rerun must not leave an old open gate.
    previous.update(ready_for_t14_t15=False,ready_for_cohort_whaleflow=False,
        blocking_reasons=['Cohort acceptance validation in progress or interrupted.'])
    write_json(gate_path,previous)
    design=json.loads((folder/'t12_design_summary.json').read_text(encoding='utf-8'))
    proof=json.loads((folder/'t12_design_reproducibility.json').read_text(encoding='utf-8'))
    source_paths=[ROOT/'config/t12_design.yaml',Path(__file__),ROOT/'src/whale_score_design.py',
        project_path(cfg['data']['processed_t09_dir'])/'node_metrics_daily.parquet',
        project_path(cfg['data']['contract_status_parquet']),project_path(cfg['data']['processed_labels_parquet']),
        project_path(settings['secondary_labels']),folder/'t12_address_review.parquet']
    source_hashes={relative_path(p):sha256(p) for p in source_paths}
    frozen=json.loads((folder/'t12_protocol_freeze.json').read_text(encoding='utf-8'))
    if frozen['settings_sha256']!=sha256(ROOT/'config/t12_design.yaml') or settings.get('regression_results_used_for_selection') is not False:
        raise ValueError('Frozen pre-T15 protocol does not match')
    if not design.get('complete') or not proof.get('all_match'):
        raise ValueError('Current design calculation/reproducibility not complete')
    for name in DESIGN_FILES:
        p=proof['hashes'][name]
        if sha256(folder/name)!=p['run1'] or p['run1']!=p['run2']:
            raise ValueError(f'Design artifact changed: {name}')
    if any(sha256(project_path(p))!=h for p,h in design['inputs'].items()):
        raise ValueError('Design source changed; rerun design before validating cohort')
    nodes=pd.read_parquet(source_paths[3]);contracts=pd.read_parquet(source_paths[4]);labels=pd.read_parquet(source_paths[5])
    secondary=pd.read_parquet(source_paths[6]);audit_review=pd.read_parquet(source_paths[7])
    members=pd.read_parquet(folder/'cohort_members_daily.parquet')
    if members.duplicated(['date','address']).any():raise ValueError('Duplicate cohort member')
    dates=pd.date_range(cfg['project']['start_date'],cfg['project']['end_date']).strftime('%Y-%m-%d').tolist()
    if not members.date.isin(dates).all():raise ValueError('Cohort date outside calendar')
    checks=independent_days(nodes,members,contracts,secondary,settings,dates)
    checks.to_parquet(folder/'t12_cohort_validation.parquet',index=False)
    # Diagnostic only: static T07 labels are not silently introduced into PIT ranking.
    tagged=members.merge(labels[['address','entity_type','entity_name','is_contract','source_url']],on='address',how='left',validate='many_to_one')
    infra=tagged.entity_type.isin(['CEX','DEX','Bridge','Contract','Other','DeFi']) | tagged.is_contract.fillna(False)
    profile=tagged.groupby('address',as_index=False).agg(cohort_days=('date','size'),
        mean_rank=('cohort_rank','mean'),top10_days=('cohort_rank',lambda s:int(s.le(10).sum())),
        trailing_volume_usdt=('value_30d','sum'),entity_type=('entity_type','first'),
        entity_name=('entity_name','first'),source_url=('source_url','first'))
    top=profile.sort_values(['top10_days','cohort_days','mean_rank','address'],ascending=[False,False,True,True]).head(20)
    required=sorted(set(audit_review.address)|set(top.address))
    queue=pd.DataFrame({'address':required}).merge(profile,on='address',how='left')
    queue['in_audit_top20']=queue.address.isin(audit_review.address)
    queue['in_cohort_top20']=queue.address.isin(top.address)
    fallback=dict(zip(audit_review.address,audit_review.source_url))
    queue['source_url']=[v if isinstance(v,str) and v.strip() else fallback.get(a,f'https://etherscan.io/address/{a}') for a,v in zip(queue.address,queue.source_url)]
    for c in ['reviewed_by','reviewed_at','review_decision','review_note']:queue[c]=''
    queue['source_opened_by_human']=False
    queue.to_parquet(folder/'t12_cohort_review_queue.parquet',index=False)
    reviewed=set();human_infrastructure=set();review_hash=None;review_path=args.human_review or folder/'t12_cohort_human_review.parquet'
    if not review_path.is_absolute():review_path=ROOT/review_path
    review_path=review_path.resolve()
    if not review_path.is_relative_to(ROOT.resolve()):raise ValueError('Human review must be stored inside the project')
    if review_path.is_file():
        human=pd.read_parquet(review_path)
        needed={'address','reviewed_by','reviewed_at','review_decision','source_url','source_opened_by_human','review_note'}
        if not needed.issubset(human):raise ValueError('Missing human review fields')
        if human.address.duplicated().any():raise ValueError('Duplicate human review')
        times=pd.to_datetime(human.reviewed_at,utc=True,errors='coerce')
        valid=human.reviewed_by.fillna('').str.strip().ne('') & times.notna() & times.le(pd.Timestamp.now(tz='UTC'))
        valid &= human.source_opened_by_human.map(lambda x:isinstance(x,(bool,np.bool_)) and bool(x))
        valid &= human.source_url.fillna('').str.startswith('https://') & human.review_note.fillna('').str.strip().ne('')
        valid &= human.review_decision.isin(['reviewed_unknown','verified_non_infrastructure','infrastructure'])
        reviewed=set(human.loc[valid,'address']);review_hash=sha256(review_path)
        human_infrastructure=set(human.loc[valid & human.review_decision.eq('infrastructure'),'address']) & set(members.address)
        if not valid.all():raise ValueError('Incomplete human source review; no AI approval or empty metadata accepted')
    pending=sorted(set(required)-reviewed)
    technical=bool(checks.status.eq('PASS').all())
    reasons=[]
    if not technical:reasons.append('Independent cohort reference calculation failed.')
    if infra.any():reasons.append(f'{int(infra.sum())} cohort member-days overlap retrospective T07 infrastructure; PIT eligibility/ownership interpretation unresolved. Do not silently exclude future labels.')
    if human_infrastructure:reasons.append(f'{len(human_infrastructure)} cohort addresses were identified as infrastructure by human review and require policy/rebuild resolution.')
    if pending:reasons.append(f'{len(pending)} audit/post-filter top addresses still require a team member to open and review sources.')
    ready=technical and not reasons
    if any(sha256(project_path(p))!=h for p,h in source_hashes.items()):raise ValueError('Inputs changed during cohort validation')
    previous.update(ready_for_t14_t15=ready,ready_for_cohort_whaleflow=ready,
        technical_cohort_validation_passed=technical,pending_human_review=len(pending),
        post_screen_top20_records=len(top),retrospective_infrastructure_member_days=int(infra.sum()),
        retrospective_infrastructure_addresses=int(tagged.loc[infra,'address'].nunique()),
        blocking_reasons=reasons,ready_for_individual_investor_inference=False,
        ready_for_rq3_pit_forecast=False,
        eligibility_scope='Unidentified high-activity address cohort only; CEX label PIT is a separate T14 condition',
        acceptance_validator=relative_path(Path(__file__)),acceptance_validator_sha256=sha256(Path(__file__)))
    report=dict(all_pass=technical,days_checked=len(checks),members_checked=len(members),
        failed_days=checks.loc[checks.status.ne('PASS'),'date'].tolist(),
        max_score_error=float(checks.max_score_error.max()),input_hashes=source_hashes,
        output_hashes={n:sha256(folder/n) for n in DESIGN_FILES},
        validation_sha256=sha256(folder/'t12_cohort_validation.parquet'),
        queue_sha256=sha256(folder/'t12_cohort_review_queue.parquet'),
        human_review_path=relative_path(review_path) if review_path.is_relative_to(ROOT) else str(review_path),
        human_review_sha256=review_hash,pending_addresses=pending,gate=previous)
    write_json(folder/'t12_cohort_review.json',report)
    write_json(gate_path,previous)
    audit=json.loads((folder/'t12_audit_summary.json').read_text(encoding='utf-8'))
    audit['downstream_gate']=previous;write_json(folder/'t12_audit_summary.json',audit)
    design.update(current_audit_sha256=sha256(folder/'t12_audit_summary.json'),
        ready_for_cohort_whaleflow=ready,cohort_validation_sha256=sha256(folder/'t12_cohort_review.json'))
    write_json(folder/'t12_design_summary.json',design)
    baseline=json.loads((folder/'t12_summary.json').read_text(encoding='utf-8'))
    baseline.update(ready_for_t14_t15=ready,ready_for_downstream=ready)
    write_json(folder/'t12_summary.json',baseline)
    print(json.dumps(dict(technical_pass=technical,days_checked=len(checks),members_checked=len(members),
        ready_for_cohort_whaleflow=ready,blocking_reasons=reasons),indent=2),flush=True)
    if not technical:raise SystemExit('Independent cohort validation failed')


if __name__=='__main__':main()
