# T11 — Community detection và network concentration

## Mục tiêu và đầu vào

T11 bàn giao community theo node–cửa sổ, modularity và chuỗi chỉ số tập trung
phục vụ RQ4. Chỉ phụ thuộc T08 đã netting, xác minh bằng SHA-256. Không cần
T07, T09 hoặc WhaleScore. Đường dẫn/lịch đọc config/config.yaml; tham số riêng
config/t11.yaml, không sửa cấu hình đã ký hash của các bước khác.

655 ngày UTC từ 2025-01-01 đến 2026-10-17; 94 tuần ISO bắt đầu thứ Hai.
Giữ snapshot rỗng trong lịch. Hai tuần thiếu ngày có is_partial_week=true và
eligible_for_regression=false, ở cả bảng snapshot và bảng node.

## Đồ thị và cộng đồng

Mỗi snapshot là DiGraph có hướng, weight=total_value từ T08, gồm node có hoạt
động trong cửa sổ. Louvain weighted directed dùng resolution=1, threshold=1e-7.
Không đổi sang đồ thị vô hướng hoặc lấy gross volume làm trọng số.

Directed modularity tính trên phân hoạch C:
Q = sum_c [W_internal,c / m − gamma × K_out,c × K_in,c / m²].
m là tổng volume cạnh; K_out,c/K_in,c là tổng strength ra/vào của node thuộc
community. Với snapshot rỗng Q=0, không tạo node giả.

Seed của mỗi snapshot là 32-bit đầu SHA-256(seed|window_type|time_window),
seed gốc 20261021. Chạy qua T11_Community_Concentration.py để ép
PYTHONHASHSEED=0. Node/cạnh và phép tổng volume community được sắp xếp ổn định.
Louvain là phương pháp heuristic; tái lập không chứng minh tìm được optimum
toàn cục hoặc phân hoạch bất biến khi đổi resolution/seed.

Community được đánh số giảm dần theo số node, rồi volume giảm dần và địa chỉ
nhỏ nhất để phá hòa. ID 0 là community lớn nhất theo node, không nhất thiết
lớn nhất theo volume. ID chỉ có ý nghĩa trong snapshot; không đại diện danh
tính ổn định qua ngày/tuần. Không đưa ID thô vào T19 như nhãn định danh bền vững.
Thống kê size bao gồm mọi community, kể cả singleton; không còn tham số
min_community_size_for_stats không được sử dụng.

## Chỉ số tập trung

Volume node = strength vào + ra. Degree = in-degree + out-degree trên DiGraph.
Volume community = tổng volume node thuộc community. Tổng volume node và tổng
volume community đều bằng 2m, vì mỗi transfer được tính ở hai đầu. Đây là
throughput tham gia, không phải số dư, tài sản hoặc net flow.

- HHI volume/degree = sum_i (x_i/sum(x))². Đây là HHI tỷ phần, có mức đồng đều
  1/N, không phải HHI được rescale để đồng đều bằng zero.
- HHI community volume/nodes dùng cùng công thức theo phân phối community.
- Gini volume/degree dùng phân phối mọi node hoạt động, giá trị zero nếu dân
  số không đủ biến thiên hoặc tổng bằng zero.
- CR1/5/10/20 là tỷ trọng volume của k node lớn nhất; giới hạn k theo N.
  CR top1%/top5% dùng ceil(0.01N)/ceil(0.05N), tối thiểu một node khi N>0.
- Entropy volume/community = −sum(p log p)/log(số nhóm); zero nếu <=1 nhóm
  hoặc không có volume.
- Internal volume ratio = tổng weight cạnh có hai đầu cùng community / m.
- CCI = max(Q,0) × HHI community volume. Chỉ số tổng hợp do dự án định nghĩa,
  không tự chứng minh tập trung kinh tế, rủi ro hệ thống hay stress.
- Community size mean/std(ddof=0)/median/max và số singleton mô tả phân phối
  size. Giant metrics dùng community ID 0.

community_volume_usdt được lặp trên mỗi dòng node của community. Khi tổng hợp
theo community phải lấy một dòng mỗi community hoặc cộng node_volume_usdt;
không cộng trực tiếp cột community_volume_usdt qua mọi node.

## Đầu ra chuẩn

Trong data/processed/t11/, tám Parquet được sinh trong cả hai lượt:

| File | Nội dung |
|---|---|
| community_nodes_daily/weekly.parquet | window_type, time_window, address, community_id, community_size, community_volume_usdt, is_giant_community, node_volume_usdt, node_degree và metadata lịch |
| snapshot_metrics_daily/weekly.parquet | Đủ lịch; modularity, số community, thống kê size, HHI/Gini/CR/entropy/CCI, internal/giant metrics và seed |
| t11_validation.parquet | Kiểm tra nội bộ từng cửa sổ |
| top_communities_summary.parquet | Top 5 community theo volume cho từng cửa sổ ngày/tuần, rank và tỷ trọng |
| rq4_daily_regimes.parquet | Nhóm hồi cứu, ngưỡng, cửa sổ tương lai, cờ censor |
| rq4_comparison.parquet | N/mean/difference, Welch Pre vs Baseline và Holm |

Metadata: t11_summary.json, t11_reproducibility.json và t11_review.json.
Chỉ bảng dữ liệu dùng Parquet; không tạo CSV.

## RQ4 mô tả và giới hạn suy luận

High-volume là total_volume_usdt >= phân vị 90% toàn bộ 655 ngày. Pre là ngày
không high-volume nhưng có high-volume trong 1–3 ngày sau. Baseline là ngày
còn lại với đủ ba ngày tương lai. Ba ngày cuối được ghi right_censored cho
cả ba nhóm và không tham gia phép so sánh; chúng vẫn có metric T11 đầy đủ.

Ngưỡng toàn kỳ và nhãn pre là phân loại hồi cứu, không phải thông tin đã biết
tại ngày dự báo. Không đưa regime/pre flag vào predictor ngày t. Muốn dự báo
phải dùng feature T11 trễ và thiết kế ngưỡng/sự kiện dựa trên thông tin quá khứ.

Welch so pre_high_volume với baseline theo tên nhóm, không theo vị trí ngầm.
Holm điều chỉnh năm phép so sánh: Gini node volume, HHI community volume, CCI,
modularity và CR top5%. Cả p Welch và Holm chỉ là thăm dò; Holm không sửa phụ
thuộc thời gian, cụm sự kiện hoặc thiết kế stress nội sinh theo volume mạng.
Không dùng chúng để khẳng định nhân quả hay xác nhận stress thị trường.

Gini node khác concentration cấp community. Không kết luận nhà đầu tư cá nhân,
ý định chuyển tiền, tái cơ cấu danh mục, nạp/rút CEX hoặc thanh lý từ community
hay centrality. Giả thuyết thị trường cần stress độc lập và thiết kế thống kê
phù hợp; kết quả không có ý nghĩa thống kê vẫn là một kết quả hợp lệ.

## Chạy và nghiệm thu

```powershell
python T11_Community_Concentration.py
python scripts/validate_t11_current.py
python -m src.visualize_t11
```

Lệnh chính tính hai lượt trong **hai tiến trình**, cùng PYTHONHASHSEED=0,
so SHA-256 đúng danh sách tám Parquet, không glob mọi file trong thư mục.
Lượt hai ở .cache/t11_repro_* và tự xóa khi kết thúc.

Summary giữ ready_for_downstream=false trong khi tính và trước kiểm định.
--skip-reproducibility luôn giữ false; không in thông báo đã tái lập.
Validator không yêu cầu ready đã true. Nó kiểm tra hash thực tế với hai lượt,
code/config/source, rồi kiểm tra mọi cửa sổ từ cạnh T08 bằng công thức riêng
(không nhập hàm chỉ số production). Kiểm tra cả bảng top, metadata node/lịch,
bảng validation, regime, thống kê RQ4 và Holm. Nếu lỗi phải hạ ready về false
và lưu lý do; chỉ thành công mới ghi review all_pass và bật ready.

Bằng chứng tái lập bảo đảm tính nhất quán trong phiên bản môi trường ghi nhận,
không hứa kết quả bit-for-bit giữa mọi phiên bản NetworkX hoặc nền tảng.
Giữ validator dữ liệu thật và kết quả JSON/Parquet. Xóa dữ liệu/code test giả,
bản đối chiếu và cache sau kiểm tra theo quy ước dự án.

## Hình vẽ và tích hợp

Bốn PNG 300 dpi ở data/figures/t11/: t11_modularity_timeseries.png,
t11_concentration_timeseries.png, t11_rq4_stress_comparison.png và
t11_community_map_2026-10-17.png. Đây là Matplotlib tĩnh, không phải Plotly
explorer. Biểu đồ box dùng thứ tự baseline/pre/high-volume, N động và đọc cùng
bảng comparison đã kiểm định. Phân hoạch của community map lấy từ toàn bộ
snapshot dù chỉ vẽ top 120 cạnh để dễ đọc.

T19 dùng thuộc tính cấu trúc có ý nghĩa trong cửa sổ; tracking community cần
alignment riêng. T27 có thể dùng bảng node và source visualization để phát
triển explorer. T13/T14 có thể dùng chuỗi feature trễ, không dùng nhãn regime
hồi cứu như predictor. Mạng chỉ chứa transfer sau netting >=500.000 USDT;
các chỉ số mô tả mạng con này, không phải toàn Ethereum hoặc toàn bộ tài sản.

Xem [báo cáo được sinh từ dữ liệu](T11_completion_report.md) và
[kết quả xử lý review](T11_review_report.md).
