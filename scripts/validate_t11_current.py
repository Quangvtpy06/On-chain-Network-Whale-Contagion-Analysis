"""Kiểm định đầy đủ T11 từ cạnh T08; không nhập công thức production T11."""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ttest_ind

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.graph_config import read_config,project_path
from src.node_centrality import sha256,verified_t08_inputs,calendar_metadata,write_json

OUTPUTS={'community_nodes_daily.parquet','community_nodes_weekly.parquet',
    'snapshot_metrics_daily.parquet','snapshot_metrics_weekly.parquet','t11_validation.parquet',
    'top_communities_summary.parquet','rq4_daily_regimes.parquet','rq4_comparison.parquet'}
SOURCE_FILES={'src/community_concentration.py','src/t11_reporting.py','src/visualize_t11.py','T11_Community_Concentration.py'}
METRICS=['gini_volume','hhi_community_volume','community_concentration_index','modularity','cr_top5pct_volume']


def reference_hhi(x):
    total=math.fsum(x)
    return math.fsum((float(v)/total)**2 for v in x) if total>0 else 0.


def reference_gini(x):
    x=np.sort(np.asarray(x,float));total=math.fsum(x);n=len(x)
    if n<=1 or total<=0:return 0.
    cumulative=np.cumsum(x)
    return 1.-math.fsum((np.r_[0.,cumulative[:-1]]+cumulative)/(n*total))


def reference_entropy(x):
    total=math.fsum(x);n=len(x)
    return -math.fsum((float(v)/total)*math.log(float(v)/total) for v in x if v>0)/math.log(n) if n>1 and total>0 else 0.


def validate_release(folder_override=None):
    cfg=read_config();settings=read_config(ROOT/'config/t11.yaml')
    folder=project_path(settings['output_dir']) if folder_override is None else Path(folder_override).resolve()
    if folder_override is not None and not folder.is_relative_to((ROOT/'.cache').resolve()):
        raise ValueError('Alternate validation directory must remain in project cache')
    summary=json.loads((folder/'t11_summary.json').read_text(encoding='utf-8'))
    summary['ready_for_downstream']=False
    write_json(folder/'t11_summary.json',summary)
    errors={};checked=[];before=verified_t08_inputs(cfg)
    def require(condition,message):
        if not bool(condition):raise ValueError(message)
    def close(observed,reference,label):
        observed=np.asarray(observed,float);reference=np.asarray(reference,float)
        delta=float(np.max(abs(observed-reference))) if np.size(observed) else 0.
        errors[label]=max(delta,errors.get(label,0.))
        require(np.allclose(observed,reference,atol=1e-7,rtol=1e-10,equal_nan=False),f'{label} differs by {delta}')
    try:
        require(summary['inputs']==before,'T08 provenance mismatch')
        require(summary['config_sha256']==sha256(ROOT/'config/config.yaml'),'Config changed')
        require(summary['settings_sha256']==sha256(ROOT/'config/t11.yaml'),'T11 settings changed')
        require(summary['code_sha256']==sha256(ROOT/'src/community_concentration.py'),'T11 code changed')
        require(set(summary.get('source_code_hashes',{}))==SOURCE_FILES,'Incomplete code provenance')
        require(all(sha256(ROOT/p)==h for p,h in summary['source_code_hashes'].items()),'Source code changed')
        require(summary.get('is_complete_run') and summary.get('reproducibility_pass'),'Exploration is not releasable')
        require(summary.get('python_hash_seed')=='0','Missing deterministic process seed')
        proof=json.loads((folder/'t11_reproducibility.json').read_text(encoding='utf-8'))
        require(proof.get('all_match') and proof.get('separate_processes') and proof.get('python_hash_seed')=='0','No independent-process reproduction proof')
        require(set(proof.get('hashes',{}))==OUTPUTS,'Incomplete output hash set')
        output_hashes={name:sha256(folder/name) for name in sorted(OUTPUTS)}
        require(all(output_hashes[name]==p.get('run1')==p.get('run2') for name,p in proof['hashes'].items()),'Current artifact hash does not match reproduction')
        expected_top=[];daily=None;snapshot_tables=[]
        for window in ['daily','weekly']:
            edges=pd.read_parquet(project_path(cfg['data'][window+'_edges_parquet']))
            nodes=pd.read_parquet(folder/f'community_nodes_{window}.parquet')
            snapshots=pd.read_parquet(folder/f'snapshot_metrics_{window}.parquet')
            snapshot_tables.append(snapshots)
            calendar=calendar_metadata(window,cfg)
            require(snapshots.time_window.tolist()==calendar.time_window.tolist(),window+': calendar mismatch')
            require(snapshots.window_type.eq(window).all() and nodes.window_type.eq(window).all(),window+': window type mismatch')
            for col in ['days_in_window','is_partial_week','eligible_for_regression']:
                require(snapshots[col].tolist()==calendar[col].tolist(),window+': '+col)
            require(not nodes.duplicated(['time_window','address']).any(),window+': duplicate node key')
            require(set(nodes.time_window)<=set(calendar.time_window),window+': unexpected node window')
            eg={k:g for k,g in edges.groupby('time_window')};ng={k:g for k,g in nodes.groupby('time_window')}
            snap=snapshots.set_index('time_window')
            for meta in calendar.to_dict('records'):
                key=meta['time_window'];e=eg.get(key,edges.iloc[:0]);n=ng.get(key,nodes.iloc[:0]).sort_values('address');s=snap.loc[key]
                label=window+'/'+key
                addresses=sorted(set(e.from_address)|set(e.to_address))
                require(n.address.tolist()==addresses,label+': node universe differs')
                for col in ['days_in_window','is_partial_week','eligible_for_regression']:
                    require(n[col].eq(meta[col]).all(),label+': node '+col)
                seed=int(hashlib.sha256(f"{settings['seed']}|{window}|{key}".encode()).hexdigest()[:8],16)
                require(s.sampling_seed==seed,label+': seed differs')
                if not addresses:
                    for col in snapshots.select_dtypes(include='number'):
                        if col not in ['days_in_window','sampling_seed']:close(s[col],0.,col)
                    checked.append(dict(window_type=window,time_window=key,status='PASS'));continue
                ins=e.groupby('to_address').total_value.sum().reindex(addresses,fill_value=0.).to_numpy()
                outs=e.groupby('from_address').total_value.sum().reindex(addresses,fill_value=0.).to_numpy()
                vol=ins+outs
                degree=e.groupby('to_address').size().reindex(addresses,fill_value=0).to_numpy()+e.groupby('from_address').size().reindex(addresses,fill_value=0).to_numpy()
                close(n.node_volume_usdt,vol,'node_volume_from_T08');close(n.node_degree,degree,'node_degree_from_T08')
                require(n.community_id.notna().all() and pd.api.types.is_integer_dtype(n.community_id),label+': invalid community ID')
                cs=n.groupby('community_id').address.size();cv=n.assign(v=vol).groupby('community_id').v.sum()
                require(set(cs.index)==set(range(len(cs))),label+': community IDs not contiguous')
                close(n.community_size,n.community_id.map(cs),'community_size')
                close(n.community_volume_usdt,n.community_id.map(cv),'community_volume')
                require(n.is_giant_community.eq(n.community_id.eq(0)).all() and cs.loc[0]==cs.max(),label+': giant community mismatch')
                comm=n.set_index('address').community_id;src=e.from_address.map(comm);dst=e.to_address.map(comm)
                m=math.fsum(e.total_value);internal=math.fsum(e.loc[src.eq(dst),'total_value'])
                cout=pd.Series(outs,index=n.address).groupby(comm).sum();cin=pd.Series(ins,index=n.address).groupby(comm).sum()
                internal_c=e.loc[src.eq(dst)].assign(cid=src[src.eq(dst)]).groupby('cid').total_value.sum().reindex(cs.index,fill_value=0.)
                q=math.fsum(float(internal_c[c])/m-settings['louvain_resolution']*float(cout[c])*float(cin[c])/m**2 for c in cs.index)
                refs=dict(num_nodes=len(n),num_edges=len(e),total_volume_usdt=m,num_communities=len(cs),modularity=q,
                    hhi_volume=reference_hhi(vol),hhi_degree=reference_hhi(degree),hhi_community_volume=reference_hhi(cv.to_numpy()),hhi_community_nodes=reference_hhi(cs.to_numpy()),
                    gini_volume=reference_gini(vol),gini_degree=reference_gini(degree),entropy_volume=reference_entropy(vol),entropy_community_volume=reference_entropy(cv.to_numpy()),
                    internal_volume_ratio=internal/m,community_size_mean=cs.mean(),community_size_std=cs.to_numpy().std(ddof=0),community_size_median=cs.median(),community_size_max=cs.max(),singletons_count=int(cs.eq(1).sum()),
                    giant_community_nodes=cs.loc[0],giant_community_node_ratio=cs.loc[0]/len(n),giant_community_volume=cv.loc[0],giant_community_volume_ratio=cv.loc[0]/math.fsum(vol),
                    community_concentration_index=max(q,0)*reference_hhi(cv.to_numpy()))
                ranked=np.sort(vol)[::-1]
                for col,k in [('cr1_volume',1),('cr5_volume',5),('cr10_volume',10),('cr20_volume',20),('cr_top1pct_volume',max(1,math.ceil(.01*len(n)))),('cr_top5pct_volume',max(1,math.ceil(.05*len(n))))]:
                    refs[col]=math.fsum(ranked[:k])/math.fsum(vol)
                for col,value in refs.items():close(s[col],value,col)
                ranked_c=sorted(cs.index,key=lambda c:(-cv.loc[c],c))[:5]
                for rank,c in enumerate(ranked_c,1):
                    expected_top.append(dict(window_type=window,time_window=key,community_id=c,community_size=cs.loc[c],community_volume_usdt=cv.loc[c],community_volume_share=cv.loc[c]/math.fsum(vol),volume_rank=rank))
                checked.append(dict(window_type=window,time_window=key,status='PASS'))
            shape=summary['shapes'][window]
            require(shape['snapshots']==len(calendar) and shape['node_rows']==len(nodes),'Summary shape mismatch')
            if window=='daily':daily=snapshots
            print(f'T11 independent reference {window}: {len(calendar)} windows PASS',flush=True)
        keys=['window_type','time_window','volume_rank']
        expected=pd.DataFrame(expected_top).sort_values(keys).reset_index(drop=True)
        top=pd.read_parquet(folder/'top_communities_summary.parquet').sort_values(keys).reset_index(drop=True)
        require(len(top)==len(expected),'Top community row count mismatch')
        for c in keys:require(top[c].tolist()==expected[c].tolist(),'Top community key mismatch')
        for c in ['community_id','community_size','community_volume_usdt','community_volume_share']:close(top[c],expected[c],'top_'+c)
        # Independent regime construction by date lookup, not production shifts.
        daily=daily.sort_values('time_window').reset_index(drop=True);dates=pd.to_datetime(daily.time_window)
        threshold=float(np.quantile(daily.total_volume_usdt,settings['rq4_volume_quantile']))
        high=set(dates[daily.total_volume_usdt.ge(threshold)]);h=settings['rq4_forward_days'];last=dates.iloc[-1]
        names=[];pre_flags=[]
        for date in dates:
            pre=any(date+pd.Timedelta(days=i) in high for i in range(1,h+1));pre_flags.append(pre)
            names.append('right_censored' if date+pd.Timedelta(days=h)>last else 'high_volume' if date in high else 'pre_high_volume' if pre else 'baseline')
        regimes=pd.read_parquet(folder/'rq4_daily_regimes.parquet')
        require(regimes.time_window.tolist()==daily.time_window.tolist() and regimes.regime.tolist()==names,'Regime/calendar mismatch')
        close(regimes.high_volume_threshold_usdt,threshold,'volume_proxy_threshold')
        require(regimes.is_high_volume.tolist()==dates.isin(high).tolist(),'High-volume flags mismatch')
        require(regimes.has_high_volume_in_forward_window.tolist()==pre_flags,'Forward-window flags mismatch')
        require(regimes.complete_forward_window.tolist()==[x!='right_censored' for x in names],'Censor flags mismatch')
        require(regimes.forward_days.eq(h).all(),'Forward horizon mismatch')
        comparison=pd.read_parquet(folder/'rq4_comparison.parquet')
        require(comparison.metric.tolist()==METRICS and comparison.comparison.eq('pre_high_volume_vs_baseline').all(),'RQ4 metric or comparison mismatch')
        raw=[]
        for row in comparison.itertuples():
            samples={name:daily.loc[np.array(names)==name,row.metric].to_numpy() for name in ['baseline','pre_high_volume','high_volume']}
            for name,x in samples.items():
                require(getattr(row,'n_'+name)==len(x),'RQ4 N mismatch')
                close(getattr(row,'mean_'+name),np.mean(x),'rq4_mean_'+name)
            base=samples['baseline'];pre=samples['pre_high_volume'];p=float(ttest_ind(pre,base,equal_var=False).pvalue)
            raw.append(p);close(row.p_welch_iid_exploratory,p,'rq4_welch')
            close(row.pre_minus_baseline,float(pre.mean()-base.mean()),'rq4_mean_difference')
            close(row.relative_change_pct,float(100*(pre.mean()/base.mean()-1)),'rq4_relative_change')
        # Holm via adjusted-p closed-form maximum across smaller sorted hypotheses.
        order=np.argsort(raw);adjusted=np.zeros(len(raw))
        for position,index in enumerate(order):adjusted[index]=min(1.,max((len(raw)-j)*raw[order[j]] for j in range(position+1)))
        close(comparison.p_holm_exploratory,adjusted,'rq4_holm')
        validation=pd.read_parquet(folder/'t11_validation.parquet')
        require(validation[['window_type','time_window']].to_dict('records')==[{k:r[k] for k in ['window_type','time_window']} for r in checked],'Validation calendar mismatch')
        require(validation.status.eq('PASS').all(),'Production validation failed')
        expected_validation=pd.concat(snapshot_tables,ignore_index=True)
        for col in ['num_nodes','num_edges','modularity','hhi_volume','gini_volume','days_in_window']:
            close(validation[col],expected_validation[col],'validation_'+col)
        for col in ['is_partial_week','eligible_for_regression']:
            require(validation[col].tolist()==expected_validation[col].tolist(),'Validation metadata mismatch')
        require(verified_t08_inputs(cfg)==before,'T08 changed during review')
        require(all(sha256(folder/name)==h for name,h in output_hashes.items()),'Artifacts changed during review')
        require(all(sha256(ROOT/p)==h for p,h in summary['source_code_hashes'].items()),'Source changed during review')
        report=dict(all_pass=True,windows_checked=len(checked),checks=checked,maximum_absolute_errors=errors,
            tolerances=dict(absolute=1e-7,relative=1e-10),output_hashes=output_hashes,input_hashes=before,
            validator_sha256=sha256(Path(__file__)),reference='Edge-based independent formulas; no production T11 metric imports',
            validity_scope='Mathematical/data validation, not confirmation of market stress, ownership or optimal partition')
        write_json(folder/'t11_review.json',report)
        summary.update(ready_for_downstream=True,independent_review_pass=True,review_file='data/processed/t11/t11_review.json')
        write_json(folder/'t11_summary.json',summary)
        return report
    except Exception as exc:
        write_json(folder/'t11_review.json',dict(all_pass=False,error=str(exc),validator_sha256=sha256(Path(__file__))))
        summary.update(ready_for_downstream=False,independent_review_pass=False)
        write_json(folder/'t11_summary.json',summary)
        raise


def main():
    if sys.platform.startswith('win'):sys.stdout.reconfigure(encoding='utf-8')
    report=validate_release()
    print(json.dumps(dict(all_pass=report['all_pass'],windows_checked=report['windows_checked']),indent=2))


if __name__=='__main__':main()
