"""Đối chiếu RQ4 bằng tiến trình khác và phép tính lịch/ngày trước độc lập."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd

import RQ4_Stress_Lead as release
from src import rq4_stress_lead as rq4
from src.analysis_release import frame_hash
from src.forecast_inputs import file_hash,hash_paths,json_write,local_path,read_config,require,verify_hashes


def independent_arithmetic(t13,t11,anchors,episodes,matched,results,cfg):
    stress=(t13.regime.to_numpy()=='Stress')
    indices=np.flatnonzero(stress)
    starts=[];last=-99
    for i in indices:
        if i-last>3:starts.append(i)
        last=i
    eligible=[i for i in starts if 3<=i<len(stress)-3]
    controls=[i for i in range(3,len(stress)-3) if not np.any(stress[i-3:i+4])]
    require(np.array_equal(np.flatnonzero(anchors.stress_onset),eligible),'Independent onset dates differ')
    require(np.array_equal(np.flatnonzero(anchors.quiet_anchor),controls),'Independent control dates differ')
    require(len(episodes)==len(starts) and int(episodes.n_stress_days.sum())==len(indices),
            'Independent episode count differs')
    checks=[]
    for metric in cfg['primary_metrics']:
        source=t11[metric].to_numpy(float)
        direct=np.array([np.mean(source[i-3:i]) if i>=3 else np.nan for i in range(len(stress))])
        require(np.allclose(anchors['pre3_'+metric],direct,equal_nan=True,atol=1e-12),
                'Independent three-day lookup differs: '+metric)
        row=results[results.metric.eq(metric)&results.analysis.eq('primary_calendar_block')].iloc[0]
        estimate=direct[eligible].mean()-direct[controls].mean()
        require(np.isclose(estimate,row.difference,atol=1e-12),'Independent primary effect differs')
        for item in matched.itertuples():
            i=anchors.index[anchors.date.eq(item.onset_date)][0]
            j=anchors.index[anchors.date.eq(item.control_date)][0]
            require(i in eligible and j in controls and (i-j)%7==0 and abs(i-j)<=60,'Invalid independent pair')
            require(np.isclose(direct[i]-direct[j],getattr(item,metric+'_difference'),atol=1e-12),
                    'Independent matched difference differs')
        checks.append(dict(check='independent_onsets_quiet_three_day_means_and_pairs',metric=metric,status='PASS'))
    return checks


def validate(config='config/rq4_stress_lead.yaml',output_dir=None):
    path=local_path(config);cfg=read_config(path);out=local_path(output_dir or cfg['output_dir'])
    summary_path=out/'rq4_stress_lead_summary.json'
    summary=json.loads(summary_path.read_text(encoding='utf-8'))
    require(summary['computation_validated'] is True and summary['parameters']==cfg and
            summary['protocol_id']==cfg['protocol_id'],'Invalid RQ4 protocol/summary')
    require(summary['inference']['causal_claim'] is False and
            summary['inference']['prospective_forecast_validated'] is False,'Unsupported RQ4 claim')
    sources=hash_paths([ROOT/n for n in release.SOURCES]+[path])
    require(sources==summary['source_config_sha256'],'RQ4 source/config differs')
    t13,t11,inputs,revision,threshold=rq4.load(cfg)
    require(inputs==summary['input_sha256'],'RQ4 input hashes differ')
    tables=rq4.analyse(t13,t11,cfg)
    anchors,episodes,matched,results=tables
    checks=rq4.validate_outputs(t13,t11,cfg,*tables)
    checks=pd.concat([checks,pd.DataFrame([dict(check='two_calculations_identical',status='PASS',detail='4 tables')])],ignore_index=True)
    names={'rq4_stress_anchor_days.parquet':anchors,'rq4_stress_episodes.parquet':episodes,
           'rq4_matched_controls.parquet':matched,'rq4_lead_results.parquet':results,'rq4_validation.parquet':checks}
    require(set(summary['content_hashes'])==set(names),'Incomplete content map')
    require(set(summary['output_sha256'])==set(names)|{'rq4_stress_lead_report.md','rq4_stress_lead.png'},
            'Incomplete output map')
    for name,expected in summary['output_sha256'].items():
        require(file_hash(out/name)==expected,'Changed RQ4 output: '+name)
    for name,frame in names.items():
        require(frame_hash(pd.read_parquet(out/name))==frame_hash(frame)==summary['content_hashes'][name],
                'Recomputation differs: '+name)
    require((out/'rq4_stress_lead_report.md').read_text(encoding='utf-8')==
            release.report(cfg,results,episodes,anchors,inputs,revision),'Report differs')
    independent=independent_arithmetic(t13,t11,anchors,episodes,matched,results,cfg)
    verify_hashes(sources);verify_hashes(inputs)
    summary['independent_review_pass']=True
    summary['rq4_answered_within_retrospective_scope']=True
    json_write(summary_path,summary)
    review=dict(all_pass=True,protocol_id=cfg['protocol_id'],source_config_sha256=sources,input_sha256=inputs,
                summary_sha256=file_hash(summary_path),output_sha256=summary['output_sha256'],
                independent_checks=independent,causal_claim=False,prospective_forecast_validated=False)
    json_write(out/'rq4_stress_lead_independent_review.json',review)
    return review


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='config/rq4_stress_lead.yaml')
    parser.add_argument('--output-dir');args=parser.parse_args()
    review=validate(args.config,args.output_dir)
    print(f"RQ4 independent review: {review['all_pass']}, checks={len(review['independent_checks'])}")
