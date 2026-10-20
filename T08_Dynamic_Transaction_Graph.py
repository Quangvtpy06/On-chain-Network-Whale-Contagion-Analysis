"""
Task T08: CLI Entry Point for Dynamic Transaction Graph (G_t)
=============================================================
Thực thi pipeline xây dựng chuỗi đồ thị động Daily & Weekly trên dữ liệu đã gộp
(Netted Flows), tính toán chỉ số mạng lưới và kiểm định bảo toàn khối lượng.

Cách chạy:
---------
# Chạy đầy đủ pipeline T08:
python T08_Dynamic_Transaction_Graph.py

# Xem đồ thị tương tác HTML một ngày bất kỳ (VD: 2025-01-01):
python T08_Dynamic_Transaction_Graph.py --show-only --date 2025-01-01
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Fix UTF-8 cho Windows console
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent

from src.build_dynamic_graph import (
    execute_t08_pipeline,
    show_dynamic_graph_snapshot,
    DynamicGraphLoader,
    DEFAULT_INPUT_PARQUET,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_LABELS_PARQUET,
)


def main():
    parser = argparse.ArgumentParser(
        description="Task T08: Xây dựng đồ thị động G_t trên dữ liệu Netted Whale Flows"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PARQUET,
        help="Đường dẫn file netted transfers (.parquet)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Thư mục xuất kết quả đồ thị",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS_PARQUET,
        help="File nhãn ví T07 (.parquet)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default="2025-01-01",
        help="Mốc ngày snapshot muốn hiển thị (mặc định: 2025-01-01)",
    )
    parser.add_argument(
        "--show-only",
        action="store_true",
        help="Chỉ mở hiển thị đồ thị HTML từ kết quả có sẵn",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=0,
        help="Số cạnh lớn nhất muốn hiển thị trên biểu đồ (0 = toàn bộ)",
    )
    parser.add_argument(
        "--all-edges",
        action="store_true",
        help="Hiển thị toàn bộ 100%% tất cả các cạnh",
    )
    parser.add_argument('--single-run', action='store_true',
                        help='Chỉ chạy một lần; B.9 giữ PENDING, chưa đủ nghiệm thu')
    parser.add_argument('--no-open', action='store_true',
                        help='Xuất HTML nhưng không tự mở trình duyệt')

    args = parser.parse_args()

    effective_top_k = 0 if args.all_edges else args.top_k
    edges_path = args.output / ('dynamic_edges_weekly.parquet' if '-W' in args.date else 'dynamic_edges_daily.parquet')

    if args.show_only:
        if not edges_path.exists():
            print(f"[-] Chưa tìm thấy: {edges_path}. Đang chạy pipeline trước...")
            execute_t08_pipeline(args.input, args.output, args.labels)
        show_dynamic_graph_snapshot(
            edges_parquet_path=edges_path,
            time_window=args.date,
            top_k_edges=effective_top_k,
            output_dir=args.output,
            auto_open=not args.no_open,
            labels_parquet_path=args.labels,
        )
        print(f'[+] Biểu đồ tương tác: {args.output / ("graph_" + args.date + ".html")}')
    else:
        execute_t08_pipeline(
            input_parquet=args.input,
            output_dir=args.output,
            labels_path=args.labels,
            verify_reproducibility=not args.single_run,
        )


if __name__ == "__main__":
    main()
