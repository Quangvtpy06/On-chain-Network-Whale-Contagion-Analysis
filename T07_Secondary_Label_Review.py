"""Import decisions made by a team member; never verifies an AI lookup itself."""
import argparse
import pandas as pd
from src.graph_config import ROOT, read_config, project_path
from src.secondary_labels import validate_decisions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decisions',required=True,help='Parquet completed by the human reviewer')
    args=parser.parse_args()
    target=project_path(read_config(ROOT/'config/t12_design.yaml')['secondary_labels'])
    incoming=validate_decisions(pd.read_parquet(project_path(args.decisions)))
    old=pd.read_parquet(target) if target.exists() else incoming.iloc[:0]
    if set(old.address)&set(incoming.address):raise ValueError('Existing approved decision: explicit versioned correction required')
    pd.concat([old,incoming],ignore_index=True).sort_values('address').to_parquet(target,index=False)
    print(f'Imported {len(incoming)} human decisions into T07 secondary-label sidecar. To merge into complete T07, run T07_Complete_Wallet_Labels.py --offline, then rebuild/review affected downstream tasks and manifest.')


if __name__=='__main__':main()
