# T17 — Robustness và sensitivity v2

Protocol `t17_usdt_daily_weekly_v2`, cấu hình `config/t17.yaml`. Chủ dự án chấp thuận ngày 26/10/2026 trước lượt chạy v2: **USDT; graph windows ngày và tuần ISO**. Chưa kiểm tra khả năng khái quát sang token khác. Trục token được loại khỏi phạm vi nghiệm thu theo quyết định này; không được ghi là thử nghiệm đa token đã đạt. Cấu hình token khác bị từ chối. Mở rộng phạm vi phải có protocol mới.

Các quy tắc dưới đây cố định trước chạy v2. V2 được xây sau review v1, không phải đăng ký trước khi nhìn thấy mọi kết quả v1. Không chọn lại tham số theo dấu hệ số, p-value hay độ lớn phản ứng.

## Nguồn và điều kiện chạy

- T14 qua validator release đầy đủ; policy observed approved CEX subset / unidentified high-activity cohort. Không suy danh tính nhà đầu tư cá nhân.
- T15/T16: kiểm tra computation, independent review, hash summary, mọi artifact, source/config/input lineage, content hashes hai lần chạy và policy. Chỉ đọc, không sửa output upstream.
- T11 ngày/tuần và T08 đúng hash tái lập và lineage T14/T11. Tuần đủ 7 ngày mới sử dụng.
- Tái tạo **chỉ base trước grid**: T15 khớp n_obs, R² baseline/full, hệ số, p và tập ngày; T16 khớp selection và ứng viên theo `(event_type,date)`, candidate, signal_available, threshold. Dừng trước grid khi không khớp.

## Các trục

| Trục | Kịch bản | Ý nghĩa |
|---|---|---|
| Horizon single-day | h=1,2,3,5,7,10,14 | log RV của đúng ngày D+h |
| Horizon cumulative | h=1,3,7,14 | log tổng RV D+1..D+h, khác estimand single-day |
| Flow window | k=1,3,7; h=1,3,7 | Tổng raw net flow k ngày, chuẩn hóa lại theo quá khứ |
| Flow window cùng mẫu | k=1,3,7; h=1,3,7 | Giao ngày hợp lệ theo branch/horizon để so cửa sổ |
| Ngưỡng event | quantile large count 0,90/0,99; CCI 0,85/0,95; flow z 1,5/2,5; percentile cạnh lớn 0,90/0,99 | Mỗi lần đổi một tham số, giữ và đối chiếu base |
| Graph window | CCI ngày / tuần ISO T11 | Tuần đặt tại Chủ nhật kết thúc tuần đầy đủ, khả dụng D+1 00:00 UTC |

Graph window không gồm 30 ngày hay 8 tuần. `weekly_minimum_history_values=8` là số quan sát tuần tối thiểu trong cửa sổ lịch sử threshold 90 ngày. Flow k ngày là tổng flow ngày đã net, không phải dựng lại đồ thị k ngày.

## Công thức và mẫu

`raw_k(D)=sum(raw(D-k+1)..raw(D))`, đủ k ngày hữu hạn. `z_k(D)` chuẩn hóa raw_k bằng mean/std(ddof=1) lịch sử `[D-L,D)` theo config T14. Raw thiếu làm tổng liên quan thiếu, không thay NaN bằng 0. Volume dùng cho scaled flow T14; không tham gia trực tiếp z-score raw flow T17. NaN volume đơn lẻ không tự làm z-score thiếu.

Mẫu = readiness branch ∩ controls hữu hạn ∩ z_k hữu hạn ∩ target hữu hạn. Không ép tập con hoặc mất k−1 ngày đầu. Validator dựng ngày kỳ vọng cho từng scenario rồi so đúng thứ tự, số lượng và giới hạn ngày; lưu membership Parquet. Common_sample thêm giao điều kiện hợp lệ k=1,3,7. HAC từ chối mẫu có khoảng trống lịch; không nén khoảng trống thành ngày liên tiếp.

Mỗi scenario: controls và controls+flow cùng ngày, OLS có intercept, HAC Bartlett/Newey–West T15. Holm trong từng trục gồm hai branch; báo p thô. Không coi các trục là một họ kiểm định toàn cục để chọn kết quả thuận lợi.

T16 giữ event PIT của release, hai chính sách nonoverlap/all_events_sensitivity. Báo n, Jaccard, post−pre log RV/log volume và CI bootstrap block theo sự kiện (2.000 lần, block 3, seed ổn định); chỉ có CI khi đủ sự kiện. Là mô tả, không nhân quả/abnormal response. Kịch bản được phép trùng ngày sự kiện/hệ số; không ép khác nhau để PASS.

## Nghiệm thu

1. Phạm vi USDT/ngày/tuần được chấp thuận và thực thi; token ngoài scope bị từ chối.
2. Upstream/base xác minh trước grid; tất cả scenario hoàn thành, ngày mẫu đúng kỳ vọng, k=1/target gốc khớp T14.
3. Mutation/truncation không thay quá khứ; beta/SE HAC khớp ma trận; Holm không nhỏ hơn p thô.
4. Hai lần tính trong CLI và hai tiến trình CLI riêng khớp hash artifact. Validator riêng tái tạo output và xác minh source/input/output/report.
5. Validator riêng tính z bằng lát cắt lịch sử NumPy, target bằng lookup ngày tương lai, membership và beta/SE cho toàn bộ 58 dòng hồi quy.
6. Ca kiểm soát: thiếu raw giữa kỳ, readiness muộn, thiếu volume; ngày mẫu sai/thừa/thiếu/trùng; candidate đổi ngày/threshold; artifact/config/review thay đổi; token không hỗ trợ; base sai dừng trước grid. Theo quy ước dự án, xóa mã/dữ liệu test giả sau đạt, giữ bằng chứng lịch sử và validator dữ liệu thật.

`computation_validated` xác nhận tính toán; `task_complete_within_approved_scope` xác nhận phạm vi đã chốt; independent review phải đạt riêng. Không cờ nào chứng nhận đa token, nhân quả hoặc hoàn tất RQ3. Transfer giới hạn từ 500.000 USDT nên mạng/số giao dịch chỉ mô tả mạng con giao dịch lớn. T17 không thay T18 hoặc untouched out-of-sample theo blueprint.

## Chạy

```text
python T17_Robustness.py
python scripts/validate_t17_release.py
```

Output `data/processed/t17/`: `t17_regression_robustness.parquet`, `t17_regression_summary.parquet`, `t17_event_robustness.parquet`, `t17_scenario_plan.parquet`, `t17_sample_membership.parquet`, `t17_validation.parquet`, `t17_report.md`, `t17_regression_robustness.png`, `t17_summary.json`, `t17_independent_review.json`. Không CSV. Source/config/input/output có SHA-256; thay nguồn phải chạy/nghiệm thu lại. Không tự upload GitHub/HF.
