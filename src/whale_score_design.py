"""Lagged cohorts and CEX diagnostics; no regression outcomes are read."""
import json
import shutil
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from src.graph_config import ROOT, read_config, project_path, relative_path
from src.node_centrality import sha256, write_json
from src.whale_score import verify_inputs
from src.whale_score_audit import log_all_components, z_matrix, ratio, read_evidence
from src.secondary_labels import VERIFIED_COLUMNS, available_labels

DESIGN_CONFIG=ROOT/'config/t12_design.yaml'
DESIGN_NAMES=['cohort_members_daily.parquet','cohort_snapshot_daily.parquet',
    'cohort_filter_sensitivity.parquet','cex_coverage.parquet','cex_netflow_daily.parquet',
    'cex_wallet_inventory.parquet','t12_design_validation.parquet']


def trailing_sum(times,values,target,lookback):
    """Reference-friendly helper: closed left, open right [t-L,t)."""
    times=np.asarray(times,dtype='datetime64[D]');target=np.datetime64(target,'D')
    return np.asarray(values)[(times>=target-np.timedelta64(lookback,'D'))&(times<target)].sum(axis=0)


def cex_mask(labels):
    # Generic exchange tags and DEX routers must never imply CEX.
    return labels.entity_type.eq('CEX') & ~labels.label_conflict_review.fillna(False).astype(bool)


def prepare_label_review(settings):
    candidate_path=project_path(settings['candidate_labels']);candidate_path.parent.mkdir(parents=True,exist_ok=True)
    candidates=read_evidence().drop(columns=['review_organization_tag'])
    candidates['entity_name']=candidates.observed_label
    candidates['entity_type']=''
    candidates['decision']='pending'
    for c in ['confidence','verified_by','verified_at','label_available_at','effective_from']:
        candidates[c]=''
    for c in ['source_opened_by_human','ethereum_address_confirmed']:
        candidates[c]=pd.Series([pd.NA]*len(candidates),dtype='boolean')
    # Regenerable AI queue only; human decisions live in a separate append-only sidecar.
    candidates.to_parquet(candidate_path,index=False)
    verified_path=project_path(settings['secondary_labels'])
    if not verified_path.exists():
        pd.DataFrame({c:pd.Series(dtype='int64' if c=='source_tier' else 'object') for c in VERIFIED_COLUMNS}).to_parquet(verified_path,index=False)


def check_protocol(settings,folder):
    frozen=folder/'t12_protocol_freeze.json';fingerprint=sha256(DESIGN_CONFIG)
    if frozen.exists():
        if json.loads(frozen.read_text(encoding='utf-8'))['settings_sha256']!=fingerprint:
            raise ValueError('Frozen protocol changed. Create a separately versioned protocol; never overwrite after seeing T15.')
    else:
        if list((ROOT/'data/processed/t15').glob('*.parquet')):
            raise ValueError('T15 outputs exist; cannot claim a pre-T15 protocol freeze.')
        write_json(frozen,dict(protocol_id=settings['protocol_id'],settings_sha256=fingerprint,
            settings=settings,regression_outcomes_read=False,
            change_policy='New version and explicit deviation report; keep v1 sensitivity and results.'))


def build_cohort(frame,contracts,secondary,dates,settings,folder):
    frame=frame.sort_values(['time_window','address']).copy()
    addresses=np.sort(frame.address.unique());n=len(addresses)
    codes=pd.Index(addresses);rows_by_day={k:g for k,g in frame.groupby('time_window',sort=True)}
    index={k:codes.get_indexer(g.address) for k,g in rows_by_day.items()}
    columns=['in_strength_usdt','out_strength_usdt','weighted_degree_tx','pagerank']
    values={k:g[columns].to_numpy(float) for k,g in rows_by_day.items()}
    totals=np.zeros((n,4));lookback=settings['lookback_days'];members=[];snapshots=[];sens=[];checks=[];previous=None
    creation=pd.to_datetime(contracts.set_index('address').first_contract_timestamp.reindex(addresses),utc=True).dt.as_unit('ns').astype('int64').to_numpy()
    nat=np.iinfo(np.int64).min
    zero=addresses=='0x'+'0'*40
    for day_index,date in enumerate(dates):
        t=pd.Timestamp(date)
        add=(t-pd.Timedelta(days=1)).strftime('%Y-%m-%d');remove=(t-pd.Timedelta(days=lookback+1)).strftime('%Y-%m-%d')
        if add in values:totals[index[add]]+=values[add]
        if remove in values:totals[index[remove]]-=values[remove]
        # Counters are integers, so this also removes inactive nodes without using future activity.
        active=np.flatnonzero(totals[:,2]>.5)
        history=day_index>=settings['minimum_history_days']
        cutoff_ns=t.value;contract_known=(creation!=nat)&(creation<cutoff_ns)
        known=available_labels(secondary,t)
        excluded_entities=set(known.loc[known.entity_type.isin(['CEX','DEX','Bridge','Contract','Other']),'address'])
        entity_excluded=np.isin(addresses[active],list(excluded_entities))
        keep=~(contract_known[active]|zero[active]|entity_excluded)
        ids=active[keep];v=totals[ids].copy();v=np.maximum(v,0.)
        population=pd.DataFrame(dict(address=addresses[ids],value=v[:,0]+v[:,1],weighted_degree=v[:,2],pagerank=v[:,3]/lookback))
        population['net_to_gross_ratio']=ratio(v[:,0],v[:,1])
        cut=max(settings['minimum_large_edge_transactions'],float(population.weighted_degree.quantile(settings['frequency_quantile']))) if len(population) else np.inf
        forwarding=(population.net_to_gross_ratio<=settings['forwarding_net_ratio'])&(population.weighted_degree>=cut)
        population['score']=np.nan;valid=~forwarding
        population.loc[valid,'score']=z_matrix(log_all_components(population.loc[valid])).sum(axis=1)
        selected=population.loc[valid].sort_values(['score','address'],ascending=[False,True]).head(settings['cohort_size']) if history else population.iloc[:0]
        current=set(selected.address);union=len(current|previous) if previous is not None else 0
        for rank,row in enumerate(selected.itertuples(),1):
            members.append(dict(date=date,address=row.address,cohort_rank=rank,score=row.score,
                value_30d=row.value,large_edge_tx_30d=row.weighted_degree,pagerank_calendar_mean_30d=row.pagerank,
                net_to_gross_ratio_30d=row.net_to_gross_ratio,window_start=(t-pd.Timedelta(days=lookback)).strftime('%Y-%m-%d'),
                information_cutoff=add,label_policy=settings['entity_label_policy'],protocol_id=settings['protocol_id']))
        snapshots.append(dict(date=date,information_cutoff=add,history_days=min(day_index,lookback),
            has_full_history=history,n_active=len(active),n_candidates=len(population),n_forwarding=int(forwarding.sum()),
            n_human_labels_available=len(known),frequency_cutoff=cut,n_selected=len(current),
            jaccard_previous=len(current&previous)/union if history and previous is not None and union else np.nan,
            ready_for_cohort_whaleflow=False))
        if history:
            for q in settings['frequency_quantile_sensitivity']:
                threshold=max(settings['minimum_large_edge_transactions'],float(population.weighted_degree.quantile(q))) if len(population) else np.inf
                for limit in settings['net_ratio_sensitivity']:
                    mask=(population.net_to_gross_ratio<=limit)&(population.weighted_degree>=threshold)
                    remaining=population.loc[~mask].copy();remaining['sensitivity_score']=z_matrix(log_all_components(remaining)).sum(axis=1)
                    other=set(remaining.sort_values(['sensitivity_score','address'],ascending=[False,True]).head(settings['cohort_size']).address)
                    sens.append(dict(date=date,frequency_quantile=q,net_ratio_limit=limit,n_removed=int(mask.sum()),
                        jaccard_to_frozen=len(current&other)/len(current|other) if current|other else np.nan))
        checks.append(dict(date=date,status='PASS' if (not history and not current) or
            (history and len(current)<=settings['cohort_size'] and np.isfinite(selected.score).all()) else 'FAIL',
            strictly_before_prediction_day=add<date,source_window_start=(t-pd.Timedelta(days=lookback)).strftime('%Y-%m-%d')))
        if history:previous=current
    for name,data in [('cohort_members_daily',members),('cohort_snapshot_daily',snapshots),('cohort_filter_sensitivity',sens),('t12_design_validation',checks)]:
        pd.DataFrame(data).to_parquet(folder/(name+'.parquet'),index=False)


def build_cex(edges,labels,secondary,dates,folder):
    # This branch is explicitly retrospective: current T07 labels, NOT a PIT forecast.
    labels=labels.copy()
    if len(secondary):
        # Decisions are human-reviewed; conflicts are not silently reconciled.
        for row in secondary.itertuples():
            present=labels.address.eq(row.address)
            if present.any() and labels.loc[present,'is_entity_attributed'].any():
                if not labels.loc[present,'entity_type'].eq(row.entity_type).all():raise ValueError('Secondary label conflicts with attributed T07')
            for column in ['entity_name','entity_type','confidence','source_url']:
                labels.loc[present,column]=getattr(row,column)
    cex=set(labels.loc[cex_mask(labels),'address']);dex=set(labels.loc[labels.entity_type.eq('DEX'),'address'])
    a=edges.from_address.isin(cex);b=edges.to_address.isin(cex)
    edges=edges.copy();edges['cex_external_in']=edges.total_value.where(~a&b,0.)
    edges['cex_external_out']=edges.total_value.where(a&~b,0.)
    edges['cex_internal']=edges.total_value.where(a&b,0.)
    edges['cex_incident']=edges.total_value.where(a|b,0.)
    edges['cex_endpoint']=edges.total_value*(a.astype(int)+b.astype(int))
    x=edges.from_address.isin(dex);y=edges.to_address.isin(dex)
    edges['dex_endpoint']=edges.total_value*(x.astype(int)+y.astype(int))
    rows=[]
    for window,groups in [('daily',edges.groupby('time_window',sort=True)),
                          ('monthly',edges.groupby(edges.time_window.str[:7],sort=True)),
                          ('full_period',[('2025-01-01/2026-10-17',edges)])]:
        for key,g in groups:
            total=float(g.total_value.sum());endpoint=float(g.cex_endpoint.sum());dexvolume=float(g.dex_endpoint.sum())
            rows.append(dict(window_type=window,time_window=key,transfer_volume_usdt=total,
                known_cex_endpoint_volume_usdt=endpoint,known_cex_endpoint_share=endpoint/(2*total) if total else np.nan,
                known_cex_incident_transfer_share=float(g.cex_incident.sum())/total if total else np.nan,
                known_cex_share_of_labeled_exchange_endpoint_volume=endpoint/(endpoint+dexvolume) if endpoint+dexvolume else np.nan,
                cex_external_in_usdt=float(g.cex_external_in.sum()),cex_external_out_usdt=float(g.cex_external_out.sum()),
                cex_netflow_usdt=float(g.cex_external_in.sum()-g.cex_external_out.sum()),cex_internal_usdt=float(g.cex_internal.sum()),
                label_policy='retrospective_T07_plus_human_verified_secondary',true_cex_recall_known=False))
    coverage=pd.DataFrame(rows);coverage.to_parquet(folder/'cex_coverage.parquet',index=False)
    flow=coverage[coverage.window_type.eq('daily')].set_index('time_window').reindex(dates)
    for column in ['cex_external_in_usdt','cex_external_out_usdt','cex_netflow_usdt','cex_internal_usdt']:flow[column]=flow[column].fillna(0.)
    flow.index.name='date';flow.reset_index().to_parquet(folder/'cex_netflow_daily.parquet',index=False)
    inventory=labels.loc[cex_mask(labels),['address','entity_name','entity_type','confidence','source_url','date_downloaded']].copy()
    inventory['participates_in_graph']=inventory.address.isin(set(edges.from_address)|set(edges.to_address))
    inventory.to_parquet(folder/'cex_wallet_inventory.parquet',index=False)


def compute(folder,cfg,settings):
    folder.mkdir(parents=True,exist_ok=True)
    dates=pd.date_range(cfg['project']['start_date'],cfg['project']['end_date']).strftime('%Y-%m-%d').tolist()
    frame=pd.read_parquet(project_path(cfg['data']['processed_t09_dir'])/'node_metrics_daily.parquet')
    secondary=pd.read_parquet(project_path(settings['secondary_labels']))
    contracts=pd.read_parquet(project_path(cfg['data']['contract_status_parquet']))
    build_cohort(frame,contracts,secondary,dates,settings,folder)
    print('Lagged 30-day cohort computed',flush=True)
    labels=pd.read_parquet(project_path(cfg['data']['processed_labels_parquet']))
    edges=pd.read_parquet(project_path(cfg['data']['daily_edges_parquet']))
    build_cex(edges,labels,secondary,dates,folder)


def main():
    cfg=read_config();settings=read_config(DESIGN_CONFIG);folder=project_path(settings['output_dir'])
    provenance,_=verify_inputs(cfg);prepare_label_review(settings);check_protocol(settings,folder)
    audit=json.loads((folder/'t12_audit_summary.json').read_text(encoding='utf-8'))
    if not audit.get('audit_complete'):raise ValueError('Run current T12 audit first')
    paths=[DESIGN_CONFIG,Path(__file__),ROOT/'src/secondary_labels.py',ROOT/'src/whale_score_audit.py',
        project_path(settings['secondary_labels']),project_path(settings['candidate_labels'])]
    inputs={relative_path(p):sha256(p) for p in paths}
    compute(folder,cfg,settings);hashes={name:dict(run1=sha256(folder/name)) for name in DESIGN_NAMES}
    cache=ROOT/'.cache';cache.mkdir(exist_ok=True);temporary=cache/f't12_design_{uuid.uuid4().hex}';temporary.mkdir()
    try:
        compute(temporary,cfg,settings)
        for name in DESIGN_NAMES:hashes[name]['run2']=sha256(temporary/name)
    finally:
        if not temporary.resolve().is_relative_to(cache.resolve()):raise ValueError('Unsafe cleanup')
        shutil.rmtree(temporary)
    same=all(row['run1']==row['run2'] for row in hashes.values())
    after,_=verify_inputs(cfg)
    if after!=provenance or any(sha256(project_path(p))!=h for p,h in inputs.items()):raise ValueError('Design inputs changed')
    snapshots=pd.read_parquet(folder/'cohort_snapshot_daily.parquet')
    validation=pd.read_parquet(folder/'t12_design_validation.parquet')
    if not same or not validation.status.eq('PASS').all():raise ValueError('Design validation failed')
    full=pd.read_parquet(folder/'cex_coverage.parquet').query("window_type == 'full_period'").to_dict('records')[0]
    inventory=pd.read_parquet(folder/'cex_wallet_inventory.parquet')
    result=dict(complete=True,inputs=inputs,upstream=provenance,protocol_id=settings['protocol_id'],
        current_audit_sha256=sha256(folder/'t12_audit_summary.json'),
        history_qualified_days=int(snapshots.has_full_history.sum()),warmup_days=int((~snapshots.has_full_history).sum()),
        median_adjacent_cohort_jaccard=float(snapshots.jaccard_previous.median()),
        maximum_human_labels_available=int(snapshots.n_human_labels_available.max()),
        cex_addresses=int(len(inventory)),cex_addresses_active=int(inventory.participates_in_graph.sum()),cex_volume_coverage=full,
        rq3_caveat='Known CEX volume share is not recall; unknown addresses may be CEX. Retrospective labels are not PIT forecast evidence.',
        blocked_scope='cohort_WhaleFlow_only',t14_cex_descriptive_available=True,
        t14_large_transfer_events_independent=True,t14_network_concentration_independent=True,
        ready_for_cohort_whaleflow=False,ready_for_rq3_pit_forecast=False)
    write_json(folder/'t12_design_reproducibility.json',dict(all_match=same,hashes=hashes))
    write_json(folder/'t12_design_summary.json',result)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
