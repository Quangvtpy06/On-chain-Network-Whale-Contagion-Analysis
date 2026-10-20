# T09 — Nghiệm thu trên T08 netted

**Trạng thái: Đạt**. Đối chiếu độc lập toàn bộ node/cửa sổ bằng pandas và phương trình PageRank SciPy.

| Độ phân giải | Snapshot | Dòng node–cửa sổ | Tuần thiếu ngày |
|---|---:|---:|---:|
| daily | 655 | 712,519 | 0 |
| weekly | 94 | 388,557 | 2 |

Sai số phương trình PageRank L1 lớn nhất: 8.5e-12.
Đã xác minh hash đầu vào, code, config và bốn bảng output. Đầu vào là T08 netted đã nghiệm thu; không dùng đồ thị thô cũ.
Các bảng node và bảng cửa sổ đều có days_in_window, is_partial_week, eligible_for_regression. Hai tuần thiếu ngày không dùng trong hồi quy.
Cửa sổ rỗng được giữ trong bảng snapshot (0 node, 0 cạnh, PageRank sum=0); bảng node không thêm ví giả.
Degree là in + out; weighted_degree_usdt là tổng volume vào + ra; weighted_degree_tx là tổng tần suất transaction theo cạnh, không phải unique transaction của cả ví.
PageRank có hướng dùng total_value, alpha trong config, phân phối uniform cho personalization/dangling; retry giữ cùng ngưỡng L1.
Nguồn remote cũ được thay thế có revision/hash ghi trong replaces_remote_outputs ở summary. Review lịch sử nằm trong docs/T09_legacy_remote_review.md.

Bàn giao: node_metrics_daily/weekly.parquet, snapshot_metrics_daily/weekly.parquet, t09_validation.parquet, t09_summary.json, t09_review.json.
Chạy lại: python T09_Network_Centrality.py rồi python scripts/validate_t09_current.py. Test/cache không nằm trong data/processed.
