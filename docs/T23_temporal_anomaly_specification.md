# T23 — Phát hiện bất thường chuỗi graph tuần (phần mở rộng)

Nguồn công việc: hàng T23 của `Phan_cong_Blueprint08.xlsx`; Task 2 nâng cao trong `08_onchain_whale_network.md`. Protocol `t23_temporal_graph_anomaly_v1`. **Chỉ được chạy sau khi T20–T22 đạt gate bắt buộc** (`t22_independent_review.json` 112/112 PASS và artifact T20/T21/T22 khớp summary).

## Mục tiêu và giới hạn

Mô hình không giám sát phát hiện tuần có cấu trúc mạng / embedding lệch so với phân phối train. Ngưỡng fit chỉ trên tuần train scoreable. Nhãn stress T13 chỉ gắn sau khi chấm điểm để đối chiếu mô tả; **không** đưa vào feature, loss hay chọn ngưỡng. Kết quả là tín hiệu thay đổi cấu trúc mạng theo thời gian, **không** phải dự báo stress thị trường.

## Đầu vào đóng băng

| Nguồn | Vai trò |
|---|---|
| T19 split tuần | lịch 94 tuần và nhãn split |
| T08 `graph_metrics_weekly` | nodes, edges, volume, density, reciprocity |
| T11 `snapshot_metrics_weekly` | HHI, CCI, modularity |
| T21 `t21_snapshot_embeddings` | embedding tuần của GraphSAGE và GCN đã fit T21 |
| T13 `rv_daily_regimes` | stress hồi cứu, chỉ để mô tả chồng lấp |

Mô hình chính là GNN được T22 chọn bằng validation (GraphSAGE). GCN chạy song song để đối chiếu. Feature gồm mức tuyệt đối, delta so với tuần liền trước, và thống kê chuẩn hóa embedding; tuần đầu sau gap không có tuần trước nên không scoreable.

## Mô hình

Isolation Forest (`n_estimators=300`, `random_state` từ config, `n_jobs=1`) fit trên 53 tuần train scoreable. Ngưỡng = phân vị 0,95 của điểm bất thường train. Tuần có điểm cao hơn ngưỡng được gắn cờ. Không dùng validation/test để chọn ngưỡng.

## Nghiệm thu

Pipeline tự kiểm tra gate T20–T22, đủ 94 tuần mỗi mô hình, fit train-only, không gắn cờ trên tuần không scoreable, stress không nằm trong predictor. Validator riêng `scripts/validate_t23_extension.py` tái tính độc lập. Hai tiến trình với `PYTHONHASHSEED` khác nhau phải cho artifact trùng SHA-256. Không xuất CSV.

Output tại `data/processed/t23/`: features, scores, events, validation Parquet, timeline PNG, summary và independent review JSON.
