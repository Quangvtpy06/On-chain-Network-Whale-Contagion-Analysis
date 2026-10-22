"""Run frozen T12 v2 twice, then independently validate before issuing its gate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.whale_score_v2 import main

if __name__ == '__main__': main()
