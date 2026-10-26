# RQ4 — Kiểm tra trước stress thị trường

Đã nối nhãn stress thị trường T13 với HHI cộng đồng và CCI của T11 trong một phép kiểm tra riêng, không thay dữ liệu T11/T13. Dùng đúng bảng T13 đã nghiệm thu trên HF: SHA-256 `837f17049e9358a421caf0845b24817c599e9197a8909aef4bc09cb2698c22bb`, 655 ngày UTC. Nguồn T11 daily khớp hai hash tái lập.

**66 ngày stress tạo thành 23 đợt theo quy tắc cách nhau tối đa 3 ngày; cả 23 onset đủ lịch.** Có 434 mốc đối chứng không có stress trong ±3 ngày. Giá trị của mỗi mốc lấy trung bình HHI/CCI từ ba ngày trước. Không đưa ngày stress vào giá trị “trước”.

| Chỉ số | Trước stress | Đối chứng | Chênh lệch | 95% CI khối lịch | p Holm tăng |
|---|---:|---:|---:|---|---:|
| HHI community volume | 0,139220 | 0,133338 | +0,005882 (+4,41%) | [−0,003419; 0,016733] | 0,2603 |
| Community concentration index | 0,097299 | 0,095386 | +0,001913 (+2,01%) | [−0,003651; 0,008307] | 0,2603 |

**Kết luận primary:** hai giá trị trung bình cao hơn trước onset stress, nhưng chưa đủ bằng chứng thống kê rằng tập trung cộng đồng tăng trước stress ở mức 5% sau Holm. Đây là câu trả lời âm tính có giới hạn cho RQ4 trong mạng con USDT được quan sát; không chứng minh chỉ số không bao giờ tăng.

Độ nhạy ghép 23 onset với 23 ngày yên bình cùng thứ trong tuần, cách tối đa 60 ngày, cho chênh lệch HHI +0,006317 và CCI +0,003733. Cả hai p một phía thô khoảng 0,03, nhưng **p Holm = 0,0580**, vẫn chưa đạt 5%. Kết quả thay đổi theo cách chọn đối chứng, nên không nâng kết luận độ nhạy thành bằng chứng xác nhận.

Bootstrap chính lấy khối 14 ngày lịch (5.000 lượt); độ nhạy lấy khối 3 đợt. Hai tiến trình CLI với `PYTHONHASHSEED` khác nhau cho 9/9 output giống SHA-256. Validator riêng kiểm tra lại số học/lịch, báo `all_pass=true`; 7 ca pytest giả đạt rồi mã test tạm được xóa. Bằng chứng hash, số dòng và kết quả kiểm định giữ tại `docs/RQ4_stress_lead_acceptance_evidence.json`.

Giới hạn cần ghi trong báo cáo học thuật: stress P90 lấy từ toàn kỳ nên đây là đối chiếu hồi cứu; 23 đợt là mẫu sự kiện nhỏ. Bootstrap khối giảm giả định độc lập theo ngày nhưng kết quả còn nhạy với độ dài khối và đối chứng. HHI/CCI đo mạng transfer USDT từ 500.000 USDT, không đo toàn hệ sinh thái; liên hệ đi trước theo lịch không xác định nguyên nhân hoặc dự báo ngoài mẫu. RQ4 về **mối liên hệ trước stress** đã được kiểm tra và có thể trả lời trong phạm vi này; nếu muốn tuyên bố tín hiệu dự báo, phải có giao thức điểm thời gian và giai đoạn kiểm tra mới.

Code: `RQ4_Stress_Lead.py`, `src/rq4_stress_lead.py`, `scripts/validate_rq4_stress_lead.py`; config: `config/rq4_stress_lead.yaml`; output: `data/processed/rq4_stress_lead/`. Chưa upload GitHub/HF.
