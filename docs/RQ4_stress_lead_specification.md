# RQ4 — Protocol kiểm tra tập trung cộng đồng trước stress

Protocol `rq4_t13_stress_t11_lead_v1`, cấu hình tại `config/rq4_stress_lead.yaml`. Chốt quy tắc trước lượt tính chính. Đây là phép kiểm tra hồi cứu mối liên hệ theo thời gian; không tuyên bố nguyên nhân–kết quả hay khả năng dự báo ngoài mẫu.

## Nguồn và phạm vi

- Stress là nhãn `Stress` của bảng T13 `rv_daily_regimes.parquet`, RV ETH/USDT phút vượt **P90 toàn bộ 655 ngày**. Bảng được tải từ revision HF `ad3d2603bb3ff1e15033d1f98cd2520151d64dbb`; hash khớp `docs/T13_release_manifest.json` trên GitHub. Manifest này không có ở đường dẫn `data/processed/t13/` trên HF. Ngưỡng toàn kỳ chỉ dùng để phân loại hồi cứu.
- Chỉ số T11 lấy từ `snapshot_metrics_daily.parquet` đã qua review/tái lập. Hai chỉ số cùng là thước đo **cộng đồng**: `hhi_community_volume` và `community_concentration_index` (CCI). Chúng không thay bằng Gini node hay CR top node.
- Lịch UTC ngày 01/01/2025–17/10/2026 phải khớp từng ngày, không thiếu/trùng. Nguồn T11 chỉ mô tả mạng con USDT transfer sau netting từ 500.000 USDT.

## Sự kiện và đối chứng

Stress days cách nhau tối đa 3 ngày lịch được gộp thành một đợt. Ngày stress đầu đợt là onset D. Mỗi đợt chỉ dùng một onset để các ngày stress gần nhau không bị tính thành quan sát độc lập. Chỉ giữ onset có đủ ngày D−3..D−1 và đủ 3 ngày sau để xác định đối chứng cùng lịch. Không dùng chỉ số D hoặc sau D làm biến “trước stress”.

Mỗi chỉ số trước stress là trung bình ba ngày D−3,D−2,D−1. Mốc đối chứng T là ngày đủ lịch trước/sau và không có stress trong T−3..T+3. Chênh lệch chính bằng trung bình của tất cả onset trừ trung bình các mốc đối chứng. Các mốc đối chứng có thể có cửa sổ trước chồng nhau; phương pháp suy luận phải giữ phụ thuộc thời gian.

## Suy luận

- Primary: bootstrap vòng khối **14 ngày lịch**, resample cặp trạng thái mốc/giá trị pre3 trên toàn chuỗi 655 ngày, 5.000 lượt, seed 20261026. Khối lịch giữ các mốc gần nhau và cửa sổ trước chồng lấn; không xem từng ngày là quan sát IID. Báo chênh lệch, CI percentile 95%, p một phía cho giả thuyết tăng (phân phối bootstrap được center theo chênh lệch quan sát). Holm hai chỉ số primary, mức 5%.
- Độ nhạy: mỗi onset ghép một mốc yên bình cùng thứ trong tuần, cách tối đa 60 ngày, gần nhất và không tái sử dụng đối chứng. Chênh lệch cặp được bootstrap vòng theo khối 3 đợt, 5.000 lượt, cùng kiểu CI/p. Holm riêng cho hai chỉ số độ nhạy; đây không phải điều kiện để thay kết luận primary.
- Khoảng tin cậy và p-value có thể không đồng nhất về ngưỡng một phía/hai phía. CI là hai phía 95%; p kiểm định tăng là một phía. Không diễn giải một CI độ nhạy như xác nhận độc lập nếu p Holm không đạt.
- Khi số đợt đủ điều kiện dưới 10, hoặc dưới 1.000 lượt bootstrap có đủ hai nhóm, pipeline từ chối kết luận. Không chọn ngưỡng P90, độ dài khối, cửa sổ trước hoặc bộ lọc đối chứng dựa trên p-value.

## Kiểm định và đầu ra

Kiểm tra SHA-256 T13/T11, lịch UTC, 66 ngày stress, tất cả onset/đối chứng, không lẫn ngày stress trong ba ngày trước onset, cửa sổ yên bình ±3 ngày, lookup trực tiếp các chỉ số, Holm và hash hai lần tính. Validator riêng đọc output và tự tìm onset, mốc yên bình, tính lại trung bình ba ngày và chênh lệch cho cả hai chỉ số. Hai tiến trình CLI độc lập phải sinh file giống SHA-256. Test giả kiểm tra cluster, biên lịch, leakage tương lai, chọn đối chứng và seed bootstrap; xóa mã/dữ liệu test giả sau khi đạt theo quy ước dự án.

Output dưới `data/processed/rq4_stress_lead/`: 5 Parquet (lịch mốc, đợt stress, cặp đối chứng, kết quả, validation), 1 PNG, báo cáo Markdown, summary JSON và independent review JSON. Không thêm CSV. Thay code/config/input đòi chạy lại nghiệm thu; chưa bao gồm kiểm tra stress theo định nghĩa khác hoặc thử dự báo tiền kỳ ngoài mẫu.
