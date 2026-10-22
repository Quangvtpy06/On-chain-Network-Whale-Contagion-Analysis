"""Validate immutable CEX evidence, actual approvals and real-data volume coverage."""
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.graph_config import ROOT, read_config, project_path
from src.node_centrality import sha256, write_json
from src.cex_label_history import CONFIG,load_settings,available_cex_labels


def reference_extract(body,mode):
    text=body.decode('utf-8')
    # A second, narrow extraction path. No production tokenizer/parser call.
    if mode=='binance_asset_list':
        match=re.search(r'\bassetList\s*=\s*\[(.*?)\n\]',text,re.S)
        if not match:raise ValueError('Missing assetList')
        return set(x.lower() for x in re.findall(r"\[\s*['\"][^'\"]+['\"]\s*,\s*['\"]ETH['\"]\s*,\s*['\"](0x[0-9a-fA-F]{40})['\"]\s*\]",match.group(1)))
    match=re.search(r'\bethereum\s*:\s*\{\s*owners\s*:\s*\[([^\]]*)\]',text,re.S)
    if not match:return None
    section=re.sub(r'/\*.*?\*/|//[^\n]*','',match.group(1),flags=re.S)
    parts=[x.strip() for x in section.split(',') if x.strip()]
    if not all(re.fullmatch(r"['\"]0x[0-9a-fA-F]{40}['\"]",x) for x in parts):return None
    return set(x[1:-1].lower() for x in parts)


def validate():
    cfg,folder=load_settings()
    write_json(folder/'t07_cex_history_gate.json',dict(ready_for_t14_endpoint_lookup=False,reason='Independent validation running or interrupted'))
    summary=json.loads((folder/'t07_cex_history_summary.json').read_text(encoding='utf-8'))
    frozen=json.loads((folder/'t07_cex_history_freeze.json').read_text(encoding='utf-8'))
    if frozen['config_sha256']!=sha256(CONFIG) or frozen['protocol_id']!=cfg['protocol_id']:
        raise ValueError('Frozen history configuration changed')
    for rel,h in summary['inputs'].items():
        if sha256(project_path(rel))!=h:raise ValueError('History source/code changed: '+rel)
    source=pd.read_parquet(folder/'t07_cex_history_source_payloads.parquet')
    candidates=pd.read_parquet(folder/'t07_cex_history_candidates.parquet')
    approved=pd.read_parquet(folder/'t07_cex_label_history.parquet')
    status=pd.read_parquet(folder/'t07_cex_history_sources.parquet')
    for r in source.itertuples():
        if hashlib.sha256(r.raw_bytes).hexdigest()!=r.payload_sha256:raise ValueError('Source bytes hash mismatch')
    pr=json.loads(source.loc[source.project.eq('_merge_metadata'),'raw_bytes'].iloc[0])
    if pr['merge_commit_sha']!=cfg['snapshot_commit'] or pr['merged_at']!=cfg['public_available_upper_bound']:
        raise ValueError('Public merge provenance mismatch')
    if pr['base']['repo']['private'] or pr['base']['repo']['full_name']!=cfg['repository'] or pr['number']!=cfg['public_merge_pr']:
        raise ValueError('Wrong repository or nonpublic source')
    study=read_config();start=pd.Timestamp(study['project']['start_date'],tz='UTC')
    if pd.Timestamp(pr['merged_at'])>=start:raise ValueError('Selected snapshot not public before the study')
    if not candidates.address.str.fullmatch(r'0x[0-9a-f]{40}').all() or candidates.claim_id.duplicated().any():raise ValueError('Invalid/duplicate candidates')
    if not candidates.chain.eq('ethereum').all() or not candidates.entity_type.eq('CEX').all():raise ValueError('Non-Ethereum/non-CEX import')
    dates=pd.to_datetime(candidates.public_available_at,utc=True)
    if not dates.eq(pd.Timestamp(pr['merged_at'])).all():raise ValueError('Historical date not bound to merge metadata')
    checks=[]
    for s in source.itertuples():
        if s.parser=='metadata':continue
        observed=candidates.loc[candidates.project.eq(s.project)]
        metadata=status.loc[status.project.eq(s.project)].iloc[0]
        if any(int(metadata['n_'+state])!=int(observed.review_status.eq(state).sum()) for state in ['approved','pending','rejected']):
            raise ValueError('Source review status counts differ from candidate decisions')
        expected=reference_extract(s.raw_bytes,s.parser) if s.http_status==200 else set()
        if expected is None:
            if len(observed):raise ValueError('Unsupported source promoted')
        elif set(observed.address)!=expected:raise ValueError('Independent parser mismatch: '+s.project)
        if len(observed) and (not observed.source_sha256.eq(s.payload_sha256).all() or not observed.snapshot_commit.eq(cfg['snapshot_commit']).all()):
            raise ValueError('Claim/source binding mismatch')
        checks.append(dict(check='source_extraction',project=s.project,n_claims=len(observed),status='PASS'))
    decision_path=folder/'t07_cex_history_human_decisions.parquet'
    expected_approved=set()
    if decision_path.exists():
        decisions=pd.read_parquet(decision_path)
        if decisions.claim_id.duplicated().any() or not set(decisions.claim_id)<=set(candidates.claim_id):raise ValueError('Stale decisions')
        for r in decisions.itertuples():
            when=pd.to_datetime(r.verified_at,utc=True)
            if pd.isna(when) or when>pd.Timestamp.now(tz='UTC') or not r.reviewed_by.strip() or not r.review_note.strip():raise ValueError('Invalid review metadata')
            if r.decision=='approve':
                if not all(isinstance(x,(bool,np.bool_)) and x for x in [r.source_opened_by_human,r.ethereum_addresses_confirmed,r.historical_bound_confirmed]):raise ValueError('Missing actual human confirmations')
                expected_approved.add(r.claim_id)
                c=candidates.loc[candidates.claim_id.eq(r.claim_id)].iloc[0]
                if (c.reviewed_by!=r.reviewed_by or pd.Timestamp(c.verified_at)!=when or
                    c.review_note!=r.review_note or not c.human_verified or c.review_status!='approved'):
                    raise ValueError('Approval metadata does not match the actual decision sidecar')
            elif r.decision!='reject':raise ValueError('Invalid decision')
    if set(approved.claim_id)!=expected_approved or approved.address.duplicated().any():raise ValueError('Approval registry mismatch')
    expected_frame=candidates.loc[candidates.review_status.eq('approved')].reset_index(drop=True)
    if not approved.reset_index(drop=True).equals(expected_frame):raise ValueError('Approved registry rows were changed or detached from source claims')
    if not approved.human_verified.eq(True).all() or not approved.review_status.eq('approved').all():raise ValueError('Unapproved row exported')
    # Concrete edge boundaries using a temporary in-memory copy of a real claim.
    # This never writes a fabricated human decision or test dataset to disk.
    probe=candidates.iloc[:1].copy();bound=pd.Timestamp(pr['merged_at'])
    probe['review_status']='approved';probe['human_verified']=True
    if len(available_cex_labels(probe,bound)) or len(available_cex_labels(probe,bound+pd.Timedelta(nanoseconds=1)))!=1:
        raise ValueError('Availability cutoff boundary failed')
    probe['effective_to']=bound+pd.Timedelta(days=1)
    if len(available_cex_labels(probe,bound+pd.Timedelta(days=1))):raise ValueError('Effective-to boundary failed')
    probe['human_verified']=False
    if len(available_cex_labels(probe,bound+pd.Timedelta(hours=1))):raise ValueError('Unverified claim admitted')
    checks.append(dict(check='cutoff_expiry_and_unverified_controls',project='',n_claims=1,status='PASS'))
    coverage=pd.read_parquet(folder/'t07_cex_history_coverage_daily.parquet')
    edges=pd.read_parquet(project_path(study['data']['daily_edges_parquet']))
    days=pd.date_range(study['project']['start_date'],study['project']['end_date']).strftime('%Y-%m-%d').tolist()
    if len(coverage)!=2*len(days) or coverage.duplicated(['date','scope']).any():raise ValueError('Incomplete coverage calendar')
    groups=dict(tuple(edges.groupby('time_window')))
    for scope in ['candidate_only_not_approved','approved_asof']:
        c=coverage.loc[coverage.scope.eq(scope)].set_index('date')
        if c.index.tolist()!=days:raise ValueError('Missing coverage day')
        for day in days:
            e=groups.get(day,edges.iloc[:0]);t=pd.Timestamp(day,tz='UTC')
            ids=set(candidates.address) if scope=='candidate_only_not_approved' else set(available_cex_labels(approved,t).address)
            # Sum independent endpoint group totals; not the build's edge masks.
            endpoint=pd.concat([e.groupby('from_address').total_value.sum(),e.groupby('to_address').total_value.sum()]).groupby(level=0).sum()
            expected=float(endpoint.reindex(list(ids)).fillna(0).sum())
            total=float(e.total_value.sum())
            if not np.isclose(c.loc[day,'labeled_endpoint_usdt'],expected,rtol=1e-10,atol=.01) or not np.isclose(c.loc[day,'transfer_volume_usdt'],total):
                raise ValueError('Independent endpoint coverage mismatch')
        checks.append(dict(check='daily_volume_coverage',project=scope,n_claims=len(days),status='PASS'))
    pd.DataFrame(checks).to_parquet(folder/'t07_cex_history_validation.parquet',index=False)
    files=['t07_cex_history_source_payloads.parquet','t07_cex_history_candidates.parquet','t07_cex_label_history.parquet',
        't07_cex_history_sources.parquet','t07_cex_history_backlog.parquet','t07_cex_history_priority.parquet',
        't07_cex_history_coverage_daily.parquet','t07_cex_history_validation.parquet']
    rows=coverage.loc[coverage.scope.eq('candidate_only_not_approved')]
    fraction=float(rows.labeled_endpoint_usdt.sum()/(2*rows.transfer_volume_usdt.sum()))
    gate=dict(protocol_id=cfg['protocol_id'],technical_validation_passed=True,
        ready_for_t14_endpoint_lookup=bool(len(approved)),ready_for_rq3_pit_forecast=False,
        eligibility_scope='Approved subset of public-history Ethereum CEX attributions; not exhaustive CEX identification',
        approved_addresses=len(approved),pending_claims=int(candidates.review_status.eq('pending').sum()),
        history_path='data/processed/t07/cex_history/t07_cex_label_history.parquet',
        input_hashes=summary['inputs'],output_hashes={n:sha256(folder/n) for n in files},
        blocking_reasons=[] if len(approved) else ['No actual member has approved historical source/chain/address/public-availability evidence'],
        limitations=['Merge metadata bounds public availability, not the first publication date',
            'Public-information PIT differs from actual research knowledge; T12 v2 is unchanged',
            'Ownership attribution persistence is an assumption until contradicted; not continuous proof of key control',
            'CEX flow coverage is measured, not true recall; T14 timing/outcomes still require separate acceptance'])
    report=dict(all_pass=True,candidate_claims=len(candidates),candidate_addresses=int(candidates.address.nunique()),
        approved_addresses=len(approved),source_projects=len(status),coverage_days_per_scope=len(days),
        candidate_endpoint_volume_share_not_approved=fraction,gate=gate)
    write_json(folder/'t07_cex_history_review.json',report)
    write_json(folder/'t07_cex_history_gate.json',gate)
    print(json.dumps({k:v for k,v in report.items() if k!='gate'},indent=2),flush=True)


if __name__=='__main__':validate()
