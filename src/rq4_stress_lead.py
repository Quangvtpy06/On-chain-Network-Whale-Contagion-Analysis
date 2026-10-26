"""RQ4: chỉ số cộng đồng T11 trước onset stress ETH/USDT T13."""
import json

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests

from src.forecast_inputs import ROOT, file_hash, local_path, require


def input_files(cfg):
    return {key: local_path(cfg[key]) for key in ['t13_regimes', 't13_manifest', 't11_daily', 't11_summary', 't11_review']}


def load(cfg):
    paths = input_files(cfg)
    before = {p.relative_to(ROOT).as_posix(): file_hash(p) for p in paths.values()}
    manifest = json.loads(paths['t13_manifest'].read_text(encoding='utf-8'))
    row = next(r for r in manifest['reproduction']['tables'] if r['file'] == paths['t13_regimes'].name)
    require(manifest['acceptance']['core_calculation_pass'] is True and
            manifest['acceptance']['independent_formula_review_pass'] is True and
            manifest['inputs']['all_matched_pinned_HF_revision'] is True, 'T13 review not accepted')
    require(file_hash(paths['t13_regimes']) == row['hf_sha256'] and row['matches_HF'] is True,
            'T13 regimes differ from pinned HF artifact')
    summary = json.loads(paths['t11_summary'].read_text(encoding='utf-8'))
    review = json.loads(paths['t11_review'].read_text(encoding='utf-8'))
    require(summary['ready_for_downstream'] is True and summary['independent_review_pass'] is True
            and review['all_pass'] is True, 'T11 review not accepted')
    # The accepted T11 reproducibility record binds the actual daily Parquet bytes.
    repro_path = ROOT/'data/processed/t11/t11_reproducibility.json'
    repro = json.loads(repro_path.read_text(encoding='utf-8'))
    expected = repro['hashes'][paths['t11_daily'].name]
    require(repro['all_match'] is True and expected['run1'] == expected['run2'] == file_hash(paths['t11_daily']),
            'T11 daily snapshot differs from accepted reproduction')
    before[repro_path.relative_to(ROOT).as_posix()] = file_hash(repro_path)
    t13 = pd.read_parquet(paths['t13_regimes'])
    t11 = pd.read_parquet(paths['t11_daily'])
    for frame, name in [(t13, 'T13'), (t11, 'T11')]:
        key = 'date' if name == 'T13' else 'time_window'
        frame['date_utc'] = pd.to_datetime(frame[key], utc=True, errors='raise').dt.as_unit('ns')
        require(frame.date_utc.notna().all() and frame.date_utc.eq(frame.date_utc.dt.normalize()).all(),
                f'{name} dates not UTC days')
        require(not frame.date_utc.duplicated().any(), f'{name} duplicate days')
        frame.sort_values('date_utc', inplace=True)
        frame.reset_index(drop=True, inplace=True)
    require(t13.date_utc.equals(t11.date_utc), 'T13/T11 calendars differ')
    require(t13.date_utc.equals(pd.Series(pd.date_range('2025-01-01','2026-10-17',tz='UTC')).dt.as_unit('ns')),
            'Expected 655-day calendar missing')
    require(t11.window_type.eq('daily').all() and t11.eligible_for_regression.astype(bool).all(),
            'Invalid T11 daily window')
    threshold = float(t13.rv.quantile(.9))
    require(np.isclose(threshold, 0.048694850425840486, rtol=1e-10, atol=1e-12),
            'T13 P90 differs from accepted report')
    require(np.array_equal(t13.regime.eq(cfg['stress_regime']).to_numpy(),
                           t13.rv.to_numpy(float) > threshold), 'Stress labels do not match T13 P90')
    require(int(t13.regime.eq(cfg['stress_regime']).sum()) == 66, 'Unexpected T13 stress count')
    for metric in cfg['primary_metrics']:
        require(np.isfinite(t11[metric].to_numpy(float)).all(), 'Missing T11 metric: '+metric)
    for name, digest in before.items():
        require(file_hash(ROOT/name) == digest, 'Changed input while loading: '+name)
    return t13, t11, dict(before), manifest['dataset']['reviewed_revision'], threshold


def build_anchors(t13, t11, cfg):
    n = len(t13); stress = t13.regime.eq(cfg['stress_regime']).to_numpy(bool)
    gap = int(cfg['stress_cluster_gap_days']); pre = sorted(map(int,cfg['pre_days']))
    pad = int(cfg['quiet_padding_days'])
    require(pre == [1,2,3] and gap == 3 and pad == 3, 'Unsupported/frozen RQ4 calendar')
    episodes = []
    for i in np.flatnonzero(stress):
        if not episodes or i - episodes[-1][-1] > gap:
            episodes.append([int(i)])
        else:
            episodes[-1].append(int(i))
    starts = {ep[0] for ep in episodes if ep[0] >= max(pre) and ep[0] < n-pad}
    quiet = {i for i in range(max(pre), n-pad) if not stress[i-pad:i+pad+1].any()}
    require(starts.isdisjoint(quiet), 'Event/quiet anchors overlap')
    values = {'date':t13.date_utc, 'regime':t13.regime, 'rv':t13.rv,
              'stress_day':stress, 'stress_onset':np.array([i in starts for i in range(n)]),
              'quiet_anchor':np.array([i in quiet for i in range(n)]),
              'anchor_status':['stress_onset' if i in starts else 'quiet' if i in quiet else 'excluded' for i in range(n)]}
    for metric in cfg['primary_metrics']:
        v = t11[metric].to_numpy(float)
        mean = np.full(n,np.nan)
        for i in range(max(pre),n):
            selected = v[[i-j for j in pre]]
            if np.isfinite(selected).all():mean[i]=float(selected.mean())
        values['pre3_'+metric]=mean
    anchors = pd.DataFrame(values)
    episode_rows = []
    for j, ep in enumerate(episodes,1):
        start=ep[0]; end=ep[-1]
        episode_rows.append(dict(episode_id=j,onset_date=t13.date_utc.iloc[start],last_stress_date=t13.date_utc.iloc[end],
                                 n_stress_days=len(ep),span_calendar_days=end-start+1,
                                 eligible=bool(start in starts),excluded_reason='' if start in starts else 'boundary_censored'))
    episode_table=pd.DataFrame(episode_rows)
    require(anchors.stress_onset.sum() == episode_table.eligible.sum(),
            'Stress episode accounting failed')
    return anchors, episode_table


def calendar_block_bootstrap(values, event, quiet, cfg):
    """Bootstrap 14-day calendar blocks of anchor/value pairs; no IID-day assumption."""
    n=len(values); boot=cfg['bootstrap']; length=int(boot['block_calendar_days']);reps=int(boot['resamples'])
    rng=np.random.default_rng(int(boot['seed']))
    starts=rng.integers(0,n,size=(reps,int(np.ceil(n/length))))
    indices=((starts[:,:,None]+np.arange(length))%n).reshape(reps,-1)[:,:n]
    draw_event=event[indices];draw_quiet=quiet[indices]
    n_event=draw_event.sum(axis=1);n_quiet=draw_quiet.sum(axis=1)
    okay=(n_event>0)&(n_quiet>0)
    diffs=np.full(reps,np.nan)
    v=values[indices]
    diffs[okay]=(np.where(draw_event,v,0).sum(axis=1)[okay]/n_event[okay]
                 -np.where(draw_quiet,v,0).sum(axis=1)[okay]/n_quiet[okay])
    return diffs[np.isfinite(diffs)]


def bootstrap_inference(estimate, replicates, alpha):
    require(len(replicates)>=1000,'Insufficient valid bootstrap draws')
    lo,hi=np.quantile(replicates,[alpha/2,1-alpha/2])
    centered=replicates-estimate
    p_increase=(1+np.sum(centered>=estimate))/(len(replicates)+1)
    p_two=(1+np.sum(np.abs(centered)>=abs(estimate)))/(len(replicates)+1)
    return float(lo),float(hi),float(p_increase),float(p_two)


def matched_controls(anchors,cfg):
    spec=cfg['matched_sensitivity'];maxdistance=int(spec['max_calendar_distance_days'])
    event_indices=list(np.flatnonzero(anchors.stress_onset));quiet_indices=list(np.flatnonzero(anchors.quiet_anchor))
    used=set();rows=[]
    for i in event_indices:
        candidates=[j for j in quiet_indices if j not in used and abs(j-i)<=maxdistance
                    and (not spec['same_weekday'] or (j-i)%7==0)]
        if not candidates:continue
        j=min(candidates,key=lambda x:(abs(x-i),x))
        used.add(j)
        row=dict(onset_date=anchors.date.iloc[i],control_date=anchors.date.iloc[j],
                 calendar_distance_days=abs(j-i),same_weekday=(j-i)%7==0)
        for metric in cfg['primary_metrics']:
            col='pre3_'+metric
            row[metric+'_event']=float(anchors[col].iloc[i])
            row[metric+'_control']=float(anchors[col].iloc[j])
            row[metric+'_difference']=row[metric+'_event']-row[metric+'_control']
        rows.append(row)
    require(bool(rows), 'No matched controls')
    return pd.DataFrame(rows)


def matched_bootstrap(diffs,cfg):
    n=len(diffs);spec=cfg['matched_sensitivity'];block=int(spec['block_episodes']);boot=cfg['bootstrap']
    rng=np.random.default_rng(int(boot['seed'])+1)
    starts=rng.integers(0,n,size=(int(boot['resamples']),int(np.ceil(n/block))))
    indices=((starts[:,:,None]+np.arange(block))%n).reshape(len(starts),-1)[:,:n]
    return diffs[indices].mean(axis=1)


def analyse(t13,t11,cfg):
    anchors,episodes=build_anchors(t13,t11,cfg)
    matched=matched_controls(anchors,cfg) if cfg['matched_sensitivity']['enabled'] else pd.DataFrame()
    event=anchors.stress_onset.to_numpy(bool);quiet=anchors.quiet_anchor.to_numpy(bool)
    require(int(event.sum())>=cfg['bootstrap']['min_event_episodes'],'Too few stress episodes')
    rows=[]
    for metric in cfg['primary_metrics']:
        values=anchors['pre3_'+metric].to_numpy(float)
        require(np.isfinite(values[event|quiet]).all(), 'Missing pre-event metric')
        estimate=float(values[event].mean()-values[quiet].mean())
        reps=calendar_block_bootstrap(values,event,quiet,cfg)
        lo,hi,p_increase,p_two=bootstrap_inference(estimate,reps,float(cfg['bootstrap']['alpha']))
        rows.append(dict(metric=metric,analysis='primary_calendar_block',n_stress_episodes=int(event.sum()),
                         n_quiet_anchors=int(quiet.sum()),n_matched_pairs=0,
                         event_pre_mean=float(values[event].mean()),control_pre_mean=float(values[quiet].mean()),
                         difference=estimate,relative_difference_pct=float(100*estimate/values[quiet].mean()),
                         ci_lower=lo,ci_upper=hi,p_increase=p_increase,p_two_sided=p_two,
                         valid_bootstrap_draws=len(reps),bootstrap_unit='14_calendar_days'))
        diffs=matched[metric+'_difference'].to_numpy(float)
        m_est=float(diffs.mean());m_reps=matched_bootstrap(diffs,cfg)
        mlo,mhi,mp,mp_two=bootstrap_inference(m_est,m_reps,float(cfg['bootstrap']['alpha']))
        rows.append(dict(metric=metric,analysis='matched_weekday_60d_sensitivity',
                         n_stress_episodes=int(event.sum()),n_quiet_anchors=int(quiet.sum()),n_matched_pairs=len(matched),
                         event_pre_mean=float(matched[metric+'_event'].mean()),
                         control_pre_mean=float(matched[metric+'_control'].mean()),difference=m_est,
                         relative_difference_pct=float(100*m_est/matched[metric+'_control'].mean()),
                         ci_lower=mlo,ci_upper=mhi,p_increase=mp,p_two_sided=mp_two,
                         valid_bootstrap_draws=len(m_reps),bootstrap_unit='3_adjacent_episodes'))
    results=pd.DataFrame(rows)
    results['p_increase_holm']=np.nan
    mask=results.analysis.eq('primary_calendar_block')
    results.loc[mask,'p_increase_holm']=multipletests(results.loc[mask,'p_increase'],method='holm')[1]
    matched_mask=results.analysis.eq('matched_weekday_60d_sensitivity')
    results.loc[matched_mask,'p_increase_holm']=multipletests(results.loc[matched_mask,'p_increase'],method='holm')[1]
    results['evidence_of_pre_stress_increase_5pct']=mask & results.p_increase_holm.lt(.05) & results.difference.gt(0)
    return anchors,episodes,matched,results


def validate_outputs(t13,t11,cfg,anchors,episodes,matched,results):
    rows=[]
    def check(name,condition,detail=''):
        require(bool(condition),name+': '+str(detail))
        rows.append(dict(check=name,status='PASS',detail=str(detail)))
    check('same_655_day_utc_calendar',len(anchors)==655 and anchors.date.equals(t13.date_utc))
    check('exact_66_t13_stress_days',int(anchors.stress_day.sum())==66)
    check('episodes_account_for_all_stress_days',int(episodes.n_stress_days.sum())==66)
    starts=np.flatnonzero(anchors.stress_onset)
    check('stress_onsets_separated_by_more_than_3_days',bool((np.diff(starts)>3).all()))
    check('event_pre_days_are_nonstress',all(not anchors.stress_day.iloc[i-3:i].any() for i in starts))
    quiet=np.flatnonzero(anchors.quiet_anchor)
    check('quiet_anchors_have_no_stress_within_3_days',all(not anchors.stress_day.iloc[i-3:i+4].any() for i in quiet))
    check('event_and_quiet_disjoint',not (anchors.stress_onset & anchors.quiet_anchor).any())
    check('no_boundary_contamination',bool((starts>=3).all() and (starts<len(anchors)-3).all()
                                           and (quiet>=3).all() and (quiet<len(anchors)-3).all()))
    check('matched_weekday_without_reuse',matched.control_date.is_unique and matched.same_weekday.all()
          and matched.calendar_distance_days.le(cfg['matched_sensitivity']['max_calendar_distance_days']).all())
    check('all_four_results_finite',len(results)==4 and np.isfinite(results[['difference','ci_lower','ci_upper','p_increase']]).all().all())
    check('holm_not_below_raw',bool((results.p_increase_holm+1e-12>=results.p_increase).all()))
    for metric in cfg['primary_metrics']:
        col='pre3_'+metric;source=t11[metric].to_numpy(float)
        positions=[3,100,300,654]
        check('pre3_lookup_'+metric,all(np.isclose(anchors[col].iloc[i],np.mean(source[i-3:i])) for i in positions))
        row=results[results.metric.eq(metric)&results.analysis.eq('primary_calendar_block')].iloc[0]
        check('direct_difference_'+metric,np.isclose(row.difference,
            anchors.loc[anchors.stress_onset,col].mean()-anchors.loc[anchors.quiet_anchor,col].mean()))
    return pd.DataFrame(rows)
