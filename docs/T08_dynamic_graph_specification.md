# T08 — Đặc tả đồ thị giao dịch động

## Đầu vào và cấu hình

Mọi đường dẫn artifact tính tương đối từ thư mục `crypto`, đọc từ `config/config.yaml`.
`src/graph_config.py` tìm bản transfer gốc trong dự án hoặc cache Hugging Face có sẵn.
Không sửa file gốc. Pipeline ghi SHA-256 của file gốc để đối soát sau khi chạy.

T07 được hoàn thiện bằng `python T07_Complete_Wallet_Labels.py`. Đầu ra chuẩn là
`data/processed/t07/t07_complete_wallet_labels.parquet`.
Mỗi địa chỉ xuất hiện đúng một lần, có nhãn thực thể, bằng chứng gốc, `is_contract`,
`contract_status_source`, `contract_status_checked_at`, `contract_status_as_of`.
`is_contract` lấy từ bảng `bigquery-public-data.crypto_ethereum.contracts` trước
mốc kết thúc nghiên cứu, độc lập với `entity_type`. Chưa xác minh là null, không
mặc định False. Có bản ghi tạo contract không bảo đảm bytecode còn tồn tại ở mọi
thời điểm trong kỳ, và không xác minh danh tính kinh tế của tổ chức.
Nhãn Unknown và Contract không có danh tính tổ chức vẫn được ghi rõ là chưa quy thuộc.

## Phép gộp dòng tiền

Với mỗi `transaction_hash` và cặp ví vô hướng `{A,B}`, đặt A < B theo thứ tự địa chỉ:

`net(A,B,tx) = sum(amount A→B trong tx) - sum(amount B→A trong tx)`.

Tính bằng micro-USDT (6 chữ số thập phân). Nếu net > 0 giữ A→B, nếu net < 0 giữ B→A
với amount = abs(net). Bỏ net = 0, rồi áp lại ngưỡng amount ≥ 500.000 USDT.
Không gộp qua các transaction khác nhau. Bỏ from = to trước khi netting và thống kê
số sự kiện/volume bị bỏ theo ngày. Địa chỉ zero được giữ và gắn cờ `is_zero_address`.
Khóa `(transaction_hash, log_index)` phải duy nhất trên dữ liệu thô; dữ liệu netted
không còn log_index đại diện cho một sự kiện, mà có khóa transaction/cặp ví.

File gộp: `data/interim/usdt_transfers_netted.parquet`.

## Cạnh và thuộc tính nút

G_t là DiGraph có hướng trên một cửa sổ UTC. Mỗi cặp có hướng xuất hiện một lần:

| Thuộc tính cạnh | Định nghĩa |
|---|---|
| total_value | Tổng amount netted của cặp trong cửa sổ |
| transaction_count | Số transaction_hash khác nhau của cặp trong cửa sổ |
| mean_value | total_value / transaction_count |
| min_value, max_value | Amount netted nhỏ nhất, lớn nhất của một transaction/cặp |
| gross_value | Tổng amount thô của **cả hai chiều** thuộc các cặp transaction còn được giữ |
| event_count | Số sự kiện thô của cả hai chiều thuộc các cặp transaction còn được giữ |
| first_timestamp, last_timestamp | Timestamp UTC đầu/cuối |
| is_zero_address | Ít nhất một đầu mút là địa chỉ zero |
| days_in_window, is_partial_week | Metadata cửa sổ |
| eligible_for_regression | False với tuần thiếu ngày |

Gross của các cặp bị triệt tiêu hoặc rơi dưới ngưỡng không có cạnh để gán; do đó tổng
gross_value trên cạnh không bằng tổng volume thô. Dùng raw_volume trong summary và
bảng monthly retention để so sánh toàn bộ trước/sau netting.

Nút có entity_name, entity_type, class từ T07; is_contract và nguồn xác minh;
is_zero_address; in/out degree và in/out volume. Loader giữ tất cả thuộc tính cạnh,
đồng thời cung cấp weight = total_value.

## Cửa sổ thời gian và snapshot rỗng

Ngày UTC theo khoảng nửa mở `[00:00:00, 00:00:00 ngày sau)`.
Tuần ISO bắt đầu thứ Hai 00:00 UTC; dùng `%G-W%V` (ISO year/week).
Trong 2025-01-01–2026-10-17 có 655 ngày và 94 tuần:

- 2025-W01: 5 ngày; is_partial_week=True.
- 2026-W42: 6 ngày; is_partial_week=True.
- 92 tuần còn lại đủ 7 ngày, eligible_for_regression=True.

Bảng metrics và loader liệt kê đủ 655 ngày/94 tuần kể cả ngày rỗng. Edge parquet là
bảng cạnh thưa: không thêm cạnh giả cho ngày không giao dịch. Snapshot rỗng có 0 nút,
0 cạnh, 0 volume và được loader trả về như DiGraph rỗng trong phạm vi cấu hình.
Các task hồi quy phải lọc `eligible_for_regression == True` khi dùng chuỗi tuần.

## Chỉ số và kiểm định

Density, reciprocity, SCC, WCC tính trên đồ thị có hướng đơn sau khi gộp cạnh.
Node volume = incoming + outgoing; tổng volume nút = 2 × volume cạnh.
`top10_volume_share`, Gini và HHI dùng phân phối này. Không làm tròn giá trị trước khi kiểm định.

`t08_validation.parquet` có một dòng mỗi ngày: date, n_events_in (số sự kiện nguồn
thuộc cặp netted còn giữ), n_netted_rows, n_tx_in (unique tx ngày), n_edges, n_nodes,
value_in, value_edges, diff_value (edges − input), self_loops (sự kiện raw bị bỏ),
zero_addr (dòng netted có zero), edge_transaction_count, status.
Đối soát volume dùng atol=0,0001 USDT, rtol=1e-12 để cho phép sai số cộng float.
Theo yêu cầu người dùng, không đối chiếu tổng transaction_count trên cạnh với số tx
unique toàn ngày: một tx có thể đóng góp nhiều cạnh.

`t08_acceptance_checks.parquet` lưu B.1–B.9. B.6 chọn ngẫu nhiên 5 transaction với seed=8,
đối chiếu tổng hai chiều thô với chiều netted và sự tồn tại trong cạnh ngày.
`t08_topology_comparison.parquet` lưu trước/sau từng cửa sổ; không giả định reciprocity
nhất thiết phải giảm vì các transaction hai chiều độc lập vẫn được giữ.

B.7 gồm monthly retention, top 10 ngày và tác nhân đo được (top transaction, top node),
top 20 nút kèm trạng thái contract/nhãn, tỷ trọng top10 nút toàn kỳ.
Giải thích tác nhân đo được không phải xác minh nguyên nhân kinh tế bên ngoài.
`residual_top10_review_threshold` trong config là ngưỡng sàng lọc của nghiên cứu,
không phải kết luận tự động về dòng tiền giả.

Audit đa bước: `t08_multistep_cycle_audit.parquet` trừ bottleneck của chu trình có hướng
trong từng transaction, theo thứ tự địa chỉ xác định. Kiểm tra tổng phần bị trừ đi/đến
của mỗi nút/transaction bằng nhau. Cách phân rã chu trình có thể không duy nhất; đây
là phép tính độ nhạy, không là bằng chứng rằng mọi vòng đều phi kinh tế. Không tự thay
đồ thị chính khi chưa có quyết định của nhóm. Nếu tập trung vượt ngưỡng, B.7 là
REVIEW_REQUIRED và ready_for_t09_t12=False.

## Tái lập và review

Từ thư mục crypto chạy bằng Python có đủ requirements (môi trường hiện tại: `.venv`
ở thư mục cha):

```powershell
& '../.venv/Scripts/python.exe' T07_Complete_Wallet_Labels.py
& '../.venv/Scripts/python.exe' T08_Dynamic_Transaction_Graph.py
```

Mặc định T08 tính hai lần từ raw, lưu lần hai vào `.cache/t08_repro_*`, so SHA-256 của 11
artifact rồi dọn thư mục tạm, xác nhận input netted không đổi. Summary không chứa timestamp chạy dễ
làm thay đổi hash. `src/t08_review.py` chạy ở tiến trình riêng, không import
production; đối chiếu netting bằng bảng tổng chiều thuận ghép bảng đảo chiều,
đối chiếu mọi cạnh, dùng SciPy sparse kiểm tra topology độc lập với NetworkX.
Đây là review tính toán độc lập, không thay chữ ký reviewer trong nhóm.

```python
from src.build_dynamic_graph import DynamicGraphLoader
loader = DynamicGraphLoader('data/processed/graphs/dynamic_edges_daily.parquet')
graph = loader.build_snapshot_graph('2025-01-01')
```

`--single-run` chỉ phục vụ phát triển: B.9 giữ PENDING, không đạt nghiệm thu.
`--show-only --date 2025-01-01 --top-k 100` xuất HTML tương tác từ kết quả có sẵn.
HTML nhúng Plotly để xem offline; `scrollZoom=True`, kéo để pan, nhấp đúp để reset.
Màu mặc định biểu diễn log(1 + in_degree + out_degree), thanh màu ghi bậc gốc;
kích thước nút cũng theo độ kết nối. Có lựa chọn màu theo entity_type T07,
ký hiệu hình thoi cho contract và hình tròn cho địa chỉ khác. Mũi tên giữa cạnh
biểu diễn chiều u→v và có tooltip volume ròng, số transaction khác nhau, mean,
gross và số event nguồn. Các giá trị node trong chế độ top-k được tính trên đồ thị
đang hiển thị; metadata nhãn lấy từ T07. Chọn top-k chỉ lọc hiển thị, không đổi dữ liệu.
Ô tìm địa chỉ và nút reset hỗ trợ khám phá. `--no-open` xuất HTML mà không mở browser.

## Giới hạn đã biết

Một sự kiện ERC-20 không nhất thiết là một dòng tiền kinh tế độc lập. Net theo cặp chỉ
loại vòng trực tiếp nội transaction; vòng qua nhiều transaction, trung gian và các
hoạt động hợp đồng khác vẫn có thể còn. Dữ liệu raw đầu vào vốn đã lọc từng event
≥500.000 USDT, nên không khôi phục được counterflow nhỏ hơn ngưỡng đã bị bỏ ở T05.
Kết quả netting vì thế chỉ là net trên tập sự kiện được quan sát.

Đồ thị chỉ chứa transfer ròng ≥500.000 USDT. Bậc nút bị cắt xén; centrality mô tả mạng
con cá voi, không phải toàn mạng Ethereum/USDT. Không suy quan hệ sở hữu hay dòng vốn
kinh tế độc lập chỉ từ cạnh, volume hoặc vòng chuyển token.
