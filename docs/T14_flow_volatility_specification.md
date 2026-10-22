# T14 — Xây biến NetFlow, WhaleFlow, volatility và biến kiểm soát

Phụ trách: TV5. Phụ thuộc T05, T06, T07 (và T08/T12 cho cạnh, nhãn, cohort).
Chạy: `python T14_Flow_Volatility.py` ở gốc dự án. Cấu hình đóng băng: `config/t14.yaml`
(protocol `t14_v1`); không chỉnh theo hệ số hay p-value của T15.

## Nguyên tắc point-in-time

- Một dòng = một ngày UTC D = [D 00:00, D+1 00:00). Mọi feature của dòng D chỉ dùng dữ
  liệu đến hết ngày D; cột `available_at` = D+1 00:00 UTC.
- Mọi chuẩn hóa (scale, z-score, phân vị) chỉ dùng các ngày **trước D**: cửa sổ [D−L, D).
- Biến mục tiêu đặt tên `target_*` (nhìn về phía trước D+h), không bao giờ làm predictor.
- Kiểm tra tự động: cắt toàn bộ dữ liệu sau ngày `cut`, tính lại; feature các ngày ≤ cut
  phải giữ nguyên (4 mốc cắt). Mã còn được thử nghiệm với một feature cố tình “nhìn
  trước” để chắc chắn kiểm tra này bắt được lỗi.

## Biến

| Nhóm | Cột | Định nghĩa |
|---|---|---|
| CEX NetFlow | `cex_external_in_usdt`, `cex_external_out_usdt`, `cex_netflow_usdt` | In − Out của tập ví CEX đã gán nhãn; chuyển nội bộ giữa hai CEX tách riêng (`cex_internal_usdt`); DEX không thuộc tập CEX. Cùng quy tắc với T12 `build_cex`, có kiểm tra khớp `cex_netflow_daily.parquet`. |
| Chuẩn hóa | `cex_netflow_scaled`, `cex_netflow_z` | NetFlow / trung bình volume transfer 30 ngày trước; z-score theo 90 ngày trước. Cần ≥30 ngày lịch sử, nếu chưa đủ là NaN. |
| WhaleFlow (cohort) | `whale_to_cex_usdt`, `cex_to_whale_usdt`, `whaleflow_usdt`, `whaleflow_scaled`, `whaleflow_z` | Cohort top-50 của T12 (`t12_lagged_v1`, chọn từ [D−30, D)). WhaleFlow = cohort→CEX − CEX→cohort trong ngày D. Địa chỉ CEX bị loại khỏi cohort (T12 chỉ loại nhãn do người xác minh). Ngày chưa có cohort là NaN, không phải 0. |
| Large transfer | `large_transfer_count`, `large_transfer_volume_usdt`, `large_to_cex_usdt`, `large_from_cex_usdt`, `large_cex_netflow_usdt`, `large_transfer_threshold_usdt` | Cạnh có `total_value` ≥ phân vị 95 của các cạnh trong 90 ngày trước (cần ≥30 ngày và ≥100 cạnh). Không dùng phân vị toàn kỳ. |
| Volatility | `rv`, `log_rv`, `realized_vol`, `n_hourly_returns` | RV_D = Σ bình phương 24 log-return giờ trong ngày D (return giờ đầu dùng close cuối D−1). Thiếu bar thì NaN; ngày đầu tiên (không có close trước) là NaN. |
| HAR | `log_rv_week`, `log_rv_month` | Log của RV trung bình 7 / 30 ngày kết thúc tại D. |
| Target | `target_log_rv_h{1,3,7}` | log RV của ngày D+h; h ngày cuối là NaN. |
| Kiểm soát X_t (thị trường) | `ret_1d`, `log_volume_usdt`, `log_trade_count`, `taker_imbalance`, `spread_cs_proxy`, `parkinson_var` | Từ ETHUSDT 1d của T06. `spread_cs_proxy` là ước lượng high-low Corwin–Schultz dùng ngày D−1 và D, **không phải spread niêm yết** (T06 chỉ có trade). |
| Kiểm soát X_t (chuỗi) | `eth_log_transactions`, `eth_log_volume`, `eth_log_gas_gwei`, `log_transfer_volume_usdt` | `eth_stats_from_2025.csv` và tổng volume cạnh T08. |
| Lịch | `day_of_week` | 0 = thứ Hai. |

## Đầu ra (`data/processed/t14/`)

`t14_features_daily.parquet` (655 dòng), `t14_validation.parquet`, `t14_summary.json`,
`t14_reproducibility.json`. Chạy hai lượt (lượt hai ở `.cache/`, tự dọn) và so SHA-256 trước
khi bật `ready_for_t15_*`.

## Giới hạn cần ghi vào báo cáo

1. Nhãn CEX của T07 là hồi cứu, không có ngày khả dụng lịch sử → NetFlow mô tả tốt nhóm ví
   đang gắn nhãn nhưng **chưa đủ làm bằng chứng dự báo PIT cho RQ3** (`cex_labels_pit=False`).
2. Tỷ trọng volume CEX đã biết không phải recall; ví Unknown có thể là ví sàn.
3. Mạng chỉ gồm transfer USDT đã netting ≥ 500.000, không phải toàn Ethereum.
4. WhaleFlow theo cohort bị chặn tới khi gate T12 mở (`whaleflow_gate_open`); cột này là thăm dò.
   High-centrality / hoạt động lớn không đồng nghĩa nhà đầu tư cá nhân.
5. Ba nhánh độc lập (CEX NetFlow, large transfer, concentration T11) không bị gate chặn;
   concentration T11 lấy trực tiếp từ bảng T11 ở bước T15, không nhân đôi ở đây.
