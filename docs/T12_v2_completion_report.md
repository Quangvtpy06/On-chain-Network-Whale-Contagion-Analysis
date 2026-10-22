# T12 v2 — nghiệm thu cohort hoạt động lớn và độ nhạy hồi cứu

Ngày 22/10/2026. Protocol `t12_unidentified_activity_v2`; [quy tắc và điều kiện nghiệm thu](T12_protocol_v2.md), cấu hình `config/t12_v2.yaml`. Không đọc output T15 để lựa chọn quy tắc. Khi freeze không có Parquet T15 cục bộ; không khẳng định kiểm soát lịch sử truy cập của mọi thành viên trên hệ thống khác.

## Kết quả nghiệm thu

- Hai lần chạy toàn bộ trên dữ liệu thật: **12/12 Parquet khớp SHA-256**.
- Tham chiếu độc lập: **1.310/1.310 nhánh–ngày đạt**, gồm 655 ngày mỗi nhánh. Sai số score lớn nhất 1,05516e-12.
- Mỗi nhánh có 30 ngày warm-up, 625 ngày đủ lịch sử và 31.250 lượt thành viên. Có snapshot cho đủ lịch ngày; warm-up không có thành viên.
- Membership, thứ hạng, cutoff và score nhánh chính giữ nguyên v1. Ngưỡng chuyển tiếp/chuẩn hóa không đổi, không chọn lại theo hồi quy.
- Nhánh hồi cứu loại hạ tầng khỏi toàn bộ tập ứng viên trước quantile/z/rank, tính lại top 50 và bổ sung thành viên thay thế; không còn overlap theo bộ lọc T07 đã định nghĩa.
- Kiểm tra rỗng, một node/std=0, đồng hạng/std=0, ví dụ giải tích ddof=0, sửa dữ liệu ngày D/tương lai không đổi cohort D, tham chiếu từ chối score thật bị sửa đều đạt.
- Negative control thực tế: sửa một byte Parquet chuẩn khi gate đang mở, validator từ chối hash sai và đóng gate; đã khôi phục đúng SHA-256 và chạy lại validator độc lập. Kết quả ở `t12_integrity_control.json`.
- Dòng tiền biên cohort đối chiếu tổng net của node T09 theo từng ngày, cả hai nhánh. Đầu ra CEX flow dùng endpoint hồi cứu, không được coi là PIT dự báo.

## Độ nhạy thực tế — không suy luận cá nhân

| Chỉ số | Kết quả |
|---|---:|
| Địa chỉ hạ tầng T07 hiện tại trong cohort chính | 79 |
| Lượt thành viên hạ tầng | 10.948 / 31.250 |
| Tỷ trọng trailing endpoint volume mang nhãn T07 hiện tại | 82,6811% |
| Tỷ trọng trailing endpoint volume thuộc hạ tầng T07 hiện tại | 82,6811% |
| Tỷ trọng trailing endpoint volume chưa được attribution T07 | 17,3189% |
| Jaccard trung vị giữa cohort chính và cohort hồi cứu | 0,470588 |
| Tổng lượt thành viên thay thế | 11.312 |
| Jaccard trung vị liền kề — chính | 0,818182 |
| Jaccard trung vị liền kề — hồi cứu | 0,785714 |
| Tương quan net_to_current_cex giữa hai nhánh | 0,0875014 |
| Chênh lệch tuyệt đối trung bình net_to_current_cex | 337.483.709,60 USDT/ngày |
| Địa chỉ ưu tiên có bảng lookup | 40 |
| Địa chỉ còn chờ human identity review | 40 |

Mẫu số trailing là tổng USDT vào + ra của node trong các cửa sổ 30 ngày, cộng theo lượt thành viên. Cửa sổ chồng lấn và node đầu mút có thể cùng đếm một transfer; **không phải volume USDT duy nhất của toàn kỳ**. Diagnostics có thêm tỷ trọng theo volume node của ngày hiện tại, để không trộn hai mẫu số. Coverage là nhãn quan sát được theo T07 hiện tại, không phải recall hay xác nhận độc lập danh tính.

Đây là mức nhạy lớn: cohort chính vẫn chịu chi phối mạnh bởi hạ tầng mà nhãn chưa khả dụng theo chính sách as-of. Không dùng sự ổn định cao hơn của cohort 30 ngày để khẳng định đúng chủ thể đầu tư. Tương quan dòng tiền thấp cho thấy kết luận về WhaleFlow có thể đổi theo bộ lọc danh tính; phải giữ cả hai nhánh khi báo cáo, không chọn nhánh theo kết quả hồi quy.

V2 được nghiệm thu **về tính toán, timing của cohort và công bố giới hạn**, không phải chứng minh construct “cá voi cá nhân”. Bản hồi cứu cũng không xác nhận những địa chỉ Unknown còn lại là cá nhân. Không nâng các lookup AI thành nhãn T07 đã xác minh; corrections như Tether Treasury/CEX tiếp tục cần review riêng.

## Gate và bàn giao T14

Gate v2: `data/processed/t12/v2/t12_downstream_gate.json`.

- `ready_for_cohort_whaleflow=true`: chỉ cho cohort hoạt động lớn v2, với đúng protocol/path/hash trong gate.
- `ready_for_individual_investor_inference=false`: không xác nhận chủ ví cá nhân.
- `ready_for_rq3_pit_forecast=false`: nhãn CEX endpoint của T14 chưa được nghiệm thu lịch sử.
- `ready_for_t14_t15=false`: không dùng cờ tổng quát để xác nhận toàn bộ pipeline T14/T15.

Đường dẫn cohort chính: `data/processed/t12/v2/primary/cohort_members_daily.parquet`. Nhánh hồi cứu ở `retrospective/`. Gate v1 và mọi sản phẩm v1 giữ nguyên; T14 chưa được sửa/chạy lại trong công việc này. Không có code T14 cục bộ để tự cập nhật loader, nên nhóm T14 phải tích hợp hợp đồng v2 này rõ ràng. Không thay cohort bằng file cũ chỉ vì tên file giống nhau.

T14 chỉ được coi CEX NetFlow/WhaleFlow là dự báo PIT sau khi endpoint CEX có bằng chứng nhãn khả dụng tại cutoff, đo coverage USDT và kiểm tra timing riêng. Các dòng `net_to_current_cex_usdt` hiện tại chỉ là sensitivity hồi cứu. RQ2 có thể mô tả khác biệt nhóm địa chỉ đã biết/chưa biết, không suy rộng thành hành vi nhà đầu tư cá nhân từ centrality cao.

## Sản phẩm và tái lập

Trong `data/processed/t12/v2/`:

- `primary/` và `retrospective/`: cohort members, snapshots, chín tổ hợp độ nhạy và design validation, đều Parquet.
- `cohort_label_diagnostics.parquet`, `cohort_sensitivity_daily.parquet`, `cohort_flows_daily.parquet`, `source_review_status.parquet`.
- `t12_validation.parquet`, `t12_controls.parquet`.
- JSON freeze, summary, acceptance, reproducibility, gate và integrity control.

Chạy `python scripts/run_t12_v2.py` để tính hai lượt và nghiệm thu; `python scripts/validate_t12_v2.py` để kiểm định lại độc lập. Validator đối chiếu hash toàn bộ code/config/input/output trước khi mở gate. Không tạo CSV hoặc giả hồ sơ human review. Các thư mục run/control tạm được xóa sau kiểm tra; giữ validator dữ liệu thật để nhóm tái lập. Chưa push GitHub/Hugging Face trong công việc này.
