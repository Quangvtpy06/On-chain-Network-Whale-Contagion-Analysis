# Đặc Tả Kỹ Thuật Đồ Thị Giao Dịch Động (Dynamic Transaction Graph Specification - T08)

**Dự án:** On-chain Network Whale Contagion Analysis  
**Mã nhiệm vụ:** T08 (Giai đoạn 2: Đồ thị và chỉ số mạng)  
**Người thực hiện:** TV1 - Yến Vy  
**Reviewer:** TV4 / Hương  
**Trạng thái:** ✅ **Hoàn thành (Done)**  

---

## 1. Cơ sở Lý thuyết & Định nghĩa Toán học

Mạng lưới giao dịch cá voi on-chain được mô hình hóa dưới dạng một **chuỗi đồ thị có hướng theo thời gian (Dynamic Directed Temporal Graph Sequence)**:

$$\mathcal{G} = \{ G_t \}_{t=1}^T = \{ (V_t, E_t, W_t) \}_{t=1}^T$$

Trong đó, mỗi lát cắt đồ thị (graph snapshot) $G_t$ tại cửa sổ thời gian $t$ được định nghĩa:

1. **Tập đỉnh (Nodes $V_t$):**  
   Tập hợp tất cả các địa chỉ ví (EOA hoặc Smart Contract) có tham gia vào ít nhất một giao dịch gửi hoặc nhận trong cửa sổ thời gian $t$:
   $$V_t = \{ u \in \mathcal{A} \mid \exists v \in \mathcal{A}: (u, v) \in E_t \lor (v, u) \in E_t \}$$
   - *Thuộc tính đỉnh (Node Attributes):* `in_degree`, `out_degree`, `in_volume`, `out_volume`, cùng nhãn phân loại thực thể (`entity_type`: CEX, DEX, DeFi, Custodian,...) được kế thừa từ Task T07.

2. **Tập cạnh (Directed Edges $E_t$):**  
   Một cạnh có hướng $e = (u, v) \in E_t$ biểu diễn luồng chuyển dịch token USDT từ ví nguồn $u$ sang ví đích $v$ trong khoảng thời gian $t$.

3. **Trọng số cạnh (Edge Weights $W_t$) theo yêu cầu T08:**  
   Để phản ánh đầy đủ cả **quy mô dòng vốn** lẫn **tần suất tương tác**, mỗi cạnh $e = (u, v)$ được gán đa trọng số:
   - **`total_value` (Volume Weight):** Tổng khối lượng USDT chuyển giao giữa $u \to v$ trong $t$:
     $$w_{\text{val}}(u, v, t) = \sum_{k \in \text{Transfers}(u \to v, t)} \text{amount}_k$$
   - **`transaction_count` (Frequency Weight):** Số lượng sự kiện chuyển token (transfer events) giữa $u \to v$ trong $t$:
     $$w_{\text{freq}}(u, v, t) = |\text{Transfers}(u \to v, t)|$$
   - **`mean_value`:** Giá trị trung bình trên mỗi lượt chuyển: $\frac{w_{\text{val}}}{w_{\text{freq}}}$.
   - **`min_value`, `max_value`, `first_timestamp`, `last_timestamp`:** Thống kê biên độ và chuỗi thời gian nội bộ cửa sổ.

---

## 2. Cửa sổ Thời gian (Time Windows)

Hệ thống hỗ trợ 2 độ phân giải thời gian (temporal granularities) phục vụ các mục tiêu nghiên cứu khác nhau:

| Tiêu chí | Cửa sổ Ngày (Daily Snapshot) | Cửa sổ Tuần (Weekly Snapshot) |
|---|---|---|
| **Ký hiệu** | $G_{t, \text{daily}}$ | $G_{t, \text{weekly}}$ |
| **Độ dài cửa sổ** | 24 giờ UTC (`00:00:00` đến `23:59:59`) | 7 ngày UTC (ISO Week: Thứ 2 đến Chủ nhật) |
| **Tổng số snapshots** | **655 ngày** (từ `2025-01-01` đến `2026-10-17`) | **94 tuần** |
| **Tổng số cạnh có trọng số** | **1.017.003** cạnh | **640.647** cạnh |
| **Số đỉnh trung bình / snapshot** | ~1.096 ví / ngày | ~4.146 ví / tuần |
| **Số cạnh trung bình / snapshot** | ~1.553 cạnh / ngày | ~6.815 cạnh / tuần |
| **Mục đích sử dụng** | Bắt trọn các cú sốc thanh khoản tức thời, contagion shock hàng ngày, phân tích sự kiện ngắn hạn | Nghiên cứu cấu trúc vĩ mô, độ bền vững của mạng lưới, centrality evolution theo tuần |

---

## 3. Cấu trúc Tệp và Dữ liệu Đầu ra

Toàn bộ kết quả được lưu trữ chuẩn hóa tại thư mục `data/processed/graphs/`:

```text
data/processed/graphs/
├── dynamic_edges_daily.parquet        # 1,017,003 cạnh có trọng số theo ngày (79.1 MB)
├── dynamic_edges_weekly.parquet       # 640,647 cạnh có trọng số theo tuần (53.7 MB)
├── graph_metrics_daily.parquet        # Chỉ số topology 655 ngày (43 KB)
├── graph_metrics_daily.csv            # Chỉ số topology 655 ngày bản CSV (105 KB)
├── graph_metrics_weekly.parquet       # Chỉ số topology 94 tuần (8 KB)
├── graph_metrics_weekly.csv           # Chỉ số topology 94 tuần bản CSV (15 KB)
└── t08_summary.json                   # Báo cáo JSON tổng hợp toàn bộ thông số
```

### Chi tiết các cột trong bảng cạnh (`dynamic_edges_*.parquet`):
1. `time_window`: Ngày (`YYYY-MM-DD`) hoặc Tuần (`YYYY-Www`).
2. `from_address`: Địa chỉ ví gửi (lowercase).
3. `to_address`: Địa chỉ ví nhận (lowercase).
4. `total_value`: Tổng khối lượng USDT chuyển giao trong cửa sổ.
5. `transaction_count`: Số giao dịch cá voi giữa 2 ví.
6. `mean_value`: Giá trị trung bình mỗi giao dịch.
7. `min_value` / `max_value`: Giao dịch nhỏ nhất / lớn nhất.
8. `first_timestamp` / `last_timestamp`: Thời điểm giao dịch đầu / cuối trong cửa sổ.
9. `window_type`: `daily` hoặc `weekly`.

### Chi tiết các cột trong bảng chỉ số mạng lưới (`graph_metrics_*.csv`):
1. `time_window`: Nhãn thời gian.
2. `num_nodes` ($|V_t|$): Số lượng ví hoạt động trong snapshot.
3. `num_edges` ($|E_t|$): Số lượng luồng chuyển tiền độc lập giữa các cặp ví.
4. `total_volume_usdt`: Tổng khối lượng USDT luân chuyển trong snapshot.
5. `total_transactions`: Tổng số lượt giao dịch cá voi.
6. `density`: Mật độ liên kết của đồ thị: $D = \frac{|E|}{|V|(|V|-1)}$.
7. `reciprocity`: Tỷ lệ dòng tiền hai chiều tương hỗ giữa các cặp ví.
8. `num_weakly_connected_components`: Số cụm liên thông yếu (WCC).
9. `num_strongly_connected_components`: Số cụm liên thông mạnh (SCC).
10. `max_in_degree` & `max_in_address`: Đỉnh hút dòng tiền mạnh nhất (thường là CEX hot wallet hoặc router hợp đồng).
11. `max_out_degree` & `max_out_address`: Đỉnh phân phối dòng tiền mạnh nhất.

---

## 4. Hướng dẫn Sử dụng Thư viện Lớp `DynamicGraphLoader`

Các thành viên phụ trách các task tiếp theo (T09, T10, Contagion Simulation) có thể trích xuất đồ thị NetworkX trực tiếp cực kỳ đơn giản:

```python
from pathlib import Path
from src.build_dynamic_graph import DynamicGraphLoader

# 1. Khởi tạo loader (tự động tích hợp nhãn thực thể T07 nếu có)
loader = DynamicGraphLoader(
    edges_parquet_path="data/processed/graphs/dynamic_edges_daily.parquet",
    labels_csv_path="data/external/t07_verified_labels.csv"
)

# 2. Xem danh sách các ngày có sẵn (655 ngày)
available_dates = loader.get_time_windows()
print("Ngày đầu:", available_dates[0], "Ngày cuối:", available_dates[-1])

# 3. Trích xuất đồ thị NetworkX DiGraph của một ngày bất kỳ
G_snap = loader.build_snapshot_graph("2025-01-01")

print(f"Số Nodes: {G_snap.number_of_nodes()}")
print(f"Số Edges: {G_snap.number_of_edges()}")

# 4. Duyệt các cạnh và trọng số
for u, v, data in list(G_snap.edges(data=True))[:5]:
    print(f"{u} -> {v} | Value: {data['weight']:,.2f} USDT | Txs: {data['transaction_count']}")
```

