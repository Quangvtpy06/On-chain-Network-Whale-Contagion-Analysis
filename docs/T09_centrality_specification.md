# T09 — Chỉ số theo node và cửa sổ

Đầu vào là bốn file T08 trong config: cạnh ngày/tuần và metrics ngày/tuần. T09 kiểm
tra ready_for_t09_t12 và SHA-256 khớp cả hai lần T08 đã nghiệm thu trước khi chạy;
không tự tải đồ thị legacy từ Hugging Face khi thiếu đầu vào hiện tại.

## Định nghĩa

Đồ thị có hướng đơn trên từng snapshot UTC, mỗi cạnh là một cặp ví có hướng sau
netting. T09 từ chối cạnh trùng, cạnh tự trỏ, địa chỉ sai, trọng số không hữu hạn,
amount không dương, transaction_count không nguyên hoặc không dương.

- in_degree / out_degree: số hàng xóm gửi vào / nhận từ node.
- degree = in_degree + out_degree. Hai chiều cùng cặp được tính riêng.
- in_strength_usdt / out_strength_usdt: tổng total_value cạnh vào / ra.
- weighted_degree_usdt = in_strength_usdt + out_strength_usdt.
- in_tx_count / out_tx_count: tổng transaction_count theo cạnh vào / ra.
- weighted_degree_tx = in_tx_count + out_tx_count, lưu int64. Một transaction đi
  qua nhiều cạnh cùng ví có thể được tính nhiều lần; đây là strength theo tần suất
  cạnh, không phải số transaction_hash unique của cả ví.
- net_inflow_usdt = in_strength_usdt - out_strength_usdt.
- pagerank: PageRank có hướng theo luồng vào, weighted bằng total_value.

PageRank có alpha mặc định 0,85, personalization uniform, phân phối dangling
uniform. Sai số L1 toàn mạng đặt trong config (mặc định 1e-11). NetworkX dùng
`tol = global_L1_tolerance / n_nodes`; retry tăng số vòng tối đa và giữ cùng tol.
T09 kiểm tra lại residual phương trình trước khi ghi kết quả. Review độc lập dựng
ma trận thưa và kiểm tra phương trình bằng SciPy.

## Cửa sổ và schema

Daily giữ đủ 655 cửa sổ, weekly giữ đủ 94 tuần ISO bắt đầu thứ Hai UTC. Cả hai bảng
node và snapshot đều có days_in_window, is_partial_week, eligible_for_regression.
2025-W01 có 5 ngày, 2026-W42 có 6 ngày; chỉ 92 tuần đủ ngày được dùng cho hồi quy.

Snapshot rỗng có 0 node, 0 cạnh, 0 volume, pagerank_sum=0, pagerank_status=empty.
Nó vẫn có hàng trong bảng snapshot, còn bảng node không thêm hàng giả.

Khóa bảng node: (window_type, time_window, address). Khóa bảng snapshot:
(window_type, time_window). Chỉ có node hoạt động trong snapshot mới có chỉ số;
node không xuất hiện không mang nghĩa số dư bằng 0 hay không tồn tại trên Ethereum.

Bàn giao trong data/processed/t09:

- node_metrics_daily.parquet, node_metrics_weekly.parquet.
- snapshot_metrics_daily.parquet, snapshot_metrics_weekly.parquet.
- t09_validation.parquet: kiểm định toàn bộ node/cửa sổ, 749 dòng.
- t09_summary.json: hash đầu vào, code, config, phiên bản thư viện và thống kê.
- t09_review.json, t09_reproducibility.json: bằng chứng nghiệm thu và tái lập.

## Chạy và bàn giao

Từ thư mục crypto:

```powershell
& '../.venv/Scripts/python.exe' T09_Network_Centrality.py
& '../.venv/Scripts/python.exe' scripts/validate_t09_current.py
& '../.venv/Scripts/python.exe' scripts/reproduce_t09.py
& '../.venv/Scripts/python.exe' scripts/prepare_hf_manifest.py
```

Code sinh bảng trước, chỉ mở ready_for_downstream sau review độc lập. Manifest chỉ
cho phép bàn giao khi bốn bảng còn đúng hash và lần chạy lặp khớp hoàn toàn. Dữ liệu
chạy lặp nằm trong .cache, được dọn sau kiểm tra, không nằm trong data/.
Mã test dữ liệu giả đã được xóa theo quy ước dự án; giữ bộ nghiệm thu dữ liệu thật.
`--max-windows` mặc định ghi vào .cache/t09_preview và không đủ điều kiện bàn giao.

Các chỉ số mô tả mạng con transfer ròng ≥500.000 USDT, không phải toàn mạng USDT;
PageRank phản ánh cấu trúc và trọng số luồng vào, không suy danh tính hay quyền sở
hữu ví. Các giới hạn về netting và transfer kinh tế độc lập được giữ từ đặc tả T08.
