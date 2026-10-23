# T14 — kiểm tra lại bản a85434e

Ngày 23/10/2026. Đã lấy GitHub main `a85434ecf5c0b972d036eb189d0c340fa9de34bf`, chạy lại nguyên trạng CLI với đầu vào HF revision `5cd5603bd8493e60c6adabb96200266769929c40`. Không sửa nguồn/config/gate, không push output thử lên HF.

**Kết luận: lỗi 30 ngày warm-up và validator bỏ lọt RV/target thiếu toàn bộ đã được sửa. T14 vẫn chưa pass toàn bộ bàn giao vì nhánh phút chưa nối vào CLI mặc định và kiểm tra lịch phút còn thiếu.**

Bằng chứng: [T14_recheck_a85434e_evidence.json](T14_recheck_a85434e_evidence.json). Báo cáo trước được giữ nguyên để đối chiếu lịch sử.

## Kết quả thực chạy

- CLI exit code 0; đủ 655 dòng feature.
- 64/64 dòng kiểm định tích hợp PASS; 5/5 bảng có hash giống nhau giữa hai lần tính.
- Thực hiện 16 ca đối chiếu/hồi quy bổ sung; 15 đạt kỳ vọng, 1 không đạt: hàm RV phút chấp nhận timestamp lệch 30 giây.
- T07/T12 hash vẫn được xác thực; overlap tiếp tục đúng 26 địa chỉ / 6.289 member-days.

## Những điểm đã sửa đúng

1. **Warm-up z-score:** 01–30/01/2025 có 30 dòng `no_cohort`; 31/01–01/03 có 30 dòng `insufficient_flow_history`; từ 02/03 có 595 dòng `ok`. Raw flow của 30 ngày thiếu lịch sử vẫn được giữ; không điền z-score=0. Các ca `zero_variance`, thiếu raw flow hiện tại và cửa sổ quá khứ đủ 30 quan sát cũng đạt.
2. **RV/target thiếu toàn bộ:** khi đặt RV/HAR/target thành NaN, validator nay báo FAIL tại các kiểm tra coverage/RV. Chỉ đặt target thành NaN cũng bị từ chối. Đã khắc phục việc điều kiện đúng trên tập rỗng. Ngưỡng coverage hiện hard-code 90%; nên ghi rõ trong phương pháp nghiệm thu.
3. **Hàm phút và sensitivity:** đã thêm `realized_volatility_minute`. Ca giả có đúng 1.440 returns phút và 288 returns 5 phút trong ngày thứ hai; RV phút khớp phép tính NumPy độc lập. Duplicate và close không dương bị từ chối. Truncation đã giữ/cắt input minute.
4. **Đặc tả:** đã chuyển sang v2, history CEX và cohort v2; bổ sung định nghĩa phút/5 phút và warm-up. Không còn mô tả sidecar rỗng như trước.

## Các điểm còn cần sửa/chốt

### 1. Hàm RV phút chưa được nối vào lệnh chạy mặc định — ưu tiên cao

`T14_Flow_Volatility.py:119` vẫn chỉ đọc `market_1h`, trả key `hourly`. `config/t14.yaml` vẫn đặt `bars_per_day: 24` và không có đầu vào phút. Trong `src/flow_volatility.py:425`, điều kiện chọn nhánh phút chỉ xảy ra khi có key `minute` hoặc bars >24, nên CLI hiện tiếp tục chạy hourly.

Bằng chứng thực chạy: không có `n_minute_returns` hoặc `rv_5m`; hash toàn bộ bảng feature vẫn giống bản hourly đã kiểm tra ở commit 0023218. Bảng eligibility đổi đúng theo logic warm-up, nhưng RV và target chưa chuyển sang phút.

Cần sửa loader/config đọc 655 file phút T06, chuẩn hóa schema `minute` hoặc DatetimeIndex sang `datetime_utc`, kiểm tra lịch và đưa vào `inputs['minute']`. Chọn 1.440 bars, sensitivity 288 bars, cập nhật provenance để hash toàn bộ file phút thực dùng. Sau đó chạy lại CLI đầy đủ, truncation/mutation, hai lần tính, đối chiếu RV/target phút với dữ liệu thật. Không chỉ đổi bars sang 1.440 khi vẫn đọc hourly.

### 2. Hàm phút chưa kiểm tra căn đúng lưới UTC — ưu tiên cao

`src/flow_volatility.py:270` kiểm tra duplicate, giá và khoảng cách liên tiếp nhưng chưa kiểm tra timestamp nằm đúng mỗi phút. Đã thử dịch toàn bộ lịch giả thêm 30 giây: hàm vẫn chấp nhận và cho ngày thứ hai đủ 1.440 returns, thay vì từ chối. Sensitivity 5m chọn theo minute modulo 5 nên cũng không phát hiện lệch giây.

Cần kiểm tra second/microsecond/nanosecond bằng 0 và lịch kỳ vọng 1.440 phút từng ngày, sau khi thống nhất datetime unit. Ngày thiếu phải báo missing/NaN theo chính sách; không làm tròn timestamp để che lỗi. Tái kiểm tra trường hợp lệch 30 giây, lệch microsecond, duplicate, thiếu phút và ranh giới ngày đầu.

### 3. Scope và hợp đồng readiness vẫn chưa chốt

`config/t14.yaml` vẫn `whaleflow_scope: null`, trong khi đặc tả mới mô tả đã chọn Phương án 1. Cần ghi nhận quyết định nhóm và đồng bộ config; review không tự lựa chọn scope.

Summary vẫn có `pit_forecast_ready_cex=false` do `t07_rq3_pit_gate_closed`; WhaleFlow bị chặn thêm scope null và các cờ RQ3 upstream. Logic này chưa đổi so với review trước. Cần chốt hợp đồng nghiệm thu đầu vào downstream hoặc chỉ rõ phê duyệt bổ sung; không sửa tay cờ T07/T12. T15/T16 trực tiếp trả lời RQ3 theo Blueprint08, việc T14 chưa trả lời RQ3 không phải lỗi của T14.

## Phạm vi nghiệm thu hiện tại

Có thể xác nhận **phần sửa 30 ngày z-score đã pass** và lỗ hổng all-missing RV/target đã được sửa. Chưa xác nhận toàn bộ T14 đáp ứng đặc tả minute hoặc sẵn sàng bàn giao làm predictor đã nghiệm thu cho T15. Cần hoàn tất nối minute loader/config/provenance, kiểm tra lưới UTC, chốt scope/readiness rồi chạy lại và lập manifest phát hành.

Dữ liệu, output và mã test tạm đã được dọn; chỉ giữ báo cáo và bằng chứng JSON. Không thay output chính trên HF.