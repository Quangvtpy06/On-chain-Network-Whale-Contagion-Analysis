# T18 — chia tập theo thời gian và backtest không dùng nhãn train tương lai

Protocol `t18_purged_fixed_origin_v2`, cấu hình `config/t18.yaml`. Runner riêng `T18_Time_Split_Backtest.py`, module tính toán `src/time_split_backtest.py`, I/O/provenance `src/t18_release.py`. Thay thế báo cáo/config T18 dựa trên T15/T16 cũ trong nhánh `841eaa6`; không cần dùng hoặc merge các script cũ từ nhánh đó.

## Thời điểm và phạm vi đã cố định trước lượt chạy mới

- Train feature date: đến **08/06/2026**; test feature date: từ **09/06/2026**. Giữ cutoff cũ, không chọn lại theo OOS score.
- Fit một lần tại **10/06/2026 00:00 UTC**, đúng forecast origin đầu tiên. Dự báo dùng feature ngày D tại `available_at=D+1 00:00 UTC`.
- Target single-day là `log RV[D+h]`, h=1/3/7; nhãn chỉ khả dụng tại **D+h+1 00:00 UTC**. Train chỉ nhận hàng có feature date thuộc train, X/target hợp lệ và `target_available_at <= fit_at`.
- Vì fit được phép diễn ra tại forecast origin đầu tiên nên nhãn RV ngày 09/06 đã biết tại lúc fit. Không được dùng nhãn ngày 10/06 trở đi. Với cutoff này h=1 không cần purge thêm, h=3 purge 2 ngày, h=7 purge 6 ngày.
- Hệ số giữ cố định trong toàn bộ test; không refit, chọn biến hoặc chọn ngưỡng sau khi xem kết quả. Các feature rolling của T14 tại mỗi ngày vẫn cập nhật bằng quá khứ theo quy tắc đã đóng băng; đây không phải việc refit mô hình.
- Chỉ đánh giá target khả dụng đến **18/10/2026 00:00 UTC**. Vẫn ghi dự báo của ngày X khả dụng nhưng chưa có outcome trong dữ liệu; gắn `evaluate=false`, không lấp nhãn bị censor.
- Giai đoạn test đã xuất hiện trong các phân tích toàn mẫu mà nhóm từng xem: đây là **retrospective/pseudo-OOS backtest**, không phải holdout chưa từng được xem. Không suy diễn nhân quả hoặc danh tính nhà đầu tư cá nhân.

## Hợp đồng dữ liệu

T14 bắt buộc qua `validate_t14_release`, đúng `t14_inputs_v1`, hash và policy. T15/T16 được xác minh đọc-only: summary, independent review, toàn bộ artifact, hash source/config/input, bằng chứng hai lần tính và sự thống nhất với T14 hiện tại. Không sửa output hay gate upstream.

Phải hash cả `config/t15.yaml`, `config/t16.yaml` và config T18 trước/sau chạy; mọi đường dẫn tương đối với gốc dự án. Predictor list lấy từ T15 đã nghiệm thu và phải thuộc predictor set T14; eligibility theo đúng nhánh. Không đưa predictor hồi cứu hoặc target vào X. Nhánh CEX chỉ thuộc tập endpoint approved quan sát được; activity cohort giữ policy `t12_v2_research_knowledge`, không gọi thành public-information-only PIT.

## Mẫu và benchmark

Mỗi nhánh/horizon có một train mask và một test-evaluation mask chung cho năm mô hình:

1. `controls_baseline`: 9 controls đã cố định ở T15, có HAR và các control thị trường.
2. `flow_model`: cùng controls, thêm flow PIT đúng nhánh.
3. `har_baseline`: chỉ log RV ngày/tuần/tháng, trên cùng các hàng train/test.
4. `train_mean`: trung bình target trong **train sau purge**, khả dụng lúc fit.
5. `last_log_rv`: log RV gần nhất đã quan sát tại forecast origin.

Ba hồi quy dùng OLS/HAC đã kiểm định của T15; mọi kiểm tra rank, zero variance và số quan sát áp dụng trên train. Không fit scaler trên test. P-value của hệ số train không được dùng chọn mô hình hoặc kết luận khả năng dự báo test.

Metrics: MSE/RMSE/MAE của log RV; R² so với mean test chỉ là chuẩn hóa score, không phải benchmark có thể giao dịch. Có thêm R² relative to train-mean forecast và relative to controls forecast. Báo riêng `mean(loss_flow−loss_controls)`, âm nghĩa là flow có loss thấp hơn trên mẫu này.

CI loss: paired circular blocks **7 ngày lịch**, 5.000 lần, seed 20261025 qua SHA-256 ổn định. Các ngày scoring phải liên tục để không đánh đồng độ lệch hàng với số ngày. Báo CI pointwise 95% và Bonferroni cho sáu so sánh chính. Đây là khoảng thăm dò dưới giả định bootstrap, không bảo đảm coverage hữu hạn mẫu, không phải phép kiểm định nested-model chuyên biệt như Clark–West, không chứng nhận causal effect. Không diễn giải cải thiện nhỏ là bằng chứng dự báo mạnh khi bất định còn bao gồm zero.

## Phần T16 theo thời gian

Giữ nguyên tập sự kiện và ngưỡng của **release T16 mới**, gồm CEX net inflow và activity-cohort net inflow tách biệt. Không dùng tên whale_inflow cũ hoặc coi ứng viên là sự kiện primary đã chọn.

Đọc các cửa sổ đã chọn, phân loại mỗi cửa sổ k=5: train nếu toàn bộ response đến hết train; test nếu toàn bộ response nằm trong test và đã quan sát tại evaluation cutoff; còn lại `boundary_excluded`. Không chọn thêm sự kiện để bù nhóm rỗng. Giữ cả primary nonoverlap và sensitivity all-events, báo riêng.

Báo mean response path và post−pre (`tau=0..5` trừ `tau=−5..−1`). Bootstrap cả event path theo quy tắc T16 đã nghiệm thu. CI chỉ có khi n ≥ max(5, 2×3)=6. Các nhóm rỗng/ít sự kiện vẫn có dòng trạng thái và n, CI null. Đó là phân tích phản ứng mô tả hồi cứu, không phải dự báo hoặc so sánh causal với phản thực.

## Kiểm định và sản phẩm

Output `data/processed/t18/`: sample membership, coefficients, predictions, metrics, daily losses, loss comparison, event partition, event counts, event statistics, validation — **10 bảng Parquet**; hai PNG; report Markdown; summary và independent-review JSON. Không CSV.

Ledger ghi feature/label availability, fit cutoff, purge, prediction/evaluation mask và lý do không dùng mỗi hàng. Pipeline kiểm tra target bằng lookup RV trực tiếp; sửa nhãn sau fit không đổi coefficients/forecasts; bỏ các hàng tương lai không đổi fit hoặc dự báo trước cutoff (sai số số học BLAS cho phép 1e−12). Tính hai lần, so content hash; kiểm tra source/config/input trước–sau.

Validator riêng tính lại release, kiểm tra đủ map hash và đối chiếu độc lập mask theo thời điểm, OLS bằng least squares, dự báo, benchmark, loss và event partition. Trước bàn giao còn chạy hai CLI với hash seed khác nhau và so SHA-256 toàn bộ output. Mã/data test tạm được xóa sau khi đạt; giữ validator dữ liệu thật và bằng chứng kiểm tra.

```text
python T18_Time_Split_Backtest.py
python scripts/validate_t18_release.py
python scripts/prepare_t18_release.py
```

Prepare chỉ tạo manifest scoped T18 và cập nhật manifest mặc định local, không upload. Thay source/config/input sau nghiệm thu cần chạy lại và kiểm định lại. Trạng thái tính toán không tự chuyển `rq3_answered` hoặc cờ nhà đầu tư cá nhân thành true.
