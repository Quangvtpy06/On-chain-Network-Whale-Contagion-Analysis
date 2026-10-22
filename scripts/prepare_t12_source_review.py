"""Prepare source evidence drafts; never marks AI research as human approval."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def main():
    evidence=json.loads((ROOT/'docs/T12_source_review_evidence.json').read_text(encoding='utf-8'))
    folder=ROOT/'data/processed/t12'
    queue=pd.read_parquet(folder/'t12_cohort_review_queue.parquet')
    cases={r['address']:r for r in evidence['cases']}
    if len(cases)!=40 or set(cases)!=set(queue.address):raise ValueError('Evidence must match all 40 review addresses')
    if not queue.address.str.fullmatch(r'0x[0-9a-f]{40}').all():raise ValueError('Invalid review address')
    sources=evidence['sources'];rows=[]
    for q in queue.itertuples():
        case=cases[q.address];source=sources.get(case.get('source'),{})
        rows.append(dict(address=q.address,t07_entity_name=q.entity_name,t07_entity_type=q.entity_type,
            in_audit_top20=q.in_audit_top20,in_cohort_top20=q.in_cohort_top20,
            candidate_entity_name=case['candidate_name'],candidate_entity_type=case['candidate_type'],
            evidence_class=case['support'],source_url=case.get('url',source.get('url','')),
            source_locator=source.get('locator','Exact address: '+q.address),
            document_date_claim=source.get('document_date',''),
            last_updated_claim=source.get('last_updated_claim',''),
            historical_status=source.get('historical_status','historical_availability_unconfirmed'),
            evidence_note=case['note'],review_method=evidence['review_method'],
            ai_lookup_date=evidence['review_date'],human_verified=False,
            source_opened_by_human=False,reviewed_by='',reviewed_at='',review_decision='',review_note='',
            approved_for_t07=False,approved_for_pit=False))
    draft=pd.DataFrame(rows)
    draft.to_parquet(folder/'t12_source_review_draft.parquet',index=False)
    pd.DataFrame([dict(source_id=k,**v) for k,v in sources.items()]).to_parquet(folder/'t12_source_review_sources.parquet',index=False)
    members=pd.read_parquet(folder/'cohort_members_daily.parquet')
    labels=pd.read_parquet(ROOT/'data/processed/t07/t07_complete_wallet_labels.parquet')
    tagged=members.merge(labels[['address','entity_type','entity_name','is_contract','source_url']],on='address',how='left',validate='many_to_one')
    infra=tagged.entity_type.isin(['CEX','DEX','Bridge','Contract','Other','DeFi'])|tagged.is_contract.fillna(False)
    profile=tagged.loc[infra].groupby('address',as_index=False).agg(
        member_days=('date','size'),first_cohort_day=('date','min'),last_cohort_day=('date','max'),
        mean_rank=('cohort_rank','mean'),t07_entity_name=('entity_name','first'),
        t07_entity_type=('entity_type','first'),t07_source_url=('source_url','first'))
    groups={a:g for g in evidence['historical_groups'] for a in g['addresses']}
    for col in ['historical_source_url','historical_document_date_claim','historical_evidence_status','candidate_entity_type','review_note']:
        profile[col]=''
    for i,row in profile.iterrows():
        group=groups.get(row.address)
        if group:
            source=sources[group['source']]
            profile.loc[i,['historical_source_url','historical_document_date_claim','historical_evidence_status','candidate_entity_type','review_note']]=[
                source['url'],source['document_date'],source['historical_status'],group['entity_type'],
                'Exact Ethereum address in dated operator page; archive/publication and human confirmation still pending.']
        elif row.address in cases:
            case=cases[row.address];source=sources.get(case.get('source'),{})
            profile.loc[i,['historical_source_url','historical_document_date_claim','historical_evidence_status','candidate_entity_type','review_note']]=[
                case.get('url',source.get('url','')),source.get('document_date',''),source.get('historical_status','current_or_inconclusive_only'),case['candidate_type'],case['note']]
        else:
            profile.loc[i,['historical_source_url','historical_evidence_status','review_note']]=[
                row.t07_source_url if isinstance(row.t07_source_url,str) else '',
                'not_individually_researched_this_pass','Existing T07 claim only; historical source review still needed.']
    profile['human_verified']=False;profile['approved_for_pit']=False
    profile=profile.sort_values(['member_days','mean_rank','address'],ascending=[False,True,True])
    profile.to_parquet(folder/'t12_infrastructure_history_review.parquet',index=False)
    matches=profile.historical_evidence_status.str.contains('dated_official_page|last_updated_date',regex=True)
    summary=dict(review_date=evidence['review_date'],queue_addresses=len(draft),
        evidence_classes=draft.evidence_class.value_counts().to_dict(),infrastructure_addresses=len(profile),
        infrastructure_member_days=int(profile.member_days.sum()),
        operator_page_historical_candidates=int(matches.sum()),
        candidate_member_days=int(profile.loc[matches,'member_days'].sum()),
        human_approvals_created=0,gate_changed=False,
        source_date_claim_is_not_approved_historical_availability=True)
    (folder/'t12_source_review_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# T12 — Bảng nguồn để thành viên review','',
        'Đây là tra cứu AI, chưa phải nhãn đã xác minh. Không có cờ human/PIT nào được bật.',
        'Unknown nghĩa là chưa xác định được chủ thể của địa chỉ, không phải không tìm thấy địa chỉ trên explorer. Nhãn hoạt động và nguồn cấp vốn được ghi riêng, không tự chuyển thành danh tính chủ ví.',
        'Mở URL, tìm toàn bộ địa chỉ, kiểm tra chain Ethereum và đọc ngữ cảnh danh tính; giao dịch với sàn không chứng minh ví thuộc sàn.',
        'Người kiểm tra ghi quyết định bằng scripts/review_t12_source.py; không cần sửa Parquet bằng IDE.','',
        '| Địa chỉ | Đề xuất/Unknown | Loại bằng chứng | Nguồn và vị trí | Ghi chú |',
        '|---|---|---|---|---|']
    for r in draft.itertuples():
        name=r.candidate_entity_name or 'Unknown'
        lines.append(f'| `{r.address}` | {name} ({r.candidate_entity_type}) | {r.evidence_class} | [Mở nguồn]({r.source_url}); {r.source_locator} | {r.evidence_note} |')
    lines+=['','Ngày trên tài liệu không tự chứng minh thời điểm xuất bản công khai. Nếu chỉ có nhãn hiện tại hoặc nguồn bị chặn, giữ unresolved; không xác nhận bừa.',
        '79 địa chỉ: xem data/processed/t12/t12_infrastructure_history_review.parquet. Những hàng not_individually_researched_this_pass chưa được tra cứu riêng trong lượt này.',
        'Không suy ra tư cách bị cáo, người phạm tội hoặc chủ tài khoản từ một địa chỉ xuất hiện trong hồ sơ tòa. Những tài liệu đó chỉ là đầu mối attribution cần đọc đúng phần sửa đổi.']
    (ROOT/'docs/T12_source_review_packet.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
