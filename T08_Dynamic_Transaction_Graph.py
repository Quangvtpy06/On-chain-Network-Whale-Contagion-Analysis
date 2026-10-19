"""
T08: Xây dựng Dynamic Transaction Graph G_t
Chạy từ thư mục gốc: python T08_Dynamic_Transaction_Graph.py
"""
import sys
from pathlib import Path

# Thêm thư mục src vào path
sys.path.append(str(Path(__file__).parent / "src"))

from build_dynamic_graph import main

if __name__ == "__main__":
    main()

