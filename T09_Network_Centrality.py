"""T09: tính Degree, weighted degree và PageRank trên T08 netted đã nghiệm thu.

Logic ở src/node_centrality.py. Đầu ra bảng dùng Parquet.
Chạy đầy đủ: python T09_Network_Centrality.py
Chạy thử: python T09_Network_Centrality.py --window daily --max-windows 2
"""
import sys
if sys.platform.startswith('win'):
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')

from src.node_centrality import calculate_snapshot, load_edges, process_window, main

if __name__=='__main__':
    main()
