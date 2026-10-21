"""
T11: Community Detection và Network Concentration (RQ4) trên T08 đã nghiệm thu.
================================================================================
Thực thi phát hiện cộng đồng Louvain, modularity Q, và tính toán toàn bộ
các chỉ số tập trung mạng lưới (HHI, Gini, CR-k, Entropy, CCI) theo cửa sổ thời gian.
"""
import os
import subprocess
import sys

# Cấu hình UTF-8 cho Windows console
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đảm bảo môi trường hash Python xác định cho việc duyệt set/dict
if os.environ.get("PYTHONHASHSEED") != "0":
    environment = dict(os.environ, PYTHONHASHSEED="0")
    raise SystemExit(subprocess.call([sys.executable, *sys.argv], env=environment))

from src.community_concentration import main

if __name__ == "__main__":
    main()
