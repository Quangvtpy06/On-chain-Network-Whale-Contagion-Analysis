"""Đối chiếu HHI/CCI ba ngày trước các đợt stress T13 với các mốc yên bình."""
import argparse
import importlib.metadata

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from src import rq4_stress_lead as rq4
from src.analysis_release import frame_hash
from src.forecast_inputs import ROOT, file_hash, hash_paths, json_write, local_path, read_config, require, verify_hashes

SOURCES = ['RQ4_Stress_Lead.py', 'src/rq4_stress_lead.py', 'scripts/validate_rq4_stress_lead.py']


def report(cfg, results, episodes, anchors, input_hashes, revision):
    primary = results[results.analysis.eq('primary_calendar_block')]
    lines = ['# RQ4 — Tập trung cộng đồng trước stress thị trường', '',
             f"Protocol `{cfg['protocol_id']}`. T13 stress ETH/USDT RV > P90 toàn kỳ, "
             f'{int(anchors.stress_day.sum())} ngày, gộp thành {len(episodes)} đợt; '
             f'{int(episodes.eligible.sum())} onset có đủ 3 ngày trước và 3 ngày sau để so sánh.',
             f"T13 artifact revision `{revision}`; T11 snapshot daily đã tái lập. "
             'Đây là phân loại hồi cứu, không phải nhãn stress biết trước tại ngày quan sát.',
             'Các ngày stress cách nhau tối đa 3 ngày thuộc cùng một đợt. Mỗi đợt chỉ có một onset; '
             'không nhân số quan sát bằng số ngày stress trong cùng đợt.',
             f"Mốc đối chứng: {int(anchors.quiet_anchor.sum())} ngày không có stress trong ±3 ngày, "
             'đủ lịch quan sát. Mỗi chỉ số là trung bình D−3,D−2,D−1; không dùng giá trị ngày stress D.',
             'Bootstrap lấy khối 14 ngày lịch của cặp nhãn/giá trị để giữ phụ thuộc thời gian; '
             '5.000 lượt, kiểm định một phía tăng, Holm cho 2 chỉ số cộng đồng.', '',
             '| Chỉ số | Trước stress | Đối chứng | Chênh lệch | 95% CI bootstrap | p tăng | p Holm |',
             '|---|---:|---:|---:|---|---:|---:|']
    for r in primary.itertuples():
        lines.append(f'| {r.metric} | {r.event_pre_mean:.6f} | {r.control_pre_mean:.6f} | '
                     f'{r.difference:+.6f} ({r.relative_difference_pct:+.2f}%) | '
                     f'[{r.ci_lower:.6f}, {r.ci_upper:.6f}] | {r.p_increase:.4f} | {r.p_increase_holm:.4f} |')
    any_positive = bool(primary.evidence_of_pre_stress_increase_5pct.any())
    lines += ['', ('Có bằng chứng thăm dò rằng ít nhất một chỉ số tập trung cộng đồng tăng trước stress '
                   'sau Holm.' if any_positive else
                   'Chưa tìm thấy bằng chứng rằng HHI hoặc CCI tập trung cộng đồng tăng trước onset stress '
                   'ở mức 5% sau Holm. Đây không phải bằng chứng chúng luôn không tăng.'), '',
              'Đối chiếu độ nhạy: mỗi onset ghép một ngày yên bình cùng thứ trong tuần, cách tối đa 60 ngày, '
              'không dùng lại ngày đối chứng; lấy mẫu khối 3 đợt. Đây là phân tích bổ sung, không chọn lại thiết kế theo kết quả.', '',
              '| Chỉ số | Cặp | Chênh lệch ghép | 95% CI | p tăng | p Holm (độ nhạy) |',
              '|---|---:|---:|---|---:|---:|']
    for r in results[results.analysis.eq('matched_weekday_60d_sensitivity')].itertuples():
        lines.append(f'| {r.metric} | {r.n_matched_pairs} | {r.difference:+.6f} | '
                     f'[{r.ci_lower:.6f}, {r.ci_upper:.6f}] | {r.p_increase:.4f} | {r.p_increase_holm:.4f} |')
    lines += ['', 'Giới hạn: ngưỡng stress P90 toàn kỳ dùng cho phân tích hồi cứu; khoảng tin cậy block '
              'phụ thuộc giả định khối 14 ngày/3 đợt, mẫu chỉ có số đợt hữu hạn. '
              'Đây là liên hệ đi trước theo lịch, không chứng minh CCI/HHI gây stress hoặc dự báo ngoài mẫu.',
              'HHI/CCI T11 mô tả mạng con transfer USDT đã net từ 500.000 USDT. '
              'Khác biệt về cấu trúc hoạt động, thành phần ví, hoặc volume cũng có thể ảnh hưởng chỉ số.',
              'Gini theo nút và CR top 5% không được dùng thay HHI/CCI cộng đồng. '
              'Kết quả trước high-volume của T11 là một phép so sánh khác.',
              '', 'Nguồn SHA-256:', '']
    lines += [f'- `{k}`: `{v}`' for k,v in sorted(input_hashes.items())]
    return '\n'.join(lines)+'\n'


def figure(results, path):
    primary=results[results.analysis.eq('primary_calendar_block')]
    sensitivity=results[results.analysis.eq('matched_weekday_60d_sensitivity')]
    labels={'hhi_community_volume':'HHI community volume','community_concentration_index':'Community concentration index'}
    fig,axes=plt.subplots(1,2,figsize=(11,3.6),constrained_layout=True)
    for ax,metric in zip(axes,labels):
        for y,(frame,color,name) in enumerate([(primary,'#167A83','Calendar blocks'),
                                               (sensitivity,'#DA7B36','Matched sensitivity')]):
            r=frame[frame.metric.eq(metric)].iloc[0]
            ax.errorbar(r.difference,y,xerr=[[r.difference-r.ci_lower],[r.ci_upper-r.difference]],
                        fmt='o',color=color,capsize=4,label=name)
        ax.axvline(0,color='#56646A',lw=1)
        ax.set(title=labels[metric],xlabel='Mean before stress − quiet control',
               yticks=[0,1],yticklabels=['14-day blocks','Matched controls'],ylim=(-.55,1.55))
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.tick_params(axis='x',labelsize=8)
    fig.savefig(path,dpi=160,metadata={'Software':'crypto-analysis'})
    plt.close(fig)


def run(config='config/rq4_stress_lead.yaml',output_dir=None):
    config=local_path(config);cfg=read_config(config)
    require(cfg['protocol_id']=='rq4_t13_stress_t11_lead_v1','Unsupported RQ4 protocol')
    require(cfg['primary_metrics']==['hhi_community_volume','community_concentration_index'],
            'Primary RQ4 metrics changed')
    sources=hash_paths([ROOT/n for n in SOURCES]+[config])
    t13,t11,inputs,revision,threshold=rq4.load(cfg)
    anchors,episodes,matched,results=rq4.analyse(t13,t11,cfg)
    second=rq4.analyse(t13,t11,cfg)
    names={'rq4_stress_anchor_days.parquet':anchors,'rq4_stress_episodes.parquet':episodes,
           'rq4_matched_controls.parquet':matched,'rq4_lead_results.parquet':results}
    repeats={n:frame_hash(f)==frame_hash(s) for (n,f),s in zip(names.items(),second)}
    require(all(repeats.values()),'Two calculations differ')
    checks=rq4.validate_outputs(t13,t11,cfg,anchors,episodes,matched,results)
    checks=pd.concat([checks,pd.DataFrame([dict(check='two_calculations_identical',status='PASS',detail='4 tables')])],ignore_index=True)
    names['rq4_validation.parquet']=checks
    out=local_path(output_dir or cfg['output_dir']);out.mkdir(parents=True,exist_ok=True)
    for name,frame in names.items():frame.to_parquet(out/name,index=False)
    md=out/'rq4_stress_lead_report.md';md.write_text(report(cfg,results,episodes,anchors,inputs,revision),encoding='utf-8')
    png=out/'rq4_stress_lead.png';figure(results,png)
    verify_hashes(sources);verify_hashes(inputs)
    primary=results[results.analysis.eq('primary_calendar_block')]
    summary=dict(protocol_id=cfg['protocol_id'],task='RQ4',computation_validated=True,
                 independent_review_required=True,independent_review_pass=False,
                 stress_definition=dict(source='T13_RV_P90_full_period',threshold=threshold,days=int(anchors.stress_day.sum()),
                                        episodes=len(episodes),eligible_episodes=int(episodes.eligible.sum()),
                                        pinned_hf_revision=revision),
                 inference=dict(evidence_of_pre_stress_increase_5pct=bool(primary.evidence_of_pre_stress_increase_5pct.any()),
                                rq4_temporal_association_tested=True,causal_claim=False,
                                prospective_forecast_validated=False),
                 parameters=cfg,source_config_sha256=sources,input_sha256=inputs,
                 versions={p:importlib.metadata.version(p) for p in ['pandas','numpy','statsmodels','pyarrow']},
                 content_hashes={n:frame_hash(f) for n,f in names.items()},
                 output_sha256={p.name:file_hash(p) for p in [out/n for n in names]+[md,png]})
    json_write(out/'rq4_stress_lead_summary.json',summary)
    print(f"RQ4: {len(episodes)} episodes, {int(episodes.eligible.sum())} eligible, "
          f"{int(anchors.quiet_anchor.sum())} quiet anchors; primary increase evidence="
          f"{summary['inference']['evidence_of_pre_stress_increase_5pct']}; output={out.relative_to(ROOT)}")
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='config/rq4_stress_lead.yaml')
    parser.add_argument('--output-dir')
    args=parser.parse_args();run(args.config,args.output_dir)
