# On-chain Network Whale Contagion Analysis 🐋

Dự án phân tích mạng lưới và mô hình hóa sự lan truyền rủi ro (Contagion Modeling) từ các giao dịch của cá voi (Whale Transactions) trên mạng lưới Ethereum.

---

## 📌 Tổng Quan Dự Án

- **Token nghiên cứu:** USDT (Tether USD ERC-20 — Contract: `0xdac17f958d2ee523a2206206994597c13d831ec7`, Decimals: 6).
- **Khoảng thời gian nghiên cứu (Dataset Freeze):** Từ **`2025-01-01`** đến **`2026-10-17`** (655 ngày liên tục).
- **Ngưỡng lấy mẫu cá voi (Whale Threshold):** $\ge 500.000$ USDT / giao dịch.
- **Quy mô tập dữ liệu thu thập:** **2.113.146** giao dịch cá voi, tổng volume luân chuyển hàng nghìn tỷ USD.

---

## 📁 Cấu Trúc Thư Mục Dự Án

```text
On-chain-Network-Whale-Contagion-Analysis/
├── data/
│   ├── external/                      # Dữ liệu nhãn ví xác thực bên ngoài
│   ├── interim/                       # Dữ liệu transfer chuẩn hóa (2.1M txs)
│   │   └── usdt_whale_transfers_interim.parquet
│   ├── processed/
│   │   ├── graphs/                    # Kết quả đồ thị động T08 (Daily & Weekly)
│   │   │   ├── dynamic_edges_daily.parquet
│   │   │   ├── dynamic_edges_weekly.parquet
│   │   │   ├── graph_metrics_daily.csv
│   │   │   ├── graph_metrics_weekly.csv
│   │   │   └── t08_summary.json
│   │   └── t07/                       # Nhãn ví phân loại thực thể T07
│   └── raw/
│       └── daily/                     # 655 file dữ liệu thô theo từng ngày
├── docs/                              # Tài liệu kỹ thuật & Báo cáo nghiệm thu
│   ├── T04_data_sampling_strategy.md
│   ├── T04_T05_completion_report.md
│   ├── T08_dynamic_graph_specification.md
│   └── T08_completion_report.md
├── src/                               # Mã nguồn cốt lõi
│   ├── download_and_normalize_transfers.py   # Pipeline crawl BigQuery (T05)
│   └── build_dynamic_graph.py                 # Pipeline xây dựng đồ thị động (T08)
├── T06_Binance_to_Drive.py            # Thu thập dữ liệu thị trường (T06)
├── T07_Wallet_Labeling.py             # Gán nhãn thực thể ví cá voi (T07)
├── T08_Dynamic_Transaction_Graph.py   # CLI xây dựng đồ thị mạng lưới động (T08)
├── requirements.txt                   # Danh sách thư viện Python
└── .gitattributes                     # Cấu hình Git LFS quản lý file parquet
```

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Dành Cho Thành Viên Nhóm

### Bước 1: Clone Repository & Tải Dữ Liệu Lớn (Git LFS)

Dự án sử dụng **Git LFS (Large File Storage)** để quản lý các file dữ liệu `.parquet`. Hãy đảm bảo máy bạn đã cài Git LFS:

```bash
# 1. Clone repository
git clone https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis.git
cd On-chain-Network-Whale-Contagion-Analysis

# 2. Khởi tạo Git LFS và kéo toàn bộ dữ liệu parquet về máy
git lfs install
git lfs pull
```

### Bước 2: Cài Đặt Thư Viện Python

Khuyến nghị sử dụng Python $\ge$ 3.10:

```bash
pip install -r requirements.txt
```

---

## ⚡ Hướng Dẫn Thực Thi Từng Phân Hệ (Pipelines)

### 1. Phân hệ Đồ thị Động (Task T08)
*Không yêu cầu tài khoản GCP hay API Key, chạy trực tiếp trên dữ liệu nội bộ:*

**A. Chạy xây dựng toàn bộ chuỗi đồ thị động:**
```bash
python T08_Dynamic_Transaction_Graph.py
```
- Tự động xây dựng chuỗi đồ thị **Daily ($G_{t,\text{daily}}$ - 655 ngày)** và **Weekly ($G_{t,\text{weekly}}$ - 94 tuần)**.
- Gán trọng số cạnh: `total_value` (tổng volume), `transaction_count` (số lượt chuyển), `mean_value`.
- Tính toán toàn bộ chỉ số topology mạng lưới: Density, Reciprocity, SCC, WCC, Top Degree.
- Kết quả xuất tại: `data/processed/graphs/`.

**B. Hiển thị trực quan đồ thị động $G_t$ (Mở ngay trên Trình duyệt Web & GUI):**
*Sử dụng cờ `--show-only` để xem nhanh đồ thị trong 1-2 giây từ dữ liệu đã có:*

```bash
# Xem toàn bộ các cạnh của ngày bất kỳ (cờ --all-edges):
python T08_Dynamic_Transaction_Graph.py --show-only --date 2025-01-01 --all-edges

# Tùy chỉnh số lượng cạnh lớn nhất hiển thị (Top-K edges):
python T08_Dynamic_Transaction_Graph.py --show-only --date 2025-06-15 --top-k 500

# Xem đồ thị theo snapshot Tuần (Weekly):
python T08_Dynamic_Transaction_Graph.py --show-only --date 2025-W10 --top-k 300
```
- Tự động mở file HTML tương tác trên trình duyệt Web (cho phép kéo thả từng ví, phóng to, thu nhỏ, rê chuột xem địa chỉ và volume).
- Tự động bật cửa sổ hình ảnh NetworkX Matplotlib.

### 2. Phân hệ Gán Nhãn Ví (Task T07)
```bash
python T07_Wallet_Labeling.py
```

### 3. Phân hệ Tải & Cập Nhật Dữ Liệu BigQuery (Task T05)
*(Chỉ cần khi muốn tải lại dữ liệu từ đầu từ Google Cloud BigQuery)*
```bash
python src/download_and_normalize_transfers.py
```

---

## 💡 Cách Sử Dụng `DynamicGraphLoader` Trong Code Python (T09, T10, Contagion)

Các thành viên làm mô hình lan truyền (Contagion Simulation) hoặc phân tích chỉ số trung tâm có thể nạp nhanh đồ thị NetworkX:

```python
from src.build_dynamic_graph import DynamicGraphLoader

# Khởi tạo loader (tự động tích hợp nhãn CEX, DEX, DeFi nếu có)
loader = DynamicGraphLoader(
    edges_parquet_path="data/processed/graphs/dynamic_edges_daily.parquet",
    labels_csv_path="data/external/t07_verified_labels.csv"
)

# Lấy danh sách 655 ngày
dates = loader.get_time_windows()

# Trích xuất đồ thị NetworkX DiGraph của một ngày bất kỳ
G_t = loader.build_snapshot_graph("2025-01-01")

print(f"Số Nodes: {G_t.number_of_nodes()}")
print(f"Số Cạnh: {G_t.number_of_edges()}")

# Đọc trọng số cạnh
for u, v, data in list(G_t.edges(data=True))[:3]:
    print(f"{u} -> {v} | Volume: {data['weight']:,.2f} USDT | Txs: {data['transaction_count']}")
```



