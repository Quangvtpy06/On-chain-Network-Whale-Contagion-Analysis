# T15 — hồi quy liên hệ giữa dòng tiền và biến động

Protocol `t15_matched_hac_v2`, cấu hình `config/t15.yaml`. Thay cho bản nhánh `182cea7` đã được review ngày 24/10/2026. Các quyết định biến, ngưỡng và mẫu được ghi cấu hình trước lượt chạy sửa lỗi; không chọn lại sau khi xem hệ số.

## Đầu vào và thời điểm

Chỉ đọc release T14 qua `scripts/validate_t14_release.py`. Bắt buộc `t14_inputs_v1`, đúng hash nguồn/config/input/output, policy và readiness của từng nhánh. Không sửa gate T07/T12/T14. Đường dẫn lấy từ config, tương đối với gốc dự án; thiếu control hoặc predictor bắt buộc thì dừng.

- Nhánh `activity_cohort`: `whaleflow_pit_z`, readiness `forecast_inputs_ready_activity_cohort`, predictor set `pit_whaleflow`, eligibility `eligible_pit_whale_h{h}`.
- Nhánh `cex`: `pit_cex_netflow_z`, readiness `forecast_inputs_ready_cex`, predictor set `pit_cex`, eligibility `eligible_pit_cex_h{h}`.
- CEX chỉ là tập endpoint approved quan sát được. Activity cohort là **địa chỉ hoạt động lớn chưa định danh** theo `t12_v2_research_knowledge`, không phải nhà đầu tư cá nhân và không phải cohort public-information-only PIT.
- Biến ngày D khả dụng D+1 00:00 UTC. Target là `log(RV[D+h])`, h=1/3/7, không cộng dồn h ngày. Chuẩn hóa timestamp về nanosecond trước đối chiếu; không làm tròn timestamp lệch lưới.

## Mẫu và mô hình

Trong mỗi nhánh/horizon, cố định **cùng các ngày** cho ba mô hình: baseline controls; primary controls + flow; robustness controls + flow hồi cứu. Mẫu là giao eligibility PIT/hồi cứu và complete-case của controls, cả hai flow và target. Với dữ liệu hiện tại, việc ghép nhánh hồi cứu không làm giảm thêm mẫu PIT; quy tắc này phục vụ so sánh theo cặp và được ghi vào `t15_sample_membership.parquet`.

Controls cố định: `ret_1d`, `log_volume_usdt`, `log_rv`, `log_rv_week`, `log_rv_month`, `log_trade_count`, `taker_imbalance`, `spread_cs_proxy`, `parkinson_var`. Baseline dùng đầy đủ cùng controls, chỉ thiếu flow. Không chọn biến theo p-value; danh sách phải thuộc predictor set T14. Không đưa target vào X. Ghi predictor thực tế, số quan sát, mốc đầu/cuối và SHA-256 các ngày của từng mẫu.

OLS có intercept. Kiểm tra mẫu liên tục theo ngày cho HAC, ít nhất 60 quan sát, không infinity, không predictor hằng hoặc rank-deficient. Newey–West Bartlett HAC:

`L = min(max(h, ceil(4*(n/100)^(2/9))), floor(n/5))`, finite-sample correction `n/(n-k)`.

Đây là quy tắc bandwidth cố định để xử lý phụ thuộc chuỗi thời gian, không khẳng định target single-day tạo residual MA(h−1) một cách tất yếu. Kiểm tra điều kiện ma trận trên X chuẩn hóa để đánh giá số học; fit trên đơn vị gốc.

Điều chỉnh Holm cho 6 phép kiểm định flow chính (2 nhánh × 3 horizon); 6 phép robustness hồi cứu là họ riêng. `p_holm` trong bảng coefficient là p đã điều chỉnh của **flow trong mô hình**, không phải p đã điều chỉnh cho các control. Không dùng nhánh hồi cứu làm bằng chứng dự báo chính.

## Sản phẩm và kiểm định

`data/processed/t15/` chứa bảng coefficients, summary, sample membership, validation (Parquet); report Markdown; biểu đồ hệ số/CI; summary và independent review JSON. JSON dùng boolean thật; NaN chỉ thành null ở JSON. Không xuất CSV.

Pipeline tính hai lần, so hash nội dung, kiểm tra source/input/config không thay đổi trong lúc chạy. Validator trong tiến trình riêng kiểm tra release và tính lại; đồng thời đối chiếu beta và HAC SE bằng đại số ma trận, không gọi hàm fit của pipeline. Nghiệm thu sửa lỗi còn chạy hai CLI với `PYTHONHASHSEED` khác nhau, so SHA-256 Parquet, report, PNG và summary.

## Giới hạn diễn giải

Đây là liên hệ lead–lag **trong mẫu**, không phải causal effect hoặc kiểm định dự báo ngoài mẫu. Chênh lệch R² nhỏ hay p không có ý nghĩa không chứng minh không tồn tại tác động. Đánh giá forecast theo thời gian thuộc T18. Transfer chỉ thuộc mạng con từ 500.000 USDT, không phải toàn bộ dòng tiền exchange. Khả năng bao phủ CEX và danh tính cohort tiếp tục giới hạn RQ3; không tự động đặt `rq3_answered=true`.

## Chạy

```text
python T15_Volatility_Regression.py
python scripts/validate_t15_t16_release.py --task t15
```

`--config` chỉ định config; `--output-dir .cache/...` dùng cho lượt đối chiếu tạm. Sửa config/source sau nghiệm thu cần chạy và kiểm định lại.
