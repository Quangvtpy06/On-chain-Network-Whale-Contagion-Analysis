"""Construct-validity diagnostics; no inference that an unknown address is a person."""
import json
import math
import shutil
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.graph_config import ROOT, read_config, project_path, relative_path
from src.node_centrality import sha256, write_json
from src.whale_score import verify_inputs, SETTINGS_FILE, OUTPUT_NAMES
from src.t12_review_evidence import ROWS, REVIEW_DATE

AUDIT_CONFIG=ROOT/'config/t12_audit.yaml'
AUDIT_NAMES=['exploratory_scores_daily.parquet','exploratory_scores_weekly.parquet',
 't12_label_coverage.parquet','t12_transfer_coverage.parquet','t12_rank_sensitivity.parquet',
 't12_component_correlations.parquet','t12_top50_stability.parquet','t12_address_behavior.parquet',
 't12_behavior_sensitivity.parquet','t12_address_review.parquet','t12_audit_validation.parquet']


def z_matrix(matrix):
    matrix=np.asarray(matrix,dtype=float)
    if not len(matrix):
        return np.zeros_like(matrix)
    std=matrix.std(axis=0,ddof=0)
    return np.divide(matrix-matrix.mean(axis=0),std,out=np.zeros_like(matrix),where=std>0)


def log_components(frame):
    return np.column_stack([np.log1p(frame.value),np.log1p(frame.weighted_degree),frame.pagerank])


def log_all_components(frame):
    """Log PR itself: log1p(PR) is effectively linear for tiny probabilities."""
    return np.column_stack([np.log1p(frame.value),np.log1p(frame.weighted_degree),
        np.log(np.maximum(frame.pagerank.to_numpy(float),np.finfo(float).tiny))])


def ratio(incoming,outgoing):
    incoming=np.asarray(incoming,dtype=float);outgoing=np.asarray(outgoing,dtype=float)
    gross=incoming+outgoing
    return np.divide(abs(incoming-outgoing),gross,out=np.zeros_like(gross),where=gross>0)


def top_addresses(frame,column,k):
    return frame.sort_values([column,'address'],ascending=[False,True]).head(k).address.tolist()


def longest_run(days):
    days=np.sort(np.unique(days));best=current=0;previous=None
    for day in days:
        current=current+1 if previous is not None and day-previous==1 else 1
        best=max(best,current);previous=day
    return best


def past_seven_days(days,flags):
    """Observed flags in (t-7d,t]; absent dates count zero, never future dates."""
    days=np.asarray(days);flags=np.asarray(flags,dtype=np.int64)
    prefix=np.r_[0,np.cumsum(flags)]
    starts=np.searchsorted(days,days-7,side='right')
    return prefix[np.arange(len(days))+1]-prefix[starts]


def coverage_rows(frame,window,key):
    rows=[]
    for scope,mask in [('all',np.ones(len(frame),dtype=bool)),('eligible',frame.eligible_for_whale_ranking),
                       ('excluded',~frame.eligible_for_whale_ranking)]:
        sub=frame.loc[mask];total=float(sub.value.sum());known=sub.is_entity_attributed.fillna(False).astype(bool)
        infrastructure=sub[['flag_exchange','flag_bridge','flag_contract','flag_zero_address']].any(axis=1)
        n=sub.address.nunique();identified=sub.loc[known,'address'].nunique()
        rows.append(dict(window_type=window,time_window=key,scope=scope,n_addresses=int(n),
            n_identified=int(identified),address_identity_coverage=identified/n if n else np.nan,
            endpoint_volume_usdt=total,identified_endpoint_volume_usdt=float(sub.loc[known,'value'].sum()),
            endpoint_identity_coverage=float(sub.loc[known,'value'].sum())/total if total else np.nan,
            infrastructure_endpoint_volume_usdt=float(sub.loc[infrastructure,'value'].sum()),
            infrastructure_endpoint_share=float(sub.loc[infrastructure,'value'].sum())/total if total else np.nan))
    return rows


def edge_coverage(frame,window,key,labels):
    maps=labels.attrs.get('coverage_maps')
    if maps is None:
        maps=(labels.is_entity_attributed,labels[['flag_exchange','flag_bridge','flag_contract','flag_zero_address']].any(axis=1))
        labels.attrs['coverage_maps']=maps
    identity,infrastructure=maps
    a=frame.from_address.map(identity).fillna(False).to_numpy(bool)
    b=frame.to_address.map(identity).fillna(False).to_numpy(bool)
    infra=frame.from_address.map(infrastructure).fillna(False)|frame.to_address.map(infrastructure).fillna(False)
    values=frame.total_value.to_numpy();total=float(values.sum())
    both=float(values[a&b].sum());one=float(values[a|b].sum());neither=float(values[~(a|b)].sum())
    return dict(window_type=window,time_window=key,transfer_volume_usdt=total,
        both_identified_volume_usdt=both,at_least_one_identified_volume_usdt=one,
        neither_identified_volume_usdt=neither,
        both_identified_share=both/total if total else np.nan,
        at_least_one_identified_share=one/total if total else np.nan,
        neither_identified_share=neither/total if total else np.nan,
        any_infrastructure_endpoint_share=float(values[infra.to_numpy()].sum())/total if total else np.nan)


def read_evidence():
    frame=pd.DataFrame(ROWS,columns=['address','observed_label','review_category','source_url','retrieval_mode','review_note'])
    if frame.address.duplicated().any():
        raise ValueError('Duplicate curated address evidence.')
    frame['reviewed_at']=REVIEW_DATE
    frame['review_method']='assistant_public_source_desk_review'
    frame['candidate_organization_claim']=frame.review_category.isin(['exchange_primary_document','exchange_tag','fund_tag','custody_tag'])
    frame['review_organization_tag']=False
    frame['verification_status']='pending_human_review'
    frame['review_organization_hint']=frame.review_category.isin(['exchange_hint','institution_document_hint','cross_chain_hint'])
    frame['primary_document_listed']=frame.review_category.eq('exchange_primary_document')
    return frame


def compute(folder,cfg,settings):
    folder.mkdir(parents=True,exist_ok=True)
    source=project_path(read_config(SETTINGS_FILE)['output_dir'])
    evidence=read_evidence().set_index('address')
    coverage=[];edge_rows=[];sensitivity=[];correlations=[];stability=[];thresholds=[];checks=[];top_days=[]
    daily=None
    for window in ['daily','weekly']:
        data=pd.read_parquet(source/f'whale_scores_{window}.parquet')
        data=data.sort_values(['time_window','address']).reset_index(drop=True)
        data['net_to_gross_ratio']=ratio(data.in_strength_usdt,data.out_strength_usdt)
        data['review_organization_tag']=False
        previous={};parts=[]
        for key,sub in data.groupby('time_window',sort=True):
            coverage.extend(coverage_rows(sub,window,key))
            eligible=sub.loc[sub.eligible_for_whale_ranking].copy()
            n=len(eligible);zlog=z_matrix(log_components(eligible));eligible['score_log1p']=zlog.sum(axis=1)
            eligible['rank_log1p']=eligible.score_log1p.rank(method='min',ascending=False).astype('Int64')
            eligible['score_raw']=eligible.whale_score
            zall=z_matrix(log_all_components(eligible))
            eligible['score_log_all']=zall.sum(axis=1)
            eligible['rank_log_all']=eligible.score_log_all.rank(method='min',ascending=False).astype('Int64')
            cutoff=max(settings['minimum_large_edge_transactions'],float(eligible.weighted_degree.quantile(settings['high_frequency_quantile']))) if n else math.inf
            eligible['frequency_cutoff']=cutoff
            eligible['flag_forwarding_candidate']=(eligible.net_to_gross_ratio<=settings['forwarding_net_ratio'])&(eligible.weighted_degree>=cutoff)
            eligible['eligible_postscreen_prototype']=~(eligible.flag_forwarding_candidate|eligible.review_organization_tag)
            eligible['score_postscreen_log1p']=np.nan
            m=eligible.eligible_postscreen_prototype
            eligible.loc[m,'score_postscreen_log1p']=z_matrix(log_components(eligible.loc[m])).sum(axis=1)
            eligible['rank_postscreen_log1p']=eligible.score_postscreen_log1p.rank(method='min',ascending=False).astype('Int64')
            raw_top=top_addresses(eligible,'score_raw',settings['top_k_stability'])
            log_top=top_addresses(eligible,'score_log1p',settings['top_k_stability'])
            all_top=top_addresses(eligible,'score_log_all',settings['top_k_stability'])
            top10raw=set(raw_top[:10]);top10log=set(log_top[:10])
            eligible['in_top10_raw']=eligible.address.isin(top10raw);eligible['in_top10_log']=eligible.address.isin(top10log)
            rho=float(spearmanr(eligible.score_raw,eligible.score_log1p).statistic) if n>1 and eligible.score_raw.nunique()>1 and eligible.score_log1p.nunique()>1 else np.nan
            sensitivity.append(dict(window_type=window,time_window=key,n_population=n,spearman_raw_log=rho,
                top10_overlap=len(top10raw&top10log)/min(10,n) if n else np.nan,
                top50_overlap=len(set(raw_top)&set(log_top))/min(settings['top_k_stability'],n) if n else np.nan,
                maximum_score_raw=float(eligible.score_raw.max()) if n else np.nan,
                maximum_score_log=float(eligible.score_log1p.max()) if n else np.nan,
                maximum_z_value_raw=float(eligible.z_value.max()) if n else np.nan,
                maximum_z_value_log=float(zlog[:,0].max()) if n else np.nan))
            sensitivity[-1].update(
                spearman_raw_log_all=float(spearmanr(eligible.score_raw,eligible.score_log_all).statistic) if n>1 else np.nan,
                spearman_log1p_log_all=float(spearmanr(eligible.score_log1p,eligible.score_log_all).statistic) if n>1 else np.nan,
                top50_overlap_raw_log_all=len(set(raw_top)&set(all_top))/min(settings['top_k_stability'],n) if n else np.nan)
            for variant,z in [('raw',eligible[['z_value','z_weighted_degree','z_pagerank']].to_numpy()),('log1p',zlog),('log_all',zall)]:
                for i,j in [(0,1),(0,2),(1,2)]:
                    nonconstant=n>1 and np.std(z[:,i])>0 and np.std(z[:,j])>0
                    correlations.append(dict(window_type=window,time_window=key,variant=variant,
                        component_a=['value','weighted_degree','pagerank'][i],component_b=['value','weighted_degree','pagerank'][j],
                        pearson=float(np.corrcoef(z[:,i],z[:,j])[0,1]) if nonconstant else np.nan,
                        spearman=float(spearmanr(z[:,i],z[:,j]).statistic) if nonconstant else np.nan))
                current=set({'raw':raw_top,'log1p':log_top,'log_all':all_top}[variant])
                if variant in previous:
                    old_key,old,old_partial=previous[variant];union=len(old|current)
                    stability.append(dict(window_type=window,previous_window=old_key,time_window=key,variant=variant,
                        previous_top_k_size=len(old),current_top_k_size=len(current),shared_top50=len(old&current),
                        jaccard=len(old&current)/union if union else np.nan,
                        retention=len(old&current)/len(old) if old else np.nan,
                        both_full_windows=not(old_partial or bool(sub.is_partial_week.iloc[0]))))
                previous[variant]=(key,current,bool(sub.is_partial_week.iloc[0]))
            for q in settings['frequency_quantile_sensitivity']:
                cut=max(settings['minimum_large_edge_transactions'],float(eligible.weighted_degree.quantile(q))) if n else math.inf
                for limit in settings['net_ratio_sensitivity']:
                    flagged=(eligible.net_to_gross_ratio<=limit)&(eligible.weighted_degree>=cut)
                    thresholds.append(dict(window_type=window,time_window=key,frequency_quantile=q,net_ratio_limit=limit,
                        frequency_cutoff=cut,n_flagged=int(flagged.sum()),
                        endpoint_volume_flagged=float(eligible.loc[flagged,'value'].sum()),
                        endpoint_volume_population=float(eligible.value.sum()),
                        top10_raw_flagged=int((flagged&eligible.in_top10_raw).sum()),
                        top10_log_flagged=int((flagged&eligible.in_top10_log).sum())))
            # Different summation path validates the new log score, not an economic claim.
            matrix=log_components(eligible)
            if n:
                mu=np.array([math.fsum(matrix[:,j])/n for j in range(3)])
                sigma=np.array([math.sqrt(math.fsum((float(v)-mu[j])**2 for v in matrix[:,j])/n) for j in range(3)])
                ref=np.divide(matrix-mu,sigma,out=np.zeros_like(matrix),where=sigma>0).sum(axis=1)
                error=float(np.max(abs(ref-eligible.score_log1p.to_numpy())))
            else:error=0.
            checks.append(dict(window_type=window,time_window=key,n_eligible=n,max_log_score_error=error,
                status='PASS' if error<1e-10 and np.isfinite(eligible.score_log1p).all() else 'FAIL'))
            matrix=log_all_components(eligible)
            if n:
                mu=np.array([math.fsum(matrix[:,j])/n for j in range(3)])
                sigma=np.array([math.sqrt(math.fsum((float(v)-mu[j])**2 for v in matrix[:,j])/n) for j in range(3)])
                ref=np.divide(matrix-mu,sigma,out=np.zeros_like(matrix),where=sigma>0).sum(axis=1)
                all_error=float(np.max(abs(ref-eligible.score_log_all.to_numpy())))
            else:all_error=0.
            checks[-1].update(max_log_all_score_error=all_error)
            if all_error>=1e-10 or not np.isfinite(eligible.score_log_all).all():checks[-1]['status']='FAIL'
            if window=='daily':
                for variant,selected in [('raw',top10raw),('log1p',top10log)]:
                    top_days.extend((variant,key,address) for address in sorted(selected))
            parts.append(eligible)
        scored=pd.concat(parts,ignore_index=True)
        columns=['window_type','time_window','address','value','weighted_degree','pagerank','net_to_gross_ratio',
            'score_raw','whale_rank','score_log1p','rank_log1p','score_log_all','rank_log_all','frequency_cutoff','flag_forwarding_candidate',
            'review_organization_tag','eligible_postscreen_prototype','score_postscreen_log1p','rank_postscreen_log1p',
            'in_top10_raw','in_top10_log','is_partial_week','eligible_for_regression','flag_unattributed']
        scored[columns].to_parquet(folder/f'exploratory_scores_{window}.parquet',index=False)
        labels=data.drop_duplicates('address').set_index('address')
        edges=pd.read_parquet(project_path(cfg['data'][f'{window}_edges_parquet']))
        for key,sub in edges.groupby('time_window',sort=True):
            row=edge_coverage(sub,window,key,labels);edge_rows.append(row)
            total=float(data.loc[data.time_window.eq(key),'value'].sum())
            if not np.isclose(total,2*row['transfer_volume_usdt'],rtol=1e-12,atol=.01):
                raise ValueError('Endpoint and edge-volume denominators do not reconcile.')
        if window=='daily':
            # Additional full-period/monthly coverage: unique addresses, not sums of daily counts.
            for period,group in data.groupby(data.time_window.str[:7],sort=True):
                coverage.extend(coverage_rows(group,'monthly',period))
            coverage.extend(coverage_rows(data,'full_period','2025-01-01/2026-10-17'))
            for period,group in edges.groupby(edges.time_window.str[:7],sort=True):
                edge_rows.append(edge_coverage(group,'monthly',period,labels))
            edge_rows.append(edge_coverage(edges,'full_period','2025-01-01/2026-10-17',labels))
            flags=scored.set_index(['time_window','address'])[['flag_forwarding_candidate','in_top10_raw','in_top10_log']]
            index=pd.MultiIndex.from_frame(data[['time_window','address']])
            for column in flags:
                data[column]=flags[column].reindex(index).astype('boolean').fillna(False).to_numpy(bool)
            daily=data
        print(f'T12 audit {window}: {len(parts)} windows',flush=True)
    daily['day_number']=pd.to_datetime(daily.time_window).astype('int64')//86400000000000
    daily=daily.sort_values(['address','day_number']).reset_index(drop=True)
    rolling_counts=np.zeros(len(daily),dtype=np.int64)
    day_numbers=daily.day_number.to_numpy()
    forwarding=daily.flag_forwarding_candidate.to_numpy()
    for _,positions in daily.groupby('address',sort=False).indices.items():
        rolling_counts[positions]=past_seven_days(day_numbers[positions],forwarding[positions])
    daily['past_7d_forwarding_days']=rolling_counts
    daily['flag_persistent_forwarding']=daily.past_7d_forwarding_days>=settings['persistent_forwarding_days_in_7d']
    daily['low_net_volume']=daily.value.where(daily.net_to_gross_ratio<=settings['forwarding_net_ratio'],0.)
    profile=daily.groupby('address',sort=True).agg(
        entity_name=('entity_name','first'),entity_type=('entity_type','first'),
        flag_unattributed=('flag_unattributed','first'),eligible_for_whale_ranking=('eligible_for_whale_ranking','first'),
        active_days=('time_window','size'),incoming_usdt=('in_strength_usdt','sum'),outgoing_usdt=('out_strength_usdt','sum'),
        median_daily_net_to_gross_ratio=('net_to_gross_ratio','median'),large_edge_transaction_count=('weighted_degree_tx','sum'),
        forwarding_candidate_days=('flag_forwarding_candidate','sum'),persistent_forwarding_days=('flag_persistent_forwarding','sum'),
        low_net_volume=('low_net_volume','sum'),endpoint_volume=('value','sum'),
        top10_days_raw=('in_top10_raw','sum'),top10_days_log=('in_top10_log','sum'))
    profile['full_period_net_to_gross_ratio']=ratio(profile.incoming_usdt,profile.outgoing_usdt)
    profile['low_net_volume_share']=profile.low_net_volume/profile.endpoint_volume
    profile=profile.drop(columns=['low_net_volume','endpoint_volume'])
    for variant in ['raw','log']:
        streaks=daily.loc[daily[f'in_top10_{variant}']].groupby('address').day_number.agg(longest_run)
        profile[f'top10_longest_streak_{variant}']=streaks.reindex(profile.index,fill_value=0).astype(int)
    profile=profile.reset_index()
    top_review={}
    for variant in ['raw','log']:
        selected=profile[profile.eligible_for_whale_ranking].sort_values([f'top10_days_{variant}','address'],ascending=[False,True]).head(settings['manual_review_top_n_per_variant'])
        # Frequency ties use address rather than unstable floating-point averages.
        top_review[variant]={a:i+1 for i,a in enumerate(selected.address)}
    addresses=sorted(set(top_review['raw'])|set(top_review['log']))
    reviewed=profile[profile.address.isin(addresses)].merge(evidence.reset_index(),on='address',how='left',validate='one_to_one')
    reviewed['selection_rank_raw']=reviewed.address.map(top_review['raw']).astype('Int64')
    reviewed['selection_rank_log']=reviewed.address.map(top_review['log']).astype('Int64')
    reviewed['review_record_present']=reviewed.review_category.notna()
    if not reviewed.review_record_present.all():
        reviewed['review_note']=reviewed.review_note.fillna('New top address needs public-source review.')
    tables={
        't12_label_coverage.parquet':pd.DataFrame(coverage),'t12_transfer_coverage.parquet':pd.DataFrame(edge_rows),
        't12_rank_sensitivity.parquet':pd.DataFrame(sensitivity),'t12_component_correlations.parquet':pd.DataFrame(correlations),
        't12_top50_stability.parquet':pd.DataFrame(stability),'t12_address_behavior.parquet':profile,
        't12_behavior_sensitivity.parquet':pd.DataFrame(thresholds),'t12_address_review.parquet':reviewed,
        't12_audit_validation.parquet':pd.DataFrame(checks)}
    for name,table in tables.items():table.to_parquet(folder/name,index=False)
    if not tables['t12_audit_validation.parquet'].status.eq('PASS').all():
        raise ValueError('Log-score reference validation failed.')
    return tables


def main():
    cfg=read_config();settings=read_config(AUDIT_CONFIG);base=read_config(SETTINGS_FILE)
    folder=project_path(settings['output_dir'])
    if folder.resolve()!=project_path(base['output_dir']).resolve():raise ValueError('Audit must match T12 output directory')
    provenance,_=verify_inputs(cfg)
    review=json.loads((folder/'t12_review.json').read_text(encoding='utf-8'))
    proof=json.loads((folder/'t12_reproducibility.json').read_text(encoding='utf-8'))
    if not review['all_pass'] or not proof['all_match']:
        raise ValueError('Technical T12 validation must pass before construct-validity audit.')
    if review.get('validator_sha256')!=sha256(ROOT/'scripts/validate_t12_current.py'):
        raise ValueError('Rerun the current independent numerical validator first.')
    for name in OUTPUT_NAMES:
        if not sha256(folder/name)==proof['hashes'][name]['run1']==proof['hashes'][name]['run2']==review['output_hashes'][name]:
            raise ValueError('T12 base artifact changed.')
    # User requested removing synthetic test sources after their successful run.
    # Keep the historical result, never present it as tests re-executed here.
    tests=json.loads((folder/'t12_tests.json').read_text(encoding='utf-8'))
    if not tests.get('passed'):
        raise ValueError('Missing historical mathematical-check evidence')
    paths=[folder/name for name in OUTPUT_NAMES]+[AUDIT_CONFIG,ROOT/'src/t12_review_evidence.py',Path(__file__),SETTINGS_FILE,
        ROOT/'src/whale_score.py',ROOT/'scripts/validate_t12_current.py',folder/'t12_tests.json']
    inputs={relative_path(p):sha256(p) for p in paths}
    tables=compute(folder,cfg,settings)
    hashes={n:dict(run1=sha256(folder/n)) for n in AUDIT_NAMES}
    cache=ROOT/'.cache';cache.mkdir(exist_ok=True);temporary=cache/f't12_audit_repro_{uuid.uuid4().hex}';temporary.mkdir()
    try:
        compute(temporary,cfg,settings)
        for n in AUDIT_NAMES:hashes[n]['run2']=sha256(temporary/n)
    finally:
        if not temporary.resolve().is_relative_to(cache.resolve()):raise ValueError('Unsafe cleanup path')
        shutil.rmtree(temporary)
    same=all(p['run1']==p['run2'] for p in hashes.values())
    after,_=verify_inputs(cfg)
    if after!=provenance or any(sha256(project_path(p))!=h for p,h in inputs.items()):raise ValueError('Audit inputs changed')
    coverage=tables['t12_label_coverage.parquet'];full=coverage[coverage.window_type.eq('full_period')]
    sensitivity=tables['t12_rank_sensitivity.parquet'];stability=tables['t12_top50_stability.parquet'];reviewed=tables['t12_address_review.parquet']
    gate=dict(ready_for_t14_t15=False,ready_for_cohort_whaleflow=False,
        t14_independent_branches_allowed=['cex_netflow','lagged_large_transfer_events','network_concentration'],
        purpose='Gate applies to cohort WhaleFlow, not all of T14',
        label_coverage_measured=True,raw_log_comparison_completed=True,
        top20_raw_records=int(reviewed.selection_rank_raw.notna().sum()),top20_log_records=int(reviewed.selection_rank_log.notna().sum()),
        review_lookup_records_complete=bool(reviewed.review_record_present.all()),
        raw_top20_organization_tags=int(reviewed.loc[reviewed.selection_rank_raw.notna(),'review_organization_tag'].sum()),
        log_top20_organization_tags=int(reviewed.loc[reviewed.selection_rank_log.notna(),'review_organization_tag'].sum()),
        pending_human_review=int(reviewed.verification_status.eq('pending_human_review').sum()),
        blocking_reasons=['AI lookup candidates have not been independently verified by a team member.',
            'Behavioral forwarding screen is a sensitivity prototype, not validated ownership classification.',
            'Post-screen top cohort and WhaleFlow definition require validation before T14/T15.'],
        technical_validation_does_not_establish_investor_identity=True)
    summary=dict(audit_complete=bool(same),ready_for_exploration=bool(same),settings=settings,inputs=inputs,
        upstream=provenance,full_period_endpoint_coverage=full.to_dict('records'),
        full_period_transfer_coverage=tables['t12_transfer_coverage.parquet'].query("window_type == 'full_period'").to_dict('records'),
        sensitivity=[dict(window_type=w,median_spearman=float(s.spearman_raw_log.median()),minimum_spearman=float(s.spearman_raw_log.min()),
            median_spearman_raw_log_all=float(s.spearman_raw_log_all.median()),
            median_spearman_log1p_log_all=float(s.spearman_log1p_log_all.median()),
            median_top50_overlap=float(s.top50_overlap.median())) for w,s in sensitivity.groupby('window_type')],
        adjacent_top50=[dict(window_type=w,variant=v,median_jaccard=float(s.jaccard.median()),median_retention=float(s.retention.median()))
            for (w,v),s in stability[stability.both_full_windows].groupby(['window_type','variant'])],
        primary_exploratory_variant=settings['primary_exploratory_variant'],canonical_raw_score_retained=True,
        tests=tests,downstream_gate=gate,
        limitations=['Large-edge transaction count only covers transfers retained after netting and >=500000 USDT threshold.',
            'Low net/gross is not proof of forwarding, custody, automation or individual ownership.',
            'Repeated top-10 placement is descriptive persistence, not an identity classifier.',
            'Current public labels and full-period profiles are retrospective; do not use them as historically available predictors.'])
    write_json(folder/'t12_audit_reproducibility.json',dict(all_match=same,hashes=hashes))
    write_json(folder/'t12_audit_summary.json',summary);write_json(folder/'t12_downstream_gate.json',gate)
    baseline=json.loads((folder/'t12_summary.json').read_text(encoding='utf-8'))
    baseline.update(ready_for_exploration=bool(same),ready_for_downstream=False,ready_for_t14_t15=False,
        interpretation='Exploratory large-activity addresses; unverified economic identity',audit_file=relative_path(folder/'t12_audit_summary.json'))
    write_json(folder/'t12_summary.json',baseline)
    print(json.dumps({k:summary[k] for k in ['audit_complete','full_period_endpoint_coverage','sensitivity','adjacent_top50','downstream_gate']},indent=2),flush=True)
    if not same:raise ValueError('Audit reproducibility failed')
