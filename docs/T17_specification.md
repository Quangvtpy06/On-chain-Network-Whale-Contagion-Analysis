# T17 — robustness và sensitivity của T15/T16

Protocol `t17_robustness_v1`, cấu hình `config/t17.yaml`, mã `src/robustness.py` và `T17_Robustness.py`. Mọi giá trị trong cấu hình được đóng băng trước lượt chạy; không chọn kịch bản theo dấu hệ số, p-value hay độ lớn phản ứng. Mọi kịch bản đều được báo cáo.

## Điều T17 không làm

- Không sửa T14, T15, T16 hay cờ RQ3. Đọc release T14 qua cùng `load_t14` (kiểm hash, policy, readiness) như T15/T16.
- Là liên hệ trong mẫu. Không phải hiệu ứng nhân quả, không phải kiểm định dự báo ngoài mẫu (T18), `rq3_answered = false`.
- **Trục token chưa chạy**: không có dữ liệu T04–T14 nào ngoài USDT. Output ghi `token_axis.status = not_run` kèm lý do. Muốn chạy phải tải token khác từ BigQuery và chạy lại T05–T16.

## Điều kiện chạy: tái tạo bản nghiệm thu trước

Kịch bản gốc (base) phải khớp đúng kết quả đã nghiệm thu, nếu không T17 báo FAIL và không dùng grid:
- T15: cùng `n_obs`, `R²` (baseline và primary), hệ số và p thô cho 2 nhánh × h = 1/3/7, sai số ≤ `tolerance`.
- T16: cùng tập ngày sự kiện được chọn (mọi loại và chính sách) và cùng số ứng viên.
- z-score flow `k=1` khớp cột T14; mục tiêu single-day tính lại khớp cột `target_log_rv_h*` của T14; `large_transfer_count` ở percentile gốc khớp T14.

## Bốn trục

| Trục | Kịch bản | Ghi chú |
|---|---|---|
| Horizon (T15) | single-day h ∈ {1,2,3,5,7,10,14}; **cộng dồn** `sum_days` h ∈ {1,3,7,14} | Hai định nghĩa không bao giờ trộn trong một kịch bản. Target luôn bắt đầu tại D+1 00:00 UTC. h=1 của hai định nghĩa trùng nhau (kiểm tra). |
| Cửa sổ dòng tiền (T15) | tổng dòng tiền ròng k = 3, 7 ngày liên tiếp (k=1 là gốc), chuẩn hóa lại chỉ bằng quá khứ `[D−L, D)` | Là tổng các ngày đã net, **không** phải đồ thị k ngày được net lại. Một ngày NaN trong cửa sổ làm cả tổng NaN, không bao giờ thành 0. |
| Ngưỡng (T16) | quantile large transfer 0,90/0,99; quantile concentration 0,85/0,95; ngưỡng z của hai sự kiện dòng tiền ròng 1,5/2,5; **percentile cạnh lớn của T14** 0,90/0,99 | Đổi một tham số một lần, các tham số khác giữ giá trị gốc. Percentile cạnh lớn dùng đúng hàm T14 trên cạnh theo ngày (hash khớp lineage T14/T11). |
| Cửa sổ đồ thị (T16) | chỉ số concentration theo **tuần ISO** của T11 thay cho theo ngày | Chỉ số tuần chỉ đặt vào ngày Chủ nhật kết thúc tuần đầy đủ (khả dụng đúng lúc kết thúc tuần); ngày khác là tín hiệu không khả dụng, không nhân bản. Tuần lẻ bị loại. |

## Mẫu, mô hình, đa kiểm định

Mỗi kịch bản T15 ước lượng hai mô hình trên **cùng các ngày**: controls; controls + flow. OLS có intercept, Newey–West Bartlett HAC theo công thức cố định của T15 (`fit_hac` gốc). Mẫu = cờ `predictors_ready_*` của T14 ∩ flow hữu hạn ∩ target hữu hạn. Ngày thuộc nhánh nào dùng nhánh đó, không trộn CEX và cohort. Holm áp dụng **trong từng trục** (mọi nhánh và kịch bản của trục là một họ); báo cả p thô. Không dùng nhánh hồi cứu làm bằng chứng.

Sự kiện: mỗi kịch bản chạy lại `events.compute` của T16 với tham số đổi. Báo số ứng viên, số sự kiện chọn, Jaccard với tập sự kiện gốc, và hiệu trung bình `log RV` / `log volume` (tau = 0..k trừ tau = −k..−1) theo từng sự kiện, kèm khoảng tin cậy bootstrap block theo sự kiện (block 3, 2.000 lần, seed ổn định theo SHA-256) chỉ khi đủ số sự kiện. Đây là phản ứng mô tả, không phải abnormal response so với phản thực.

## Kiểm định

- Tái tạo T15/T16 (trên).
- Giải ngoài: tính lại beta và SE HAC của vài kịch bản bằng đại số ma trận, so với `fit_hac`.
- Truncation và mutation của flow cửa sổ k ngày tại nhiều điểm cắt: giá trị trước điểm cắt không đổi khi bỏ hoặc sửa tương lai.
- Mọi kịch bản ước lượng thành công; Holm không nhỏ hơn p thô; mẫu k ngày lồng trong mẫu gốc.
- Chạy hai lần, so hash nội dung các bảng; hash nguồn/config/input kiểm lại sau khi tính.

## Sản phẩm (`data/processed/t17/`)

`t17_regression_robustness.parquet`, `t17_regression_summary.parquet`, `t17_event_robustness.parquet`, `t17_scenario_plan.parquet`, `t17_validation.parquet`, `t17_report.md`, `t17_regression_robustness.png`, `t17_summary.json` (boolean thật, hash đầy đủ).

## Chạy

```text
python T17_Robustness.py
```

Cần đã có đúng bản nghiệm thu: `data/processed/t14`, `t15`, `t16`, `t11` (kể cả `snapshot_metrics_weekly.parquet`), `data/processed/graphs/dynamic_edges_daily.parquet` và các gate T07/T12 mà `scripts/validate_t14_release.py` yêu cầu.
