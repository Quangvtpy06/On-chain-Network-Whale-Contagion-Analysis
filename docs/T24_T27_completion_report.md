# Giai đoạn 5 — T24 đến T27 (On-chain Explorer)

**Trạng thái:** hoàn thành ứng dụng Streamlit tại `app.py`, có entry point Cloud
ở `demo/app.py`. Ứng dụng đọc trực tiếp các bảng Parquet nghiệm thu, không tạo
hoặc sửa dữ liệu nghiên cứu.

## Bàn giao theo task

| Task | Nội dung | Bàn giao |
|---|---|---|
| T24 | Khung ứng dụng Explorer | Bộ chọn USDT, ngày/tuần, cửa sổ quan sát; các tab mạng lưới, dòng tiền, hình báo cáo và câu trả lời RQ1–RQ5 |
| T25 | Hiển thị network graph | Hiển thị toàn bộ nút/cạnh theo cửa sổ, tô màu theo cộng đồng; bảng đầy đủ xếp theo weighted degree với bí danh ẩn danh |
| T26 | Panel flow và volatility | CEX inflow/outflow/netflow, cohort whale-flow PIT, T12 whale score và realized volatility |
| T27 | Hình cho báo cáo | Community map đầy đủ, whale cohort → CEX so với volatility, event-time response T16 và nhận xét diễn giải |

Tất cả biểu đồ Plotly hỗ trợ zoom bằng con lăn và kéo để pan. Chuỗi thời gian có
các preset 30/90/180 ngày hoặc toàn bộ dữ liệu đến ngày đã chọn; thanh chọn phạm
vi và giới hạn pan được cập nhật theo dữ liệu đang hiển thị. Đồ thị mạng và bản đồ
cộng đồng có bộ chọn Top-N/tất cả để cân bằng khả năng đọc với độ bao phủ; bảng
vẫn giữ đủ dữ liệu. Mỗi bảng có ô tìm kiếm, số dòng hiển thị và CSV xuất theo kết
quả lọc. Giao diện dùng theme sáng cố định theo `DESIGN.md`. Đồ thị và file tải về
chỉ hiển thị bí danh, không render địa chỉ ví.

## Nguồn và cách chạy

Nguồn dữ liệu: T08 (edges/metrics), T09 (centrality), T11 (communities), T12
(whale score), T14 (flows/volatility), T16 (event study). Kết luận RQ1/RQ2 lấy
từ `docs/T13_completion_report.md`; RQ3 tổng hợp T15/T16/T18; RQ4 từ
`docs/RQ4_stress_lead_completion_report.md`; RQ5 từ `docs/T20_T22_completion_report.md`.

```bash
pip install -r demo/requirements.txt
streamlit run app.py --server.address 127.0.0.1
```

Ứng dụng ưu tiên output Parquet local; nếu thiếu file, ứng dụng tải on-demand từ
dataset Hugging Face public tại revision được ghim trong `app.py`. Xem README để
cấu hình demo online trên Streamlit Community Cloud.

## Phạm vi diễn giải

Dataset hiện có chỉ chứa USDT nên bộ chọn tài sản chỉ cung cấp USDT. Nhãn ví và
cohort có thể mang tính hồi cứu; whale score không xác minh chủ sở hữu. Các biểu
đồ flow/volatility và event-time mô tả dữ liệu trong mẫu, không chứng minh quan
hệ nhân quả, không phải dự báo thị trường và không phải khuyến nghị đầu tư.
