# T10 — Chỉ số tính toán nặng trên T08 netted

Trạng thái: **Đạt — sẵn sàng bàn giao**.

749/749 cửa sổ đạt kiểm định clustering/eigenvector và đối chiếu betweenness
bằng API subset với phép chuẩn hóa riêng. Sai lệch betweenness lớn nhất
5,55e-17. Hai lượt tính đầy đủ cho SHA-256 giống nhau trên cả 6/6 bảng Parquet;
bản chạy thứ hai đã được xóa. Chi tiết tại t10_review.json,
t10_validation.parquet và t10_reproducibility.json.

| Độ phân giải | Cửa sổ | Dòng node–cửa sổ | Cạnh đầu vào T08 |
|---|---:|---:|---:|
| Ngày UTC | 655 | 712.519 | 998.663 |
| Tuần ISO | 94 | 388.557 | 633.921 |

Hai tuần thiếu ngày được gắn `eligible_for_regression=false`; giữ 92 tuần đủ
ngày. Các chỉ số bàn giao: betweenness có hướng theo số bước, eigenvector trái
có trọng số USDT, clustering có hướng không trọng số và có trọng số.

81 cửa sổ ngày dùng betweenness chính xác. 574 ngày và toàn bộ 94 tuần dùng
128 nguồn lấy mẫu có seed xác định. Eigenvector dùng ARPACK với khởi tạo cố
định; clustering tính đầy đủ trên đồ thị thưa.

## Chất lượng sampling

So với betweenness chính xác trên ba cửa sổ theo quy mô ở mỗi độ phân giải:

| Cửa sổ | Node | Phương pháp | MAE | Trùng top 20 |
|---|---:|---|---:|---:|
| 2025-03-23 | 325 | Chính xác | 0 | 100% |
| 2025-04-24 | 1.190 | 128 nguồn | 0,000742 | 80% |
| 2025-09-25 | 2.325 | 128 nguồn | 0,000399 | 85% |
| 2025-W01 | 2.238 | 128 nguồn | 0,000368 | 85% |
| 2025-W39 | 5.903 | 128 nguồn | 0,000211 | 85% |
| 2026-W22 | 4.027 | 128 nguồn | 0,000335 | 85% |

Kết quả là độ chính xác đo được trên các cửa sổ chọn kiểm tra, không phải bảo
đảm thứ hạng cho toàn kỳ. RMSE và sai số lớn nhất nằm trong bảng sampling_quality.

## Kiểm tra và dọn dữ liệu

Clustering được đối chiếu bằng công thức ma trận tam giác có hướng; eigenvector
được kiểm tra chuẩn L2 và phương trình riêng trên từng node/cửa sổ. Sai số riêng
lớn nhất khoảng 1,46e-10, thấp hơn ngưỡng 1e-8. Eigenvector trên đồ thị rời rạc
có cờ cảnh báo khả năng không duy nhất; không thay bằng PageRank.

Đã kiểm tra lại ba cửa sổ ngày nhỏ/trung vị/lớn bằng tiến trình Python riêng:
cả bốn cột chỉ số đều khớp từng giá trị. Entry point cố định PYTHONHASHSEED=0
để thứ tự cộng trọng số tam giác của NetworkX ổn định giữa các tiến trình.

Bộ kiểm tra thuật toán T08–T10 gồm 29 ca đã đạt trước khi xóa mã test. Đã xóa
thư mục tests, cấu hình pytest, helper review/download cũ không còn sử dụng và
cache test. Giữ kiểm định dữ liệu thật đang được pipeline gọi, bằng chứng
Parquet/JSON và dữ liệu nguồn. Quy ước lưu tại `../AGENTS.md`.

Giữ `src/__init__.py` làm dấu gói Python cho các lệnh import `src.*`; tệp này
không chứa dữ liệu, mã test hoặc tác vụ chạy ngầm.

## Bàn giao

`data/processed/t10/`: node_metrics_daily/weekly.parquet,
snapshot_metrics_daily/weekly.parquet, t10_validation.parquet,
t10_sampling_quality.parquet và summary/reproducibility/review JSON.
Không xuất CSV và không tự upload Hugging Face. Manifest bàn giao được tạo
bằng `scripts/prepare_hf_manifest.py` sau nghiệm thu.

Chạy: `T10_Heavy_Graph_Metrics.py`. Xem định nghĩa, giới hạn và cách tái lập
trong [đặc tả T10](T10_heavy_metrics_specification.md).
