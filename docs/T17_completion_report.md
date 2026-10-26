# T17 — Hoàn thành trong phạm vi USDT, protocol v2

Ngày nghiệm thu local: 26/10/2026. Protocol `t17_usdt_daily_weekly_v2`. Chủ dự án đã chốt USDT; graph windows ngày và tuần ISO. **Chưa kiểm tra khả năng khái quát sang token khác.** Không coi token bị loại khỏi phạm vi là một thử nghiệm đa token đã đạt.

## Thay đổi

- Bỏ validator ép mất đúng k−1 ngày. Dựng tập ngày kỳ vọng theo từng scenario từ readiness, controls, rolling raw-flow z và target; so đúng thứ tự/ngày/số lượng/giới hạn, lưu membership Parquet.
- Xác minh T15/T16 bằng source/config/input/output hash, independent review, policy và bằng chứng tái lập trước khi đọc bảng. Artifact thay đổi hoặc review không đạt bị từ chối.
- T16 đối chiếu candidate theo khóa event/date cùng signal availability, threshold và cờ candidate, thay vì chỉ đếm tổng.
- Tái tạo base trước sensitivity grid; base không khớp thì dừng ngay. Không ép kịch bản phải có hệ số hoặc ngày sự kiện khác nhau.
- Bổ sung flow k=1/3/7 trên cùng giao ngày hợp lệ theo branch/horizon; giữ cả kết quả dùng mọi ngày hợp lệ mỗi k.
- Chốt phạm vi trong config, summary, scenario plan, report, đặc tả và README. Token ngoài USDT bị từ chối; graph window không có 30 ngày hay 8 tuần. Số 8 là minimum history của chỉ số tuần, không phải graph window.
- Giữ công thức z-score raw flow: volume chỉ phục vụ scaled flow, không tự làm z-score thiếu khi NaN. Thiếu raw vẫn lan qua rolling; HAC từ chối khoảng trống lịch, không điền 0.

## Kiểm định

| Nội dung | Kết quả |
|---|---|
| Hồi quy | 58 dòng, không scenario thất bại |
| Event study | 30 dòng |
| Kiểm tra trong pipeline | 136 PASS, 0 FAIL |
| Ca pytest có kiểm soát | 20 PASS |
| Hai tiến trình CLI riêng | 9/9 artifact giống SHA-256, lần hai PYTHONHASHSEED=137 |
| Kiểm định riêng | Tái tạo toàn bộ bảng/report, kiểm tra hash và 58 kiểm tra số học độc lập đều đạt |

Các ca kiểm soát gồm NaN raw giữa kỳ, readiness muộn, NaN volume, ngày mẫu ngoài kỳ/bị mất/trùng, sai n hoặc ngày cuối; candidate đổi ngày/threshold/trùng khóa; source/review/artifact thay đổi; token/scope không được hỗ trợ; base sai dừng trước grid; cùng mẫu k=1/3/7; fit HAC thật từ chối khoảng trống.

Validator dữ liệu thật `scripts/validate_t17_release.py` được giữ lại: tính z bằng lát cắt NumPy, target bằng lookup RV tương lai, kiểm tra tập ngày và OLS/HAC bằng ma trận cho cả 58 dòng, rồi đối chiếu output đã lưu. Mã test giả, dữ liệu test và bản chạy dư được xóa sau đạt theo quy ước dự án; bằng chứng lịch sử lưu tại `docs/T17_v2_acceptance_evidence.json`. Không mô tả các ca giả đã xóa như một bộ test tự động còn tồn tại.

## Kết quả nghiên cứu và giới hạn

Không kịch bản hồi quy flow nào có p Holm dưới 0,05 trong các họ đã chạy. Dấu hệ số thay đổi theo horizon/cửa sổ: với flow_window thông thường, cohort cùng dấu base 7/9, CEX 5/9; họ cùng mẫu cũng lần lượt 7/9 và 5/9. Không thể tuyên bố tín hiệu flow bền vững chỉ vì pipeline PASS.

CI event là exploratory pointwise; không suy nhân quả từ post−pre. Toàn bộ output là liên hệ trong mẫu của mạng con transfer từ 500.000 USDT; activity cohort là địa chỉ hoạt động lớn chưa định danh. V2 sửa sau review v1, không được trình bày như đăng ký trước mọi kết quả nghiên cứu. Không kết luận về token khác, nhà đầu tư cá nhân hay untouched out-of-sample. `rq3_answered=false` được giữ nguyên; T17 không tự hoàn tất RQ3.

## Bàn giao

- `data/processed/t17/`: 6 Parquet, 1 PNG, 1 report Markdown, summary JSON và independent review JSON.
- `config/t17.yaml`, `T17_Robustness.py`, `src/robustness.py`, `src/t17_release_inputs.py`.
- `scripts/validate_t17_release.py`, `scripts/prepare_t17_release.py` và whitelist T17 của publisher.
- `docs/T17_specification.md`, README và bằng chứng nghiệm thu.
- Manifest chỉ chứa output/config T17 đã nghiệm thu; không tự upload. Phạm vi chấp nhận là **T17 USDT ngày/tuần**, không phải toàn bộ RQ3.
