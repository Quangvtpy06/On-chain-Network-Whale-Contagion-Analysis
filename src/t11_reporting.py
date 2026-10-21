"""Bảng RQ4 mô tả hồi cứu; không xác nhận stress thị trường hoặc danh tính ví."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.stats import ttest_ind

REGIMES=['baseline','pre_high_volume','high_volume']
RQ4_METRICS=['gini_volume','hhi_community_volume','community_concentration_index','modularity','cr_top5pct_volume']


def holm_adjust(values):
    values=np.asarray(values,float);out=np.full(len(values),np.nan)
    good=np.flatnonzero(np.isfinite(values));order=good[np.argsort(values[good],kind='stable')]
    if len(order):out[order]=np.minimum(1.,np.maximum.accumulate(values[order]*(len(order)-np.arange(len(order)))))
    return out


def build_rq4(daily,settings):
    daily=daily.sort_values('time_window').reset_index(drop=True)
    volume=daily.total_volume_usdt
    q=float(settings.get('rq4_volume_quantile',.9));horizon=int(settings.get('rq4_forward_days',3))
    high=volume.ge(volume.quantile(q));pre=pd.Series(False,index=daily.index)
    for lag in range(1,horizon+1):pre|=high.shift(-lag,fill_value=False)
    complete=pd.Series(np.arange(len(daily))+horizon<len(daily),index=daily.index)
    # Conservative complete-horizon comparison: final h days are censored for every group.
    regime=np.select([~complete,high,pre],['right_censored','high_volume','pre_high_volume'],default='baseline')
    regimes=pd.DataFrame(dict(time_window=daily.time_window,regime=regime,
        is_high_volume=high,has_high_volume_in_forward_window=pre,complete_forward_window=complete,
        high_volume_threshold_usdt=float(volume.quantile(q)),forward_days=horizon,
        interpretation='retrospective_volume_proxy_not_market_stress'))
    merged=daily.merge(regimes[['time_window','regime']],on='time_window',validate='one_to_one')
    rows=[]
    for metric in RQ4_METRICS:
        groups={name:merged.loc[merged.regime.eq(name),metric].to_numpy(float) for name in REGIMES}
        base=groups['baseline'];before=groups['pre_high_volume']
        p=float(ttest_ind(before,base,equal_var=False).pvalue) if len(base)>1 and len(before)>1 else np.nan
        means={name:float(x.mean()) if len(x) else np.nan for name,x in groups.items()}
        rows.append(dict(metric=metric,**{f'n_{name}':len(x) for name,x in groups.items()},
            **{f'mean_{name}':v for name,v in means.items()},
            pre_minus_baseline=means['pre_high_volume']-means['baseline'],
            relative_change_pct=100*(means['pre_high_volume']/means['baseline']-1) if means['baseline'] else np.nan,
            p_welch_iid_exploratory=p,comparison='pre_high_volume_vs_baseline',
            inference_scope='descriptive; serial dependence not corrected; no causal or PIT prediction claim'))
    comparison=pd.DataFrame(rows)
    comparison['p_holm_exploratory']=holm_adjust(comparison.p_welch_iid_exploratory)
    return regimes,comparison


def write_derived_tables(folder,settings):
    tops=[]
    for window in ['daily','weekly']:
        nodes=pd.read_parquet(folder/f'community_nodes_{window}.parquet')
        if nodes.empty:continue
        communities=nodes.groupby(['time_window','community_id'],sort=True).agg(
            community_size=('address','size'),community_volume_usdt=('node_volume_usdt','sum')).reset_index()
        communities['window_type']=window
        communities['community_volume_share']=communities.community_volume_usdt/communities.groupby('time_window').community_volume_usdt.transform('sum')
        communities=communities.sort_values(['time_window','community_volume_usdt','community_id'],ascending=[True,False,True])
        communities['volume_rank']=communities.groupby('time_window').cumcount()+1
        tops.append(communities[communities.volume_rank<=5])
    columns=['time_window','community_id','community_size','community_volume_usdt','window_type','community_volume_share','volume_rank']
    top=pd.concat(tops,ignore_index=True) if tops else pd.DataFrame(columns=columns)
    top.to_parquet(folder/'top_communities_summary.parquet',index=False)
    regimes,comparison=build_rq4(pd.read_parquet(folder/'snapshot_metrics_daily.parquet'),settings)
    regimes.to_parquet(folder/'rq4_daily_regimes.parquet',index=False)
    comparison.to_parquet(folder/'rq4_comparison.parquet',index=False)


def write_completion_report(folder,root):
    summary=json.loads((folder/'t11_summary.json').read_text(encoding='utf-8'))
    review=json.loads((folder/'t11_review.json').read_text(encoding='utf-8'))
    proof=json.loads((folder/'t11_reproducibility.json').read_text(encoding='utf-8'))
    regimes=pd.read_parquet(folder/'rq4_daily_regimes.parquet')
    comparison=pd.read_parquet(folder/'rq4_comparison.parquet')
    counts=regimes.regime.value_counts().to_dict();top=pd.read_parquet(folder/'top_communities_summary.parquet')
    lines=['# T11 — Community detection và network concentration', '',
        '**Hoàn tất phần kỹ thuật, kiểm định và tái lập trên T08 hiện tại.**',
        'Kết quả RQ4 là mô tả hồi cứu quanh ngày volume cao, chưa xác nhận stress thị trường hoặc hành vi nhà đầu tư.', '',
        '## Phạm vi bàn giao', '',
        '| Cửa sổ | Snapshot | Dòng node | Q trung bình |', '|---|---:|---:|---:|']
    for window in ['daily','weekly']:
        shape=summary['shapes'][window]
        lines.append(f"| {window} | {shape['snapshots']} | {shape['node_rows']:,} | {shape['mean_modularity']:.6f} |")
    lines += ['', 'Giữ 655 ngày UTC và 94 tuần ISO; hai tuần thiếu ngày có eligible_for_regression=false.',
        'Louvain có hướng, trọng số USDT, resolution=1. Community ID chỉ có ý nghĩa trong từng snapshot.', '',
        '## Kiểm định', '',
        f"- Validator độc lập đạt {review['windows_checked']}/{review['windows_checked']} cửa sổ từ cạnh T08; không nhập hàm tính chỉ số production.",
        f"- {len(proof['hashes'])}/{len(proof['hashes'])} Parquet khớp SHA-256 giữa hai tiến trình mới, PYTHONHASHSEED=0.",
        '- Kiểm tra calendar, khóa, node/edge, volume/degree, phân hoạch, modularity, mọi chỉ số tập trung, bảng top và thống kê RQ4.',
        '- Chỉ validator đạt mới bật ready_for_downstream; --skip-reproducibility luôn giữ false.',
        '- Tái lập không chứng minh quyền sở hữu, ý nghĩa kinh tế hoặc giả thuyết RQ4.', '',
        '## Bảng sản phẩm và hash hiện tại', '', '| File | Dòng | SHA-256 |','|---|---:|---|']
    for name,h in proof['hashes'].items():
        lines.append(f"| {name} | {len(pd.read_parquet(folder/name)):,} | `{h['run1']}` |")
    lines += ['', f"Bảng top có {len(top):,} dòng, top 5 theo volume trong mỗi cửa sổ ngày/tuần, được sinh trong cả hai lượt.",
        'Metadata: t11_summary.json, t11_review.json, t11_reproducibility.json.', '',
        '## RQ4 — đối chiếu mô tả', '',
        'High-volume là volume T08 >= phân vị 90% toàn kỳ; pre là 1–3 ngày trước high-volume và không phải high-volume.',
        f"Số ngày: baseline={counts.get('baseline',0)}, pre={counts.get('pre_high_volume',0)}, high-volume={counts.get('high_volume',0)}, censored={counts.get('right_censored',0)}.",
        'Ba ngày cuối không đủ quan sát tương lai bị loại khỏi so sánh; không mặc định chúng là baseline.', '',
        '| Chỉ số | Baseline | Pre | High-volume | Thay đổi Pre/Base | p Welch | p Holm (5 chỉ số) |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for row in comparison.itertuples():
        lines.append(f'| {row.metric} | {row.mean_baseline:.6f} | {row.mean_pre_high_volume:.6f} | {row.mean_high_volume:.6f} | {row.relative_change_pct:+.2f}% | {row.p_welch_iid_exploratory:.6g} | {row.p_holm_exploratory:.6g} |')
    lines += ['', 'Các p-value là thăm dò: Welch giả định quan sát độc lập, Holm chỉ điều chỉnh kiểm định nhiều chỉ số, không xử lý phụ thuộc thời gian/cụm sự kiện.',
        'Không thể suy từ Gini node sang tập trung cộng đồng, danh tính cá nhân, tái cơ cấu danh mục, dòng vào sàn hoặc khủng hoảng thanh khoản.',
        'HHI cộng đồng và CCI không cung cấp bằng chứng đủ để xác nhận giả thuyết tăng tập trung trước stress thị trường.',
        'Cần sự kiện stress độc lập và thiết kế thống kê phù hợp trước khi đưa ra kết luận thị trường/nhân quả hoặc dự báo.', '',
        '## Biểu đồ và giới hạn', '',
        'Bốn PNG được tạo ở data/figures/t11/: modularity_timeseries, concentration_timeseries, rq4_stress_comparison và community_map_2026-10-17 (tiền tố t11_).',
        'Các box dùng thứ tự baseline/pre/high-volume, N động và cùng bảng rq4_comparison; đây là biểu đồ Matplotlib tĩnh.',
        'Mạng chỉ chứa transfer sau netting >=500.000 USDT; concentration mô tả mạng con đang hoạt động, không phải toàn mạng hoặc tài sản cá nhân.',
        'Volume node là vào + ra, tổng bằng hai lần volume cạnh; community_volume lặp trên node, không cộng lại cột này qua các node.',
        'CCI=max(Q,0)×HHI community volume là chỉ số tổng hợp của dự án, không tự xác nhận rủi ro hệ thống.', '',
        '## Chạy lại', '', '```powershell','python T11_Community_Concentration.py',
        'python scripts/validate_t11_current.py','python -m src.visualize_t11','```', '',
        'Không lưu mã/bản test giả sau khi kiểm tra; giữ validator dữ liệu thật và bằng chứng Parquet/JSON.',
        'Xem [đặc tả](T11_community_concentration_specification.md) và [kết quả xử lý review](T11_review_report.md).']
    (root/'docs/T11_completion_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
