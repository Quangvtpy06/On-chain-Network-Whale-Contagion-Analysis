# Kiểm tra bản T13 đã sửa trên GitHub và Hugging Face

Ngày kiểm tra: 22/10/2026.

T13 đạt kiểm tra tính toán và tái lập đối với sản phẩm mô tả RQ1/RQ2. Báo cáo phát hành đã được cập nhật và manifest kiểm định cuối đã được bổ sung. Biểu đồ HF và liên kết ảnh được giữ nguyên theo yêu cầu chủ dự án; khác biệt bố cục được ghi nhận trong manifest. Theo Blueprint08, T15/T16 trực tiếp trả lời RQ3; việc T13 không đánh giá gate dự báo RQ3 không phải lỗi nghiệm thu T13.

## Phiên bản được kiểm tra

- GitHub main: `30d29a1efa9f757d0e36e581252c1cb04dfe928a`.
- Commit sửa nguồn T13: `b67c3a62c8eb634ffaa8d5bc44d8823065164420`, đã có trong main. File nguồn local khớp đối tượng Git trên origin/main.
- HF dataset: `team-crypto/Market-data-crypto-project`, revision `ad3d2603bb3ff1e15033d1f98cd2520151d64dbb`.
- Thư mục HF: `data/processed/t13`, gồm 20 Parquet và 4 PNG. Tất cả tải và đọc được; không gặp file pointer thay cho nội dung Parquet.
- Đầu vào: 655 file OHLCV phút và 4 bảng graph/T09; SHA-256 của cả 659 file khớp phiên bản HF đã ghim.

## Kết quả thực chạy

Chạy CLI T13 hai lần trong thư mục tạm, giữ chế độ kiểm tra nghiêm ngặt. Cả hai lần kết thúc thành công.

| Kiểm tra | Kết quả |
| --- | --- |
| 20 bảng tính lại so với HF | 20/20 khớp giá trị; rtol=1e-9, atol=1e-11; bỏ qua khác biệt dtype khi so bảng |
| Hai lần chạy Parquet | 20/20 hash byte giống nhau |
| Hai lần chạy biểu đồ | 4/4 hash byte giống nhau |
| Lịch phút UTC độc lập | 655 ngày, 943.200 nến; không thiếu/thừa mốc phút |
| RV tính lại từ log return | 943.199 returns; sai số tuyệt đối tối đa 2,26e-16 |
| Phân loại theo RV P90 | 589 ngày normal, 66 ngày stress; P90=0,048694850425840486 |
| Tuần đủ ngày | 92 tuần; loại tuần không đủ 7 ngày |
| Tỷ trọng dòng tiền của nhóm ví trung tâm | 5.895 dòng; sai số tối đa 5,56e-16 |
| OLS/HAC tính độc lập | 20 mô hình khớp hệ số, sai số chuẩn và p-value |
| Hiệu chỉnh BH/FDR độc lập | Khớp; RQ1 có 7/11, RQ2 có 7/9 kiểm định đạt FDR 5% |

Phép kiểm tra công thức độc lập không gọi lại các hàm tính của T13: dùng hiệu log close và tổng bình phương theo ngày; NumPy sắp xếp theo điểm và địa chỉ để kiểm tra top-K; tính OLS và hiệp phương sai Bartlett/Newey-West lag 7, sau đó tính BH bằng sắp xếp p-value. Việc chạy lặp lại được báo cáo riêng với việc kiểm tra công thức.

Lỗi timestamp cũ đã được sửa tại `T13_Network_Statistics.py:299`: cả lịch kỳ vọng và timestamp dữ liệu đều đổi về `ns` trước `.equals()`. Đây là thống nhất độ chính xác lưu datetime, không phải đổi tần suất đồ thị ngày thành phút.

## Cập nhật bàn giao sau review

- Đã sửa `T13_completion_report.md`: bỏ thông tin CSV và commit/merge cũ, ghi đúng snapshot nguồn/dữ liệu và kết quả kiểm định cuối.
- Bổ sung `docs/T13_release_manifest.json` và cùng nội dung tại `data/processed/t13/t13_release_manifest.json` trên HF. Manifest ghi hash 659 đầu vào, 20 bảng HF, hai lần chạy, môi trường và kết quả kiểm tra công thức độc lập.
- Giữ nguyên hình HF và liên kết ảnh theo yêu cầu. Khác biệt tên/bố cục giữa hình công bố và hình nguồn hiện tại được ghi nhận, không khẳng định nguyên nhân chưa chạy lại và không coi là lỗi tính toán.
- Không sửa code hoặc output tính toán của T13/T14 trong bản cập nhật tài liệu này.

## Phạm vi kết luận nghiên cứu

- Có thể dùng T13 làm bằng chứng mô tả cấu trúc mạng, phân phối centrality và khác biệt normal/stress cho RQ1/RQ2, trong phạm vi mạng transfer lớn của T08.
- Stress dùng ngưỡng và chuẩn hóa trên toàn kỳ phù hợp so sánh hồi cứu. Không chuyển trực tiếp các nhãn đó thành predictor point-in-time cho T14/T15; cần quy tắc chỉ dùng dữ liệu có sẵn tại thời điểm dự báo.
- Ví trung tâm trong T13 được chọn bằng T09. T13 không xác minh cá nhân, không dùng thay nghiệm thu cohort T12 và không chứng minh quan hệ nhân quả.
- Mạng chỉ chứa transfer sau netting đạt ngưỡng 500.000 USDT; không đại diện toàn bộ hoạt động USDT. Incident volume đếm hai đầu cạnh trong mẫu số, không phải lượng tài sản ròng hay dòng tiền kinh tế độc lập.

Bằng chứng bàn giao máy đọc được: [T13_release_manifest.json](T13_release_manifest.json). Bằng chứng nội bộ bổ sung: `.release/t13_review_report.json` và `.release/t13_formula_review.json`. Dữ liệu đầu vào tải phục vụ review và hai bộ output thử được xóa sau kiểm tra theo quy ước dự án. Không sửa nguồn hoặc output chính T13/T14 trong lần review này.