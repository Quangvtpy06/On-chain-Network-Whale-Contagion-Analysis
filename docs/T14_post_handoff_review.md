# T14 — review sau bàn giao T07/T12

Ngày kiểm tra: 23/10/2026. **Đạt phần tính toán đã triển khai, chưa đạt toàn bộ yêu cầu bàn giao.** Không sửa nguồn T14 hoặc cờ gate trong lần review này.

## Phiên bản và thực chạy

Đã fetch và fast-forward checkout tới GitHub main `0023218eb576c62804bddda60129c56e714f6424`; thay đổi T14 ở commit `3fbdd21827fcf569613e49d072b806a2947db0c9`. Đầu vào HF được ghim revision `5cd5603bd8493e60c6adabb96200266769929c40`, dataset `team-crypto/Market-data-crypto-project`.

Chạy `T14_Flow_Volatility.py` bằng Python 3.12.5 của PyCharm, không dùng `--skip-reproducibility`: exit code 0. Kết quả có 655 dòng feature, 66 cột ngoài date; 6 bảng Parquet và 2 JSON, không sinh CSV. Output chỉ phục vụ review, không xuất bản lên HF.

Bằng chứng bàn giao: [T14_post_handoff_review_evidence.json](T14_post_handoff_review_evidence.json), gồm hash nguồn/đầu vào/đầu ra, summary, từng dòng validation và đối chiếu độc lập.

## Kết quả đã đạt

- **60/60** dòng kiểm tra tích hợp PASS, gồm lịch, chiều flow, CEX internal/external, ví dụ tính tay, NaN khác 0, ranh giới nhãn tại cutoff, truncation và future-label mutation ở 4 cutoff.
- **5/5** bảng được pipeline tái tính có SHA-256 giống nhau giữa hai lần chạy. Bảng validation không thuộc danh sách 5 bảng được so hash hai lần; không suy rộng kết quả sang tất cả output.
- **27/27** đối chiếu bổ sung đạt: daily PIT flow, overlap, coverage, normalization tính độc lập, RV **1 giờ theo code hiện có**, target h1/h3/h7, cutoff và các ca sửa protocol/input/output/cohort hash bị từ chối.
- Loader dùng registry T07 approved và cohort T12 v2, kiểm tra hash thực tế. Không thấy trộn cohort v1 hoặc nhãn hồi cứu vào tập PIT.
- PIT NetFlow dùng C_D; chỉ CEX, tách CEX→CEX, chuẩn hóa từ chính flow PIT bằng quá khứ. Có 306 endpoint, khả dụng đủ 655 ngày; coverage endpoint toàn kỳ **21,2014489%**, không phải recall CEX.
- Giữ membership T12, overlap đúng **26 địa chỉ / 6.289 member-days**; 30 ngày chưa có cohort giữ NaN.
- Target chốt `single_day`: log RV của đúng D+h. Cutoff bằng D+1 00:00 UTC; predictor/target và nhánh PIT/hồi cứu được tách rõ.

## Đối chiếu các phần bàn giao

| Phần | Kết quả | Cần xử lý |
| --- | --- | --- |
| 1. Config, loader, gate/history T07 và cohort T12 v2 | Đạt kiểm tra thực chạy | Không phát hiện sai nhánh đầu vào |
| 2. CEX NetFlow as-of, normalization, coverage | Đạt số học và quy tắc as-of | Làm rõ trách nhiệm nghiệm thu readiness downstream |
| 3. WhaleFlow và overlap | Đạt phần triển khai/report | Scope vẫn null, chưa chốt trước T15 |
| 4. Market, target, cutoff | Đạt target/cutoff theo code; chưa khớp đặc tả | Code dùng 1h, chưa có kiểm tra 1.440 phút và RV 5m |
| 5. Validation, reproducibility, outputs | Đạt nhiều kiểm tra; chưa đủ nghiệm thu toàn bộ | Bỏ lọt RV/target thiếu toàn bộ; trạng thái warm-up sai; MD còn cũ |

## Các phát hiện cần xử lý

### 1. RV/target dùng 1h, khác đặc tả 1m/5m — ưu tiên cao

`src/flow_volatility.py:270` tính sum bình phương return hourly; `config/t14.yaml:18` đọc `market_1h`, dòng 39 đặt 24 bars/ngày. Đặc tả `docs/T14_flow_volatility_specification.md:26` lại cam kết 1m, 1.440 returns/ngày và sensitivity 5m. Output có `n_hourly_returns`, không có `rv_5m`, `log_rv_5m`, `n_returns` như tài liệu. Thực chạy có 654 ngày đủ 24 returns; ngày đầu có 23 và RV=NaN.

Mẫu độc lập ngày 02/01/2025 từ cùng snapshot HF: 1.440 returns phút cho RV=0,0006503000899875011; T14 hourly cho 0,0005685291109684245, thấp hơn khoảng **12,57%**. Đây là tần suất lấy mẫu, không phải độ chính xác lưu datetime us/ns.

Cần triển khai minute loader, lịch UTC/duplicate/missing/close>0, first-return boundary và sensitivity 5m theo bàn giao; hoặc nhóm ban hành thay đổi phương pháp chính thức trước T15 nếu chủ động chọn hourly. Không chỉ đổi tên cột hoặc đặt 1.440 bars khi vẫn đọc dữ liệu hourly. RV hourly tính đúng không chứng minh đáp ứng đặc tả minute.

### 2. Validator PASS khi toàn bộ RV/target không còn hợp lệ — ưu tiên cao

Tái hiện trên bản sao bảng trong bộ nhớ: đặt RV, realized_vol, log_RV, HAR, ba target thành NaN; `n_hourly_returns=0`. Hàm `fv.validate()` tại `src/flow_volatility.py:688` vẫn trả tất cả PASS. Các điều kiện dùng dropna hoặc chỉ xét dòng RV không-null đúng trên tập rỗng. Pipeline dùng tất cả status PASS làm một phần điều kiện computation_validated tại `T14_Flow_Volatility.py:226`.

Cần kiểm tra độ phủ market/return theo lịch và chính sách missing; bảo đảm đủ predictor/target cho từng nhánh/horizon. Ca toàn bộ RV/target thiếu phải thất bại hoặc đóng readiness. Ngày đầu có thể thiếu return do không có close ngoài mẫu, phải xét theo quy tắc boundary đã công bố. Dữ liệu thật lần này không thiếu toàn bộ RV; phát hiện nói về lỗ hổng validator.

### 3. Scope WhaleFlow chưa chốt

`config/t14.yaml:32` vẫn `whaleflow_scope: null`. Code giữ W và dùng W\C_D ở biên cohort→CEX, báo overlap, không tạo top50 mới. Cần nhóm chấp thuận scope `v2_activity_cohort` hoặc phối hợp T12 phát hành cohort phiên bản mới trước T15. Review không tự chọn hoặc sửa gate.

### 4. Eligibility nhầm warm-up với input thiếu

`src/flow_volatility.py:470` xác định warm-up theo vị trí đầu toàn mẫu thay vì số raw flow quá khứ hợp lệ. **30 ngày từ 31/01 đến 01/03/2025** có raw WhaleFlow PIT nhưng bị ghi `whaleflow_pit_z_status=missing_input`; thực chất chưa đủ 30 raw flow trước đó để tính z-score.

Cần phân biệt no_cohort, insufficient_flow_history, zero_variance, missing_input. Eligibility hiện là complete-case số học, không phải chứng nhận nhánh đã duyệt: có 594/592/588 dòng đủ dữ liệu PIT WhaleFlow h1/h3/h7 dù scope/readiness còn đóng. T15 phải kiểm tra readiness bên cạnh eligibility.

### 5. Đặc tả còn phiên bản cũ

`docs/T14_flow_volatility_specification.md:5` ghi t14_v1; dòng 23 ghi t12_lagged_v1; dòng 24 nói sidecar rỗng/PIT NaN; đoạn readiness còn yêu cầu pit_cex_labels.enabled. Code hiện dùng v2 và registry approved, có PIT flow đủ 655 ngày. Cần đồng bộ schema cột, scope/overlap, outputs, sampling RV, target và readiness với bản chạy cuối.

### 6. Readiness đầu vào dự báo bị phụ thuộc cờ upstream ngoài phạm vi nghiệm thu T14

Summary thực chạy: computation_validated=true, retrospective_analysis_ready=true, cả hai pit_forecast_ready_* = false. CEX bị chặn bởi t07_rq3_pit_gate_closed; WhaleFlow bị chặn thêm scope null và cờ RQ3 T07/T12. `T14_Flow_Volatility.py:230` yêu cầu cờ forecast T07 cho CEX và cả T07/T12 cho WhaleFlow, dù endpoint/cohort gate cần thiết đã mở.

Cần làm rõ hợp đồng: upstream chứng nhận nhãn/cohort; T14 nghiệm thu xây feature/target và sử dụng chúng; **T15/T16 trực tiếp trả lời RQ3 theo Blueprint08**. Nếu T14 cần được nghiệm thu độc lập thì không chỉ chờ cờ RQ3 upstream luôn false. Nếu nhóm giữ phê duyệt bổ sung phải chỉ rõ người phê duyệt, bằng chứng và điều kiện. Không sửa tay cờ T07/T12. T14 chưa trả lời RQ3 không phải lỗi; đây là hợp đồng readiness cho đầu vào dự báo.

Split train/test và đánh giá horizon chồng lấn phải phối hợp T18/T15/T16 trước mô hình; review này chưa xác nhận chúng đã đóng băng.

## Kết luận

Có thể tiếp tục từ bản sửa này: phần loader/gate, CEX as-of, normalization PIT và overlap đã được kiểm thử thành công. Chưa ghi T14 pass toàn bộ hoặc coi mọi output là đầu vào dự báo đã nghiệm thu. Ưu tiên thống nhất RV/target, tăng validator chống thiếu dữ liệu, chốt scope và cập nhật MD/readiness, rồi chạy lại kiểm định và phát hành manifest mới.