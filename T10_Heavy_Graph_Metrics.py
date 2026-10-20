"""T10: betweenness, eigenvector và directed clustering trên T08 đã nghiệm thu."""
import os
import subprocess
import sys

# NetworkX weighted triangles iterate address sets: fix ordering across processes.
if os.environ.get('PYTHONHASHSEED') != '0':
    environment = dict(os.environ, PYTHONHASHSEED='0')
    raise SystemExit(subprocess.call([sys.executable, *sys.argv], env=environment))

from src.heavy_graph_metrics import main

if __name__ == '__main__':
    main()
    if '--skip-reproducibility' not in sys.argv:
        from scripts.validate_t10_current import main as validate_release
        validate_release()
