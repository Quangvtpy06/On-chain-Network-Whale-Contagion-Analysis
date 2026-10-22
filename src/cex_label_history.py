"""Public-history CEX evidence, separate from retrospective T07 and human approval."""
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from src.graph_config import ROOT, read_config, project_path, relative_path
from src.node_centrality import sha256, write_json

CONFIG=ROOT/'config/t07_cex_history.yaml'
TOKEN=re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_$][\w$]*|[^\s]',re.S)
ADDRESS=re.compile(r'0x[0-9a-fA-F]{40}\Z')


def tokens(text):
    return [(m.group(),text.count('\n',0,m.start())+1) for m in TOKEN.finditer(text)
            if not m.group().startswith(('//','/*'))]


def extract_owners(text, parser):
    """Parse literal Ethereum owners only; never execute downloaded JavaScript."""
    tok=tokens(text);v=[s for s,_ in tok];found=[]
    if parser=='binance_asset_list':
        # Only rows of the declared assetList, never unrelated ETH token contracts.
        begin=v.index('assetList');begin=v.index('[',begin);depth=0;end=None
        for i in range(begin,len(v)):
            depth+=int(v[i]=='[')-int(v[i]==']')
            if depth==0:end=i;break
        for i in range(begin,end-6):
            if v[i]=='[' and v[i+2]==',' and v[i+4]==',' and v[i+6]==']':
                network=v[i+3].strip('\"\'');address=v[i+5].strip('\"\'')
                if network=='ETH' and ADDRESS.fullmatch(address):found.append((address.lower(),tok[i][1],tok[i+6][1]))
    elif parser=='ethereum_owners':
        for i in range(len(v)-2):
            if v[i].strip('\"\'')!='ethereum' or v[i+1:i+3]!=[':','{']:continue
            depth=1;j=i+3
            while j<len(v) and depth:
                depth+=int(v[j]=='{')-int(v[j]=='}');j+=1
            block=v[i+3:j-1]
            for offset in range(len(block)-2):
                if block[offset].strip('\"\'')!='owners' or block[offset+1:offset+3]!=[':','[']:continue
                start=i+3+offset+3;stop=start
                while stop<len(v) and v[stop]!=']':stop+=1
                if stop==len(v):raise ValueError('Unclosed owners list')
                literals=[x for x in v[start:stop] if x!=',']
                if not all(x[:1] in ['\"',"'"] and ADDRESS.fullmatch(x[1:-1]) for x in literals):
                    raise ValueError('Dynamic/non-address Ethereum owners list requires manual extraction')
                found.extend((v[k][1:-1].lower(),tok[k][1],tok[k][1]) for k in range(start,stop) if v[k]!=',')
    else:raise ValueError('Unknown extraction mode')
    result={}
    for address,first,last in found:result.setdefault(address,(address,first,last))
    return list(result.values())


def load_settings():
    cfg=read_config(CONFIG)
    return cfg,project_path(cfg['output_dir'])


def available_cex_labels(history,cutoff):
    """Use only approved public-history claims; verification time is never backdated.

    cutoff is exclusive, typically UTC midnight D for D-1 information. This is
    public-information PIT, distinct from the team's actual knowledge in v1/v2.
    """
    t=pd.Timestamp(cutoff)
    if t.tzinfo is None:raise ValueError('Explicit UTC/timezone-aware cutoff required')
    t=t.tz_convert('UTC')
    if history.empty:return history.copy()
    start=pd.to_datetime(history.effective_from,utc=True,errors='raise')
    end=pd.to_datetime(history.effective_to,utc=True,errors='raise')
    available=pd.to_datetime(history.public_available_at,utc=True,errors='raise')
    approved=history.review_status.eq('approved') & history.entity_type.eq('CEX')
    approved &= history.chain.eq('ethereum') & history.human_verified.eq(True)
    approved &= available.lt(t) & start.lt(t) & (end.isna()|end.gt(t))
    selected=history.loc[approved].copy()
    if selected.address.duplicated().any():raise ValueError('Overlapping approved CEX history claims')
    return selected


def load_cex_for_cutoff(cutoff):
    """T14 entry point: refuse stale/unapproved registries instead of zero-filling."""
    _,folder=load_settings()
    gate=json.loads((folder/'t07_cex_history_gate.json').read_text(encoding='utf-8'))
    if not gate.get('ready_for_t14_endpoint_lookup'):
        raise ValueError('T07 historical CEX subset has not been human-approved; do not use candidates as PIT endpoints')
    for rel,digest in gate['input_hashes'].items():
        if sha256(project_path(rel))!=digest:raise ValueError('CEX history input changed; rebuild/revalidate')
    for name,digest in gate['output_hashes'].items():
        if sha256(folder/name)!=digest:raise ValueError('CEX history output changed; rebuild/revalidate')
    return available_cex_labels(pd.read_parquet(folder/'t07_cex_label_history.parquet'),cutoff)


def validate_approvals(candidates,decisions):
    extra=['review_status','reviewed_by','verified_at','review_note','source_opened_by_human',
           'ethereum_addresses_confirmed','historical_bound_confirmed','human_verified']
    out=candidates.copy()
    out['review_status']='pending';out['reviewed_by']='';out['verified_at']=pd.Series(pd.NaT,index=out.index,dtype='datetime64[ns, UTC]')
    out['review_note']=''
    for c in extra[4:]:out[c]=False
    if decisions is not None and not decisions.empty:
        required={'claim_id','decision','reviewed_by','verified_at','review_note','source_opened_by_human',
                  'ethereum_addresses_confirmed','historical_bound_confirmed'}
        if not required<=set(decisions):raise ValueError('Missing human decision metadata')
        if decisions.claim_id.duplicated().any() or not set(decisions.claim_id)<=set(candidates.claim_id):
            raise ValueError('Duplicate or stale human decision claim')
        now=pd.Timestamp.now(tz='UTC')
        for r in decisions.itertuples():
            when=pd.to_datetime(r.verified_at,utc=True,errors='raise')
            if pd.isna(when) or when>now:raise ValueError('Invalid actual review timestamp')
            if not str(r.reviewed_by).strip() or not str(r.review_note).strip():raise ValueError('Empty reviewer/note')
            if r.decision not in ['approve','reject']:raise ValueError('Invalid human decision')
            flags=[r.source_opened_by_human,r.ethereum_addresses_confirmed,r.historical_bound_confirmed]
            if r.decision=='approve' and not all(isinstance(x,(bool,__import__('numpy').bool_)) and bool(x) for x in flags):
                raise ValueError('Explicit source, chain/addresses and historical bound confirmations required')
            at=out.claim_id.eq(r.claim_id)
            out.loc[at,extra]=['approved' if r.decision=='approve' else 'rejected',r.reviewed_by,when,r.review_note,
                              *flags,r.decision=='approve']
    approved=out.loc[out.review_status.eq('approved')].copy()
    if approved.address.duplicated().any():raise ValueError('Resolve conflicting/duplicate entity attribution before approval')
    return out,approved


def fetch_sources(direct=False):
    import requests
    from concurrent.futures import ThreadPoolExecutor
    cfg,folder=load_settings();folder.mkdir(parents=True,exist_ok=True)
    target=folder/'t07_cex_history_source_payloads.parquet'
    if target.exists():raise ValueError('Pinned evidence already exists; rebuild offline, do not overwrite it')
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    def client():
        s=requests.Session();s.trust_env=not direct
        s.headers['User-Agent']='crypto-research-cex-history'
        s.mount('https://',HTTPAdapter(max_retries=Retry(total=2,backoff_factor=.5,status_forcelist=[429,500,502,503,504])))
        return s
    session=client()
    pr_url=f"https://api.github.com/repos/{cfg['repository']}/pulls/{cfg['public_merge_pr']}"
    response=session.get(pr_url,timeout=30);response.raise_for_status();pr=response.json()
    if pr['merge_commit_sha']!=cfg['snapshot_commit'] or pr['merged_at']!=cfg['public_available_upper_bound'] or pr['base']['repo']['private']:
        raise ValueError('Public merge metadata does not match pinned snapshot')
    def fetch(spec):
        url=f"https://raw.githubusercontent.com/{cfg['repository']}/{cfg['snapshot_commit']}/{spec['path']}"
        with client() as worker:r=worker.get(url,timeout=25)
        if r.status_code not in [200,404]:r.raise_for_status()
        return dict(**spec,source_url=url,http_status=r.status_code,raw_bytes=r.content,
                    payload_sha256=hashlib.sha256(r.content).hexdigest(),retrieved_at=pd.Timestamp.now(tz='UTC').isoformat())
    with ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(fetch,cfg['sources']))
    # Store the original PR API response as well as its body hash; never a fabricated archive date.
    rows.append(dict(project='_merge_metadata',entity='',path='',parser='metadata',source_url=pr_url,
        http_status=200,raw_bytes=response.content,payload_sha256=hashlib.sha256(response.content).hexdigest(),
        retrieved_at=pd.Timestamp.now(tz='UTC').isoformat()))
    license_url=f"https://raw.githubusercontent.com/{cfg['repository']}/{cfg['snapshot_commit']}/LICENSE"
    r=session.get(license_url,timeout=30)
    rows.append(dict(project='_license',entity='',path='LICENSE',parser='metadata',source_url=license_url,
        http_status=r.status_code,raw_bytes=r.content,payload_sha256=hashlib.sha256(r.content).hexdigest(),
        retrieved_at=pd.Timestamp.now(tz='UTC').isoformat()))
    pd.DataFrame(rows).to_parquet(target,index=False)
    print(f'Pinned {len(rows)} source responses in Parquet',flush=True)


def build():
    cfg,folder=load_settings();folder.mkdir(parents=True,exist_ok=True)
    write_json(folder/'t07_cex_history_gate.json',dict(ready_for_t14_endpoint_lookup=False,reason='History build/validation in progress'))
    freeze=folder/'t07_cex_history_freeze.json'
    if freeze.exists():
        if json.loads(freeze.read_text(encoding='utf-8'))['config_sha256']!=sha256(CONFIG):
            raise ValueError('Frozen CEX history protocol changed; issue a new version')
    else:
        write_json(freeze,dict(protocol_id=cfg['protocol_id'],config_sha256=sha256(CONFIG),
            settings=cfg,issued_at=pd.Timestamp.now(tz='UTC').isoformat(),regression_outcomes_read=False))
    project=read_config();source_path=folder/'t07_cex_history_source_payloads.parquet'
    sources=pd.read_parquet(source_path);rows=[];source_status=[]
    for s in sources.itertuples():
        if hashlib.sha256(s.raw_bytes).hexdigest()!=s.payload_sha256:raise ValueError('Evidence payload corrupted')
        if s.parser=='metadata':continue
        count=0;status='not_found_in_snapshot' if s.http_status==404 else 'no_literal_ethereum_owners'
        if s.http_status==200:
            try: extracted=extract_owners(s.raw_bytes.decode('utf-8'),s.parser)
            except ValueError as e:extracted=[];status='manual_parser_review_required: '+str(e)
            for address,first,last in extracted:
                claim=hashlib.sha256((s.source_url+'|ethereum|'+address).encode()).hexdigest()
                rows.append(dict(claim_id=claim,address=address,chain='ethereum',entity_name=s.entity,entity_type='CEX',
                    project=s.project,source_tier=cfg['source_tier'],confidence=cfg['confidence_proposal'],
                    source_url=s.source_url,source_locator=f'Lines {first}-{last}',source_sha256=s.payload_sha256,
                    historical_evidence_url=f"https://github.com/{cfg['repository']}/blob/{cfg['snapshot_commit']}/{s.path}#L{first}-L{last}",
                    snapshot_commit=cfg['snapshot_commit'],public_merge_url=f"https://github.com/{cfg['repository']}/pull/{cfg['public_merge_pr']}",
                    public_available_at=pd.Timestamp(cfg['public_available_upper_bound']),
                    availability_basis=cfg['availability_policy'],effective_from=pd.Timestamp(cfg['public_available_upper_bound']),
                    effective_to=pd.NaT,persistence_policy=cfg['persistence_policy'],
                    source_extraction_verified=True,identity_status='secondary_source_attribution_not_verified_personal_ownership'))
            count=len(extracted)
            if count:status='literal_ethereum_addresses_extracted_pending_human_review'
        source_status.append(dict(project=s.project,entity_name=s.entity,source_url=s.source_url,
            http_status=s.http_status,n_ethereum_claims=count,status=status))
    candidates=pd.DataFrame(rows).sort_values(['entity_name','address']).reset_index(drop=True)
    if candidates.empty or candidates.claim_id.duplicated().any():raise ValueError('Missing or duplicate evidence')
    candidates['effective_to']=pd.Series(pd.NaT,index=candidates.index,dtype='datetime64[ns, UTC]')
    decision_path=folder/'t07_cex_history_human_decisions.parquet'
    decisions=pd.read_parquet(decision_path) if decision_path.exists() else None
    candidates,approved=validate_approvals(candidates,decisions)
    for s in source_status:
        group=candidates.loc[candidates.project.eq(s['project'])]
        s['n_approved']=int(group.review_status.eq('approved').sum())
        s['n_pending']=int(group.review_status.eq('pending').sum())
        s['n_rejected']=int(group.review_status.eq('rejected').sum())
        if s['n_ethereum_claims']:s['status']='literal_ethereum_addresses_extracted'
    candidates.to_parquet(folder/'t07_cex_history_candidates.parquet',index=False)
    approved.to_parquet(folder/'t07_cex_label_history.parquet',index=False)
    pd.DataFrame(source_status).to_parquet(folder/'t07_cex_history_sources.parquet',index=False)
    # Real transfer coverage, no claim that observed volume share equals CEX recall.
    labels=pd.read_parquet(project_path(project['data']['processed_labels_parquet']))
    edges=pd.read_parquet(project_path(project['data']['daily_edges_parquet']))
    endpoint=pd.concat([edges.groupby('from_address').total_value.sum(),edges.groupby('to_address').total_value.sum()]).groupby(level=0).sum()
    priority=candidates.copy()
    priority['netted_endpoint_usdt']=priority.address.map(endpoint).fillna(0.)
    priority['participates_in_graph']=priority.netted_endpoint_usdt.gt(0)
    priority=priority.sort_values(['netted_endpoint_usdt','address'],ascending=[False,True])
    priority.to_parquet(folder/'t07_cex_history_priority.parquet',index=False)
    inventory=labels.loc[labels.entity_type.eq('CEX'),['address','entity_name','source_url','label_conflict_review']].copy()
    inventory['netted_endpoint_usdt']=inventory.address.map(endpoint).fillna(0.)
    inventory['has_historical_candidate']=inventory.address.isin(candidates.address)
    inventory['has_approved_history']=inventory.address.isin(approved.address)
    inventory['status']=inventory.has_historical_candidate.map({True:'historical_evidence_pending_or_reviewed',False:'no_history_in_selected_snapshot'})
    inventory.loc[inventory.entity_name.str.contains('Tether',case=False,na=False),'status']='classification_correction_required_issuer_not_CEX'
    inventory.sort_values(['has_approved_history','netted_endpoint_usdt','address'],ascending=[True,False,True]).to_parquet(folder/'t07_cex_history_backlog.parquet',index=False)
    candidate_ids=set(candidates.address);coverage=[]
    dates=pd.date_range(project['project']['start_date'],project['project']['end_date']).strftime('%Y-%m-%d')
    grouped=dict(tuple(edges.groupby('time_window')))
    for day in dates:
        e=grouped.get(day,edges.iloc[:0]);total=float(e.total_value.sum());t=pd.Timestamp(day,tz='UTC')
        for scope,ids in [('candidate_only_not_approved',candidate_ids),('approved_asof',set(available_cex_labels(approved,t).address))]:
            a=e.from_address.isin(ids);b=e.to_address.isin(ids)
            endpoint_volume=float(e.loc[a,'total_value'].sum()+e.loc[b,'total_value'].sum())
            coverage.append(dict(date=day,scope=scope,n_label_addresses=len(ids),transfer_volume_usdt=total,
                labeled_endpoint_usdt=endpoint_volume,observed_endpoint_volume_share=endpoint_volume/(2*total) if total else float('nan'),
                incident_transfer_usdt=float(e.loc[a|b,'total_value'].sum()),
                cex_internal_usdt=float(e.loc[a&b,'total_value'].sum()),
                interpretation='Observed share of thresholded netted transfers; not true CEX recall; candidate scope is not PIT-approved'))
    pd.DataFrame(coverage).to_parquet(folder/'t07_cex_history_coverage_daily.parquet',index=False)
    inputs=[CONFIG,freeze,Path(__file__),ROOT/'config/config.yaml',ROOT/'src/graph_config.py',ROOT/'src/node_centrality.py',
        ROOT/'scripts/build_t07_cex_history.py',ROOT/'scripts/validate_t07_cex_history.py',
        ROOT/'scripts/review_t07_cex_history.py',source_path,project_path(project['data']['processed_labels_parquet']),
        project_path(project['data']['daily_edges_parquet'])]
    if decision_path.exists():inputs.append(decision_path)
    write_json(folder/'t07_cex_history_summary.json',dict(protocol_id=cfg['protocol_id'],
        candidates=len(candidates),candidate_addresses=int(candidates.address.nunique()),approved=len(approved),
        source_projects=len(source_status),historical_snapshot=cfg['snapshot_commit'],
        public_available_upper_bound=cfg['public_available_upper_bound'],
        inputs={relative_path(p):sha256(p) for p in inputs},
        availability_not_backdated_verification=True,retrospective_T07_unchanged=True,
        T12_v2_unchanged=True,public_information_model_distinct_from_research_knowledge_model=True))
    packet=['# T07 CEX — bảng review lịch sử','',
        f"Trạng thái registry: {len(approved)} approved / {int(candidates.review_status.eq('pending').sum())} pending / {int(candidates.review_status.eq('rejected').sum())} rejected. Quyết định của thành viên được lưu riêng, không suy từ extraction status.",
        'Nguồn thứ cấp DefiLlama, snapshot cố định và merge công khai trước mẫu. Chưa có phê duyệt của thành viên thì không được dùng như nhãn PIT đã nghiệm thu.',
        'Mở URL blob và PR merge; đối chiếu đúng owners Ethereum và các địa chỉ. Ngày commit không thay được ngày public merge. verified_at là thời điểm review thật hôm nay.',
        'Review theo project bằng scripts/review_t07_cex_history.py; không cần sửa Parquet trực tiếp. Xem docs/T07_CEX_history_handoff.md.','',
        '| Project | Chủ thể | Số địa chỉ | Approved / Pending / Rejected | Nguồn cố định | Trạng thái trích xuất |','|---|---|---:|---|---|---|']
    for s in source_status:
        blob=s['source_url'].replace('https://raw.githubusercontent.com/'+cfg['repository']+'/', 'https://github.com/'+cfg['repository']+'/blob/')
        packet.append(f"| {s['project']} | {s['entity_name']} | {s['n_ethereum_claims']} | {s['n_approved']} / {s['n_pending']} / {s['n_rejected']} | [Mở nguồn]({blob}) | {s['status']} |")
    packet+=['','## Ưu tiên 20 địa chỉ có volume đầu mút netted cao nhất','',
        'Bảng xếp theo volume để đối chiếu. Trạng thái review được ghi riêng. Mẫu số volume là tổng hai đầu mút của node; cùng một transfer có thể nằm ở hai node.',
        '| Địa chỉ | Chủ thể được nguồn gán | USDT đầu mút | Review | Vị trí nguồn lịch sử |','|---|---|---:|---|---|']
    for r in priority.head(20).itertuples():
        packet.append(f'| `{r.address}` | {r.entity_name} | {r.netted_endpoint_usdt:,.2f} | {r.review_status} | [Mở đúng dòng]({r.historical_evidence_url}) |')
    (ROOT/'docs/T07_CEX_history_review_packet.md').write_text('\n'.join(packet)+'\n',encoding='utf-8')
    print(f'T07 history built: {len(candidates)} claims, {len(approved)} approved',flush=True)
