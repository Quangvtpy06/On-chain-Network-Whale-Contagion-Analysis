"""Record a team member's source review. Run only after personally opening the source."""
import argparse
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address',required=True)
    parser.add_argument('--reviewer',required=True)
    parser.add_argument('--decision',required=True,choices=['reviewed_unknown','verified_non_infrastructure','infrastructure'])
    parser.add_argument('--source-url',required=True)
    parser.add_argument('--note',required=True)
    parser.add_argument('--source-opened-by-human',action='store_true',required=True)
    args=parser.parse_args()
    folder=ROOT/'data/processed/t12';queue=pd.read_parquet(folder/'t12_cohort_review_queue.parquet')
    address=args.address.strip().lower()
    if address not in set(queue.address):raise ValueError('Address is not in the required review queue')
    if not args.reviewer.strip() or not args.note.strip() or not args.source_url.startswith('https://'):
        raise ValueError('Reviewer, HTTPS source and a substantive note are required')
    # Recording review is not approving a T07 identity or backdating a historical label.
    row=pd.DataFrame([dict(address=address,reviewed_by=args.reviewer.strip(),
        reviewed_at=pd.Timestamp.now(tz='UTC').isoformat(),review_decision=args.decision,
        source_url=args.source_url,source_opened_by_human=True,review_note=args.note.strip())])
    target=folder/'t12_cohort_human_review.parquet'
    old=pd.read_parquet(target) if target.exists() else row.iloc[:0]
    if address in set(old.address):raise ValueError('Review already exists; use an explicit versioned correction')
    merged=pd.concat([old,row],ignore_index=True).sort_values('address')
    tmp=target.with_suffix('.parquet.tmp');merged.to_parquet(tmp,index=False);tmp.replace(target)
    print(f'Recorded human review for {address}. {len(merged)}/{len(queue)} addresses reviewed. Gate and T07 labels were not changed.')


if __name__=='__main__':main()
