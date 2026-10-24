# T19 — Ma trận feature node-window, nhãn T07 và split theo thời gian

Protocol `t19_v1`. Chạy từ gốc dự án: `python T19_Graph_ML_Features.py`. Cấu hình: `config/t19.yaml`. Mã: `src/graph_ml_features.py`.

## Phạm vi và những gì T19 không khẳng định

- Mỗi dòng là một cặp **(window_type, time_window, address)**: địa chỉ có ít nhất một cạnh vượt ngưỡng 500.000 USDT trong cửa sổ đó. Bảng chính là `weekly` (tuần ISO), bảng phụ là `daily`.
- Nhãn T07 là nhãn **hồi cứu** (thu thập 2026-10-20), không có ngày khả dụng lịch sử. T19 là bài toán **phân loại node trên feature cùng cửa sổ**, không phải dự báo nhãn tại thời điểm. Cờ `pit_label_forecast` luôn là `false`.
- Địa chỉ được gán nhãn thường là thực thể hoạt động lớn nên mẫu có nhãn **lệch chọn** so với toàn bộ node. Kết quả T20 chỉ đúng cho tập địa chỉ đã có nhãn.
- `Unknown`, `Contract`, `Other` không phải lớp âm. Giữ trong bảng với `label_status` riêng, không đưa vào huấn luyện có giám sát.

## Đầu vào

T09 `node_metrics_{weekly,daily}` và `snapshot_metrics_*`, T10 `node_metrics_*`, T11 `community_nodes_*` và `snapshot_metrics_*`, T07 `t07_complete_wallet_labels.parquet`. Ba bảng node phải có cùng số dòng và cùng khóa; nếu không, kiểm định báo FAIL, không bỏ dòng im lặng.

## Feature (chỉ dùng thông tin đến hết cửa sổ)

| Nhóm | Cột |
|---|---|
| T09 | degree, in/out degree, in/out strength, weighted degree (USDT và số giao dịch), net inflow, PageRank |
| T10 | betweenness, eigenvector, clustering, clustering có trọng số |
| T11 | community_size, community_volume_usdt, is_giant_community |
| Dẫn xuất | in_share, mean_edge_value, mean_tx_value, volume_share_of_window, community_volume_share, log1p và signed-log1p, xếp hạng phần trăm **trong cùng cửa sổ** |
| Lịch sử | windows_seen_before, seen_prev_window, lag1_degree, lag1_weighted_degree_usdt (cửa sổ trước; vắng mặt = 0 vì không có cạnh vượt ngưỡng) |

Không dùng `community_id` (số hiệu tùy ý theo từng cửa sổ), các cột dòng tiền của T07 (`incoming_usdt`… tính trên toàn kỳ), `is_contract`, nhãn của hàng xóm, tập CEX hay cohort T12. Không fit scaler ở T19; T20 fit trên train.

## Thời điểm khả dụng

Feature của cửa sổ khả dụng tại `available_at` = cuối cửa sổ (UTC). Tuần đầu 2025-W01 là tuần lẻ 5 ngày, tuần cuối lẻ 6 ngày; cả hai `eligible_for_regression = false` nên không vào split.

## Nhãn

Lớp = `entity_type` của T07 sau khi loại: `Unknown`, `Contract`, `Other`, địa chỉ zero, địa chỉ có `label_conflict_review`, lớp có ít hơn `min_addresses_per_class` (50) địa chỉ khác nhau. `label_status` ghi lý do từng dòng không có nhãn. Cột nhãn chỉ được ghép **sau khi** feature đã cố định; kiểm định so sánh hash feature trước và sau ghép.

## Split

Sắp theo thứ tự cửa sổ đủ điều kiện: train 60%, validation 20%, test 20% (đóng băng trong config), chừa **1 cửa sổ trống (tuần)** hoặc **7 cửa sổ (ngày)** giữa các split. Cột `split` nhận `train/validation/test/gap/excluded_partial_window`. Cùng một địa chỉ có thể xuất hiện ở nhiều split, nên có thêm cờ `address_seen_in_train`: T20 phải báo metric trên toàn bộ test **và** trên các dòng `address_seen_in_train == False`. Không chỉnh tỷ lệ hay gap theo kết quả mô hình.

## Kiểm định

- Số dòng T09/T10/T11 bằng nhau; khóa duy nhất; lịch cửa sổ liên tục.
- PageRank mỗi cửa sổ cộng bằng 1; weighted degree = in + out; net inflow = in − out; `community_volume_share` khớp tỷ lệ giant community của T11 snapshot.
- Không vô cực; cột feature không trùng danh sách cấm (id, nhãn, split, cột T07).
- Split đúng thứ tự thời gian, có gap, `address_seen_in_train` đúng.
- Cắt dữ liệu tương lai (truncation) và sửa dữ liệu tương lai (mutation) tại 3 điểm cắt: feature các cửa sổ trước không đổi.
- Chạy hai lần, so hash nội dung của bảng feature, split và tóm tắt nhãn.
- Cảnh báo (WARN, không chặn): lớp thiếu `min_addresses_per_class_per_split` (10) địa chỉ trong một split.

## Sản phẩm (Parquet + JSON)

`t19_node_features_{weekly,daily}.parquet`, `t19_split_windows_*`, `t19_label_summary_*`, `t19_feature_dictionary`, `t19_validation`, `t19_summary.json`, `t19_repro.json`.

`computation_validated` không có nghĩa `node_classification_ready`: sẵn sàng phân loại cần thêm số lớp ≥ 2 và mọi lớp đủ địa chỉ trong từng split.
