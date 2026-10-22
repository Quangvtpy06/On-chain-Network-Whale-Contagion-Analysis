"""Record an actual member review of selected CEX history claims; never impersonate a reviewer."""
import argparse
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.cex_label_history import load_settings, validate_approvals


def main():
    p=argparse.ArgumentParser(description=__doc__)
    scope=p.add_mutually_exclusive_group(required=True)
    scope.add_argument('--project');scope.add_argument('--address')
    p.add_argument('--reviewer',required=True);p.add_argument('--note',required=True)
    p.add_argument('--decision',choices=['approve','reject'],required=True)
    p.add_argument('--source-opened-by-human',action='store_true')
    p.add_argument('--ethereum-addresses-confirmed',action='store_true')
    p.add_argument('--historical-bound-confirmed',action='store_true')
    a=p.parse_args();_,folder=load_settings()
    candidates=pd.read_parquet(folder/'t07_cex_history_candidates.parquet')
    selected=candidates.loc[candidates.project.eq(a.project)] if a.project else candidates.loc[candidates.address.eq(a.address.lower())]
    if selected.empty:raise ValueError('No matching claims; inspect candidates/review packet first')
    target=folder/'t07_cex_history_human_decisions.parquet'
    old=pd.read_parquet(target) if target.exists() else pd.DataFrame()
    if len(old) and set(selected.claim_id)&set(old.claim_id):raise ValueError('Existing review; use an explicit versioned correction, do not overwrite')
    now=pd.Timestamp.now(tz='UTC')
    new=pd.DataFrame([dict(claim_id=r.claim_id,decision=a.decision,reviewed_by=a.reviewer.strip(),
        verified_at=now,review_note=a.note.strip(),source_opened_by_human=a.source_opened_by_human,
        ethereum_addresses_confirmed=a.ethereum_addresses_confirmed,historical_bound_confirmed=a.historical_bound_confirmed)
        for r in selected.itertuples()])
    all_decisions=pd.concat([old,new],ignore_index=True)
    validate_approvals(candidates,all_decisions)
    tmp=target.with_suffix('.parquet.tmp');all_decisions.to_parquet(tmp,index=False);tmp.replace(target)
    # An edited review must never leave an old accepted endpoint registry open.
    from src.node_centrality import write_json
    write_json(folder/'t07_cex_history_gate.json',dict(ready_for_t14_endpoint_lookup=False,
        reason='Human decisions updated; rebuild and independently validate before using endpoints'))
    print(f'Recorded {len(new)} actual review decisions; run scripts/build_t07_cex_history.py. No T07 retrospective table or T12 output changed.')


if __name__=='__main__':main()
