"""Acquire pinned CEX evidence once, then build and independently validate offline."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.cex_label_history import fetch_sources, build

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fetch',action='store_true')
    parser.add_argument('--direct',action='store_true',help='Fetch public sources without environment proxy settings')
    args=parser.parse_args()
    if args.fetch:fetch_sources(direct=args.direct)
    build()
    from scripts.validate_t07_cex_history import validate
    validate()
