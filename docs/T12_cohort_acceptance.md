# T12: nghiệm thu cohort trước khi mở gate T14

**Tài liệu này ghi điều kiện và kết quả v1.** V1 giữ nguyên để đối chiếu.
Nhóm đã ban hành [protocol v2](T12_protocol_v2.md) cho scope địa chỉ hoạt động lớn,
cho phép Unknown như giới hạn đo lường và yêu cầu bản độ nhạy hồi cứu riêng.
Gate v2 nằm tại `data/processed/t12/v2/t12_downstream_gate.json`, không phải gate v1 bên dưới.

Gate này chỉ áp dụng cho WhaleFlow theo cohort. Nó không xác nhận chủ sở hữu là nhà đầu tư cá nhân, không chứng nhận nhãn CEX của T14 là point-in-time và không chặn các nhánh volatility/large-edge độc lập.

Đã có [bảng nguồn 40 địa chỉ để thành viên mở kiểm tra](T12_source_review_packet.md) và
[đề xuất xử lý lịch sử nhãn/79 địa chỉ](T12_label_history_resolution.md). Overlap hồi cứu
là chẩn đoán contamination, không tự chứng minh scoring dùng dữ liệu tương lai;
điều kiện gate v1 là bảo thủ và phải đổi protocol công khai nếu đổi scope cohort.

## Kết quả kiểm tra 22/10/2026

- Tính lại hai lần: 7/7 Parquet design khớp SHA-256.
- Tham chiếu độc lập: 655/655 ngày đạt, 31.250 lượt thành viên; max score error khoảng 1,06e-12.
- Kiểm tra nhóm rỗng, một thành viên/std=0 và đồng hạng đạt. Thay giá trị ngày dự báo và tương lai không làm đổi cohort đầu tiên đủ lịch sử trong code production. Mã và dữ liệu tạm của các ca kiểm tra đã xóa, giữ t12_cohort_controls.json.
- Negative control trên bản sao dữ liệu thật: sửa byte của cohort, giả lập gate cũ đang mở; validator từ chối hash sai và đóng gate. Bản sao đã xóa, output chuẩn không bị sửa bởi ca này.
- 79 địa chỉ overlap hạ tầng theo T07 hồi cứu, tổng 10.948 lượt địa chỉ–ngày. Đây là chẩn đoán contamination, không phải nhãn PIT mới hoặc xác minh độc lập danh tính.
- Tập CEX T14 hiện loại 10.702 lượt thành viên khỏi cohort; còn các loại hạ tầng khác cũng cần xem xét. Việc loại tập CEX hồi cứu tại T14 không biến cohort thành PIT.
- Có 40 địa chỉ cần review: hợp của 22 địa chỉ raw/log audit và 20 địa chỉ nổi bật sau lọc, đã loại trùng.
- Gate canonical vẫn false, technical_cohort_validation_passed=true. Không được báo T12 đã đủ điều kiện mở WhaleFlow chỉ vì các phép tính đều đúng.

Ví dụ overlap T07: 0x21a31ee1afc51d94c2efccaa2092ad1028285549 và 0xdfd5293d8e347dfe59e90efd55b2956a1343963d mang nhãn Binance, 0x46340b20830761efd32832a74d7169b29feb9758 mang nhãn Crypto.com; mỗi địa chỉ có mặt 625 ngày trong cohort v1. Các tên này được trích từ T07, không được coi là nhãn mới do trợ lý xác minh.

## Thay đổi

`scripts/validate_t12_cohort.py` tính lại từng cohort trực tiếp từ T09 trong cửa sổ [D−30,D). Validator không nhập hàm chấm điểm/cohort production; tính z-score bằng moment dân số với math.fsum. Kiểm tra đủ ngày, warm-up, tập địa chỉ, thứ hạng, value/tần suất/PageRank 30 ngày, net/gross, cutoff, protocol và hash đầu vào/output. Cấu hình scoring/filter t12_lagged_v1 giữ nguyên, không chọn ngưỡng theo T15.

Sau hai lượt tái lập design, `src.whale_score_design` tự gọi validator này. Gate được đánh giá từ kết quả thực tế; không còn chỉ giữ trạng thái mặc định mà không có kiểm định cohort sau lọc. Khi validator bắt đầu, cờ canonical bị đóng trước để không giữ một gate mở của lần chạy cũ khi kiểm định lỗi.

Đầu ra bổ sung, đều dưới `data/processed/t12/`:

- `t12_cohort_validation.parquet`: một dòng mỗi ngày, so sánh tham chiếu độc lập.
- `t12_cohort_review.json`: hash, kết quả, địa chỉ còn chờ review và gate.
- `t12_cohort_review_queue.parquet`: hợp của 20 địa chỉ đầu raw/log đã có trong audit và 20 địa chỉ nổi bật sau lọc cohort. Top sau lọc được chọn theo số ngày top10, số ngày tham gia, mean rank, rồi địa chỉ; đây là quy tắc lấy mẫu review hồi cứu, không thay cohort theo ngày.
- `t12_downstream_gate.json`: cờ canonical mà T14 phải đọc.

Trường `ready_for_cohort_whaleflow` trong snapshot design v1 là trạng thái prototype lúc tạo; bên sử dụng phải đọc gate canonical mới nhất và kiểm tra provenance, không lấy field snapshot làm quyết định toàn task.

## Điều kiện mở gate

1. Các phép tính T12 trước đó, hai lượt design và tham chiếu cohort độc lập đều đạt; config đóng băng và input/output còn khớp hash.
2. Những địa chỉ trong danh sách review phải có thành viên nhóm mở nguồn, ghi rõ người/ngày/kết quả và nhận xét. AI không tự điền người xác minh hoặc coi lookup là nhãn đã xác nhận.
3. Những địa chỉ cơ sở hạ tầng T07 vẫn nằm trong cohort phải được xử lý theo một chính sách danh tính hợp lệ. Không âm thầm loại bằng nhãn cuối kỳ rồi gọi kết quả là PIT; không sửa ngày khả dụng nhãn để đưa vào quá khứ.

Việc đổi chính sách lọc nhãn phải tạo protocol mới có deviation report, giữ nguyên v1 và kết quả độ nhạy. Với dữ liệu hiện có, không thể giải quyết thiếu lịch sử nhãn chỉ bằng sửa code. Nếu chọn cohort hồi cứu, phải dùng gate/phạm vi hồi cứu riêng, không bật cờ dự báo PIT.

## Review của thành viên nhóm

Đọc queue Parquet, mở URL, lưu một bản quyết định ở `data/processed/t12/t12_cohort_human_review.parquet` với các cột:

| Cột | Yêu cầu |
|---|---|
| address | Đúng địa chỉ trong queue; không trùng |
| reviewed_by | Thành viên thực sự kiểm tra |
| reviewed_at | Thời điểm UTC thực tế; không backdate |
| source_url | HTTPS đến nguồn đã mở |
| source_opened_by_human | Boolean true khi đã mở nguồn |
| review_decision | reviewed_unknown / verified_non_infrastructure / infrastructure |
| review_note | Bằng chứng/kết quả hoặc giới hạn khi chưa xác định được |

`reviewed_unknown` chỉ nghĩa đã kiểm tra mà chưa xác định được chủ thể, không phải chứng minh ví cá nhân. `verified_non_infrastructure` cũng không tự tạo nhãn danh tính T07. Khi xác nhận danh tính, vẫn phải nhập nguồn bậc hai qua workflow T07 với source_url, confidence và thời điểm khả dụng thật.

Chạy lại:

```powershell
python -m src.whale_score_design
# Hoặc đánh giá lại gate khi output design không đổi:
python scripts/validate_t12_cohort.py --human-review data/processed/t12/t12_cohort_human_review.parquet
```

Review nguồn mới không tự sửa được các địa chỉ CEX/infra còn nằm trong cohort. Cần giải quyết chính sách/lịch sử nhãn rồi rebuild phiên bản cohort phù hợp, kiểm định lại trước khi mở gate.

## Quy ước bàn giao

Giữ validator dữ liệu thật, báo cáo và bằng chứng JSON/Parquet. Không giữ mã/dữ liệu test giả hoặc các thư mục chạy đối chiếu tạm sau khi kiểm tra xong. Không tự push dữ liệu chưa được nghiệm thu lên HF như một release đã mở gate.
