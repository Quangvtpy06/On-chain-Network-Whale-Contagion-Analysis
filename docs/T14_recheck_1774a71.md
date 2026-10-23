# T14 — kiểm tra lại bản 1774a71

Ngày 23/10/2026. Source: GitHub main `1774a71dd35265fc6b524fff75e3471ddca33136`. HF đầu vào: `team-crypto/Market-data-crypto-project`, revision `5cd5603bd8493e60c6adabb96200266769929c40`.

## Kết luận phạm vi

Các sửa code về nhánh RV phút, kiểm tra timestamp lệch giây và cấu hình scope đã có hiệu lực. Vẫn còn thiếu một đầu vào trong gói phát hành: config yêu cầu file phút gộp không có trên snapshot HF hiện tại. Readiness đầu vào dự báo cũng vẫn phụ thuộc cờ RQ3 upstream như trước. Không sửa nguồn/config/gate hoặc push dữ liệu trong lần review này.

Bằng chứng kiểm định được lưu tại [T14_recheck_1774a71_evidence.json](T14_recheck_1774a71_evidence.json). Phải phân biệt chạy nguyên trạng với chạy sau khi reviewer chuẩn bị đầu vào tạm.

## 1. Nhánh phút đã được nối đúng

Config dùng `market_1m`, 1.440 bars và sensitivity 288 bars. `load_inputs` tạo key `minute`; `build_features` gọi `realized_volatility_minute` và truyền cả tham số sensitivity. Sau khi chuẩn bị đầu vào thật, output có RV 1m, RV 5m, `n_minute_returns`, `n_5m_returns`.

Đã đối chiếu độc lập 943.200 nến/943.199 minute returns trên 655 ngày. RV 1m sai số tối đa 2,38e-16; RV 5m sai số tối đa 1,90e-16. Có 654 ngày RV hợp lệ; ngày đầu thiếu close trước mẫu nên RV là NaN theo chính sách đã công bố. Target single_day h1/h3/h7 và HAR 7/30 ngày đều khớp phép tính độc lập.

Ngày 02/01/2025: RV 1m = 0,0006503000899874552; RV 5m = 0,0006148427672870045. Không còn kết quả hourly cũ khi dùng đầu vào phút đã chuẩn bị.

## 2. Kiểm tra UTC phút đã sửa

12 ca kiểm tra hàm phút đều đạt: công thức 1m/5m, số return, first-day boundary, duplicate, close=0, close=NaN, thiếu phút, timestamp lệch 30 giây, 1 microsecond và 1 nanosecond. Ba loại lệch thời gian đều bị từ chối, không làm tròn để che lỗi.

## 3. Warm-up và bảo vệ all-missing tiếp tục đúng

Output eligibility có 30 dòng no_cohort, 30 dòng insufficient_flow_history và 595 dòng ok. Các ngày thiếu lịch sử không bị ghi nhầm là missing_input. Ca xóa toàn bộ RV/HAR/target vẫn bị validator từ chối.

## 4. Vẫn thiếu file đầu vào trong gói HF

Lệnh CLI nguyên trạng thoát mã 1 với FileNotFoundError tại:

`market/processed/ohlcv_1m/ETHUSDT_1m_2025-2026.parquet`

Đã kiểm tra metadata snapshot HF: không có file gộp này; có 655 file ngày `ETHUSDT_1m_YYYY-MM-DD.parquet`. Schema ngày T06 dùng cột `minute` hoặc DatetimeIndex; loader mới lại yêu cầu file gộp có `datetime_utc`, `close`.

Để kiểm tra phần tính toán phía sau, reviewer tải 655 file tại revision đã ghim, kiểm tra lịch 1.440 phút/ngày, chuyển timestamp sang `datetime_utc`, ghép tạm 943.200 dòng thành đúng file config yêu cầu; đồng thời tải daily market. Không thay nguồn hoặc config. Đây là chuẩn bị dữ liệu cho review, không chứng minh file gộp đã được bàn giao hoặc đã có trên HF.

Cần chọn một cách hoàn tất trước khi team tái lập:

- Loader đọc trực tiếp thư mục 655 file T06, chuẩn hóa schema và hash từng file thực dùng; hoặc
- Bàn giao bước tạo file gộp có thể tái lập, phát hành file gộp lên HF cùng manifest/provenance, ghi rõ SHA-256 và quan hệ với 655 file nguồn.

Không chỉ sửa tên đường dẫn thành thư mục vì `pd.read_parquet(..., columns=['datetime_utc','close'])` hiện vẫn không khớp schema phút T06. Bằng chứng review giữ SHA-256 của cả 655 file nguồn và file gộp được tạo tạm.

## 5. Scope đã đặt; readiness contract chưa thay đổi

`whaleflow_scope` hiện là `v2_activity_cohort`, phù hợp phương án giữ membership/rank v2 và báo overlap. Không còn lỗi scope null.

Tuy nhiên, phần readiness vẫn yêu cầu `t07_gate['ready_for_rq3_pit_forecast']`; nhánh WhaleFlow yêu cầu thêm cờ tương ứng của T12. Hai cờ upstream hiện vẫn false. Cần làm rõ ai nghiệm thu đầu vào dự báo downstream hoặc phê duyệt bổ sung nào còn cần; không sửa tay các cờ T07/T12 để vượt qua. T15/T16 trực tiếp trả lời RQ3, không phải T14. Readiness false ở đây là trạng thái/hợp đồng dùng đầu vào, không phải yêu cầu T14 phải trả lời RQ3.

## Tái lập và dọn dữ liệu

Lượt kiểm định đầy đủ, so hash hai lần và trạng thái readiness thực tế được ghi trong evidence JSON. Không dùng --skip-reproducibility. Dữ liệu ghép, output và ca test chỉ phục vụ review được dọn sau kiểm tra; chỉ giữ MD/JSON chứng cứ. Output chính trên HF không bị thay thế.
Kết quả cuối sau chuẩn bị đầu vào: CLI exit code 0; 64/64 kiểm tra tích hợp PASS; 5/5 bảng so hash hai lần khớp; 12/12 ca hàm phút và 11/11 đối chiếu độc lập đạt. computation_validated=true, retrospective_analysis_ready=true; cả hai pit_forecast_ready_* vẫn false vì cờ RQ3 upstream. Đã hoàn tất dọn dữ liệu tạm.
