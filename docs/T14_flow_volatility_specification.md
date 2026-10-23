# T14 — Xây biến NetFlow, WhaleFlow, Volatility và Biến kiểm soát (Protocol t14_v2)

Phụ trách: TV5. Phụ thuộc T05, T06, T07 (bản CEX History approved) và T08/T12 v2 (Activity Cohort).
Chạy: `python T14_Flow_Volatility.py` tại thư mục gốc dự án. Cấu hình đóng băng: `config/t14.yaml`.

---

## 1. Nguyên tắc Point-In-Time (PIT) & Ranh giới thông tin

- **Một dòng = một ngày UTC:** $D = [D\text{ 00:00:00 UTC}, D+1\text{ 00:00:00 UTC})$. Mọi feature của ngày $D$ chỉ sử dụng dữ liệu phát sinh trước hoặc trong ngày $D$; cột `available_at` = $D+1\text{ 00:00:00 UTC}$.
- **Chuẩn hóa quá khứ (Past-only):** Mọi chuẩn hóa (scale, rolling mean, z-score, phân vị) chỉ dùng cửa sổ nghiêm ngặt trước $D$: $[D-L, D)$ thông qua `shift(1)`. Tuyệt đối không chứa ngày $D$ trong mẫu tính tham số.
- **Biến mục tiêu (Target):** Đặt tên `target_*`, chỉ nhìn về tương lai $[D+1, D+h]$. Bắt buộc bị loại hoàn toàn khỏi danh sách predictor (`feature_columns`).
- **Kiểm định Truncation:** Cắt toàn bộ dữ liệu sau mốc $cut$, tính toán lại; mọi feature của các ngày $\le cut$ phải bất biến 100% trên cả 4 phân vị cắt ($25\%, 50\%, 75\%, 95\%$).

---

## 2. Nhóm biến và Định nghĩa chi tiết

| Nhóm | Tên cột | Định nghĩa & Quy tắc tính toán |
|---|---|---|
| **CEX NetFlow (PIT)** | `pit_cex_external_in_usdt`, `pit_cex_external_out_usdt`, `pit_cex_netflow_usdt`, `pit_cex_internal_usdt` | Tính theo tập nhãn khả dụng từng ngày $C_D$ (`public_available_at < D`, `effective_from < D`, `effective_to > D` hoặc null, `review_status=approved`). Không có nhãn khả dụng thì mang giá trị `NaN` (không đánh đồng với 0). Chuyển nội bộ giữa hai sàn được ghi riêng. |
| **WhaleFlow (PIT Cohort)** | `whale_to_cex_pit_usdt`, `cex_to_whale_pit_usdt`, `whaleflow_pit_usdt` | Cohort hoạt động lớn T12 v2 ($W_D$). WhaleFlow = cohort $\to$ CEX trừ CEX $\to$ cohort. Tuân thủ **Phương án 1**: Giữ nguyên rank/membership của v2, loại giao dịch nội bộ $W_D \cap C_D$, ghi nhận chi tiết tại `cohort_cex_pit_overlap`. |
| **Chuẩn hóa Flow** | `*_scaled`, `*_z` | Tử số là raw flow PIT. Mẫu số: `*_scaled` chia cho trung bình volume chuyển USDT toàn mạng trong 30 ngày trước $[D-30, D)$; `*_z` là z-score trượt 90 ngày $[D-90, D)$. Cần tối thiểu $\ge 30$ quan sát lịch sử hợp lệ. |
| **Large Transfer** | `large_transfer_count`, `large_transfer_volume_usdt`, `pit_large_cex_netflow_usdt` | Cạnh có giá trị $\ge$ phân vị 95 của các cạnh trong 90 ngày trước $[D-90, D)$ (yêu cầu $\ge 30$ ngày và $\ge 100$ cạnh). |
| **Realized Volatility (Chính)** | `rv`, `log_rv`, `realized_vol`, `n_minute_returns` | $RV_D = \sum_{m=1}^{1440} r_{D, m}^2$ tính từ 1.440 log-return 1 phút căn chuẩn UTC trong ngày $D$. Return phút đầu tiên lấy giá close cuối ngày $D-1$. Ngày thiếu bar là `NaN`. |
| **Sensitivity Volatility** | `rv_5m`, `realized_vol_5m` | Ước lượng độ nhạy từ 288 thanh 5 phút ($RV_{D, 5m} = \sum_{k=1}^{288} r_{D, 5m, k}^2$). |
| **HAR Volatility** | `log_rv_week`, `log_rv_month` | Log của RV trung bình 7 ngày và 30 ngày kết thúc tại ngày $D$. |
| **Forward Target** | `target_log_rv_h{1,3,7}` | Log realized volatility của ngày $D+h$ (định nghĩa `single_day`). $h$ ngày cuối cùng của mẫu mang giá trị `NaN`. |
| **Kiểm soát Thị trường** | `ret_1d`, `log_volume_usdt`, `log_trade_count`, `taker_imbalance`, `spread_cs_proxy`, `parkinson_var` | Trích xuất từ ETHUSDT 1d của T06. `spread_cs_proxy` là ước lượng High-Low Corwin–Schultz (2012) từ ngày $D-1$ và $D$. |
| **Kiểm soát On-chain** | `eth_log_transactions`, `eth_log_volume`, `eth_log_gas_gwei`, `log_transfer_volume_usdt` | Dữ liệu `eth_stats_from_2025.csv` và tổng USDT transfer netted từ T08. |

---

## 3. Quy tắc phân loại Eligibility & Warm-up (30 ngày đầu)

Bảng điều kiện mẫu `t14_sample_eligibility_daily.parquet` phân loại rõ lý do khả dụng của từng ngày:
- **01/01/2025 – 30/01/2025:** Chưa có cohort T12 v2 $\to$ `whaleflow_pit_status = no_cohort`.
- **31/01/2025 – 01/03/2025:** Đã có cohort và raw WhaleFlow, nhưng số lượng quan sát quá khứ trong $[D-90, D)$ chưa đủ 30 ngày $\to$ giữ z-score là `NaN` và đánh dấu `whaleflow_pit_z_status = insufficient_flow_history`.
- **Từ 02/03/2025 trở đi:** Đủ điều kiện tính z-score và chuẩn hóa hồi quy (nếu độ lệch chuẩn quá khứ $> 0$, ghi nhận `ok`; nếu độ lệch chuẩn $= 0$, ghi nhận `zero_variance`).
- Chỉ đánh dấu `missing_input` khi dữ liệu đầu vào thực sự bị thiếu ngoài dự kiến.

---

## 4. Danh mục File Đầu ra (`data/processed/t14/`)

1. `t14_features_daily.parquet`: Bảng đặc trưng chính (655 ngày UTC từ 01/01/2025 đến 17/10/2026).
2. `t14_cex_coverage_daily.parquet`: Thống kê độ bao phủ endpoint và USDT volume share theo từng ngày.
3. `t14_cex_coverage_monthly.parquet`: Tổng hợp coverage theo từng tháng và toàn kỳ.
4. `t14_cohort_cex_overlap_daily.parquet`: Báo cáo chi tiết số ví và member-days giao thoa giữa Cohort v2 và registry CEX lịch sử.
5. `t14_sample_eligibility_daily.parquet`: Trạng thái khả dụng chi tiết theo từng nhánh mô hình và từng horizon.
6. `t14_validation.parquet`: Kết quả kiểm định tự động (bắt buộc toàn bộ PASS).
7. `t14_summary.json` & `t14_reproducibility.json`: Metadata, checksum SHA-256 đối chiếu 2 lần chạy độc lập.
