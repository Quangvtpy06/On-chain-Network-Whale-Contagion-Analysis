# On-chain Network Whale Contagion Analysis 🐋

Dự án phân tích mạng lưới và mô hình hóa sự lan truyền rủi ro (Contagion Modeling) từ các giao dịch của cá voi (Whale Transactions) trên mạng lưới Ethereum.

Bảng dữ liệu đầu ra chỉ lưu Parquet; chỉ giữ `eth_stats_from_2025.csv` tại thư mục gốc.
Các báo cáo và metadata kiểm định tiếp tục dùng Markdown/JSON.
Danh sách file bàn giao Hugging Face được tạo bằng `scripts/prepare_hf_manifest.py`;
xem [quy ước dữ liệu dùng chung](docs/DATA_HANDOFF.md). Test/cache không đưa vào dataset.

T12 hiện là điểm thăm dò địa chỉ hoạt động lớn, chưa xác nhận nhà đầu tư cá nhân.
Chạy `python T12_Whale_Score.py` cho raw và audit hoặc
`python T12_Whale_Score_Audit.py` nếu raw đã khớp hash. Audit so raw/log,
độ phủ nhãn theo USDT, top 50 liền kề và ứng viên nhãn chờ người xác minh.
Lệnh audit cũng tạo cohort 30 ngày kết thúc t−1 và CEX diagnostics (tách DEX).
Sau khi 23 pytest đạt, mã test và dữ liệu/cache tạm đã được xóa theo yêu cầu
bàn giao. Giữ bằng chứng JSON và kiểm định dữ liệu thật trong pipeline.
Xem [báo cáo T12](docs/T12_completion_report.md) và gate T14/T15
trong `data/processed/t12/t12_downstream_gate.json` trước khi dùng WhaleFlow.
Gate chỉ chặn WhaleFlow theo cohort; các nhánh T14 độc lập được triển khai song
song. Cấu hình lọc đóng băng ở `config/t12_design.yaml`, không chọn lại sau T15.

---

## 📌 Tổng Quan Dự Án

- **Token nghiên cứu:** USDT (Tether USD ERC-20 — Contract: `0xdac17f958d2ee523a2206206994597c13d831ec7`, Decimals: 6).
- **Khoảng thời gian nghiên cứu (Dataset Freeze):** Từ **`2025-01-01`** đến **`2026-10-17`** (655 ngày liên tục).
- **Ngưỡng lấy mẫu cá voi (Whale Threshold):** $\ge 500.000$ USDT / giao dịch.
- **Quy mô dữ liệu nguồn:** **2.113.146 sự kiện transfer ERC-20**; T08 dùng dữ liệu đã netting theo transaction/cặp ví, không coi mỗi sự kiện là một dòng tiền độc lập.

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
│   │   │   ├── graph_metrics_daily.parquet
│   │   │   ├── graph_metrics_weekly.parquet
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
└── .gitattributes                     # Quy ước lưu dữ liệu qua Hugging Face
```

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Dành Cho Thành Viên Nhóm

### Bước 1: Clone code từ GitHub

GitHub lưu code, cấu hình và tài liệu. Dữ liệu dùng chung lưu tại
`team-crypto/Market-data-crypto-project` trên Hugging Face; thư mục data được Git bỏ qua.

```bash
# 1. Clone repository
git clone https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis.git
cd On-chain-Network-Whale-Contagion-Analysis

```

### Bước 2: Cài Đặt Thư Viện Python

Khuyến nghị sử dụng Python $\ge$ 3.10:

```bash
pip install -r requirements.txt
```

### Bước 3: Tải bộ dữ liệu đã nghiệm thu từ Hugging Face

Chạy đoạn Python sau ở gốc dự án sau khi cài thư viện. Revision được cố định cho
cả lần tải, chỉ lấy danh sách bàn giao và dữ liệu nguồn được manifest ghi nhận:

```python
import json
from huggingface_hub import HfApi, hf_hub_download, snapshot_download

repo = 'team-crypto/Market-data-crypto-project'
revision = HfApi().repo_info(repo, repo_type='dataset').sha
manifest = json.load(open(hf_hub_download(repo, 'data/hf_release_manifest.json',
    repo_type='dataset', revision=revision), encoding='utf-8'))
paths = [row['path'] for row in manifest['upload_files']]
paths += ['data/hf_release_manifest.json']
snapshot_download(repo, repo_type='dataset', revision=revision,
    allow_patterns=paths, local_dir='.')
```

T09: `python T09_Network_Centrality.py`, sau đó chạy các lệnh nghiệm thu trong
`docs/T09_centrality_specification.md`. T10: `python T10_Heavy_Graph_Metrics.py`
tự tính hai lượt, so hash và kiểm định; xem `docs/T10_heavy_metrics_specification.md`.
T11: `python T11_Community_Concentration.py` phát hiện cộng đồng Louvain, tính modularity
và chỉ số tập trung mạng lưới (HHI, Gini, CR-k, CCI) phục vụ RQ4; xem `docs/T11_community_concentration_specification.md`.
T12: `python T12_Whale_Score.py` tính WhaleScore từ T07/T09, gắn cờ hạ tầng
và tạo ranking qua bộ lọc; xem `docs/T12_whale_score_specification.md`.
High-centrality hoặc score cao không xác nhận nhà đầu tư cá nhân.

Để bàn giao dữ liệu: đăng nhập bằng `hf auth login`, chạy
`python scripts/prepare_hf_manifest.py`, rồi `python scripts/publish_hf_release.py`.
Lệnh upload kiểm tra hash trước/sau và chỉ đẩy danh sách được manifest chấp nhận.

---

## ⚡ Hướng Dẫn Thực Thi Từng Phân Hệ (Pipelines)

### 1. Phân hệ Đồ thị Động (Task T08)
*Không yêu cầu tài khoản GCP hay API Key, chạy trực tiếp trên dữ liệu nội bộ:*

**A. Chạy xây dựng toàn bộ chuỗi đồ thị động:**
```bash
python T08_Dynamic_Transaction_Graph.py
```
- Tự động xây dựng chuỗi đồ thị **Daily ($G_{t,\text{daily}}$ - 655 ngày)** và **Weekly ($G_{t,\text{weekly}}$ - 94 tuần)**.
- Gộp hai chiều trong từng transaction/cặp, áp lại ngưỡng 500.000 USDT; giữ nguyên file gốc.
- `transaction_count` là số transaction_hash khác nhau trên từng cạnh, không phải số sự kiện.
- Mặc định chạy hai lần, so hash và review tính toán độc lập; xem `t08_acceptance_checks.parquet` cho B.1–B.9.
- Chỉ dùng cho T09–T12 khi `ready_for_t09_t12` trong summary là true. Hai tuần thiếu ngày không dùng trong hồi quy.
- Tính toán toàn bộ chỉ số topology mạng lưới: Density, Reciprocity, SCC, WCC, Top Degree.
- Kết quả xuất tại: `data/processed/graphs/`.

**B. Hiển thị trực quan đồ thị động $G_t$ (Mở ngay trên Trình duyệt Web & GUI):**
*Sử dụng cờ `--show-only` để xem đồ thị từ dữ liệu đã có:*

```bash
# Xem toàn bộ các cạnh của ngày bất kỳ (cờ --all-edges):
python T08_Dynamic_Transaction_Graph.py --show-only --date 2025-01-01 --all-edges

# Tùy chỉnh số lượng cạnh lớn nhất hiển thị (Top-K edges):
python T08_Dynamic_Transaction_Graph.py --show-only --date 2025-06-15 --top-k 500

# Xem đồ thị theo snapshot Tuần (Weekly):
python T08_Dynamic_Transaction_Graph.py --show-only --date 2025-W10 --top-k 300
```
- Biểu đồ HTML offline: zoom bằng con lăn, kéo để di chuyển, nhấp đúp hoặc bấm “Đặt lại góc nhìn” để khôi phục.
- Màu và kích thước nút theo độ kết nối; có thể đổi màu theo nhãn T07. Contract có hình thoi, địa chỉ khác hình tròn.
- Rê chuột lên mũi tên để xem ví gửi/nhận, volume ròng, số giao dịch, gross và số sự kiện nguồn. Ô tìm ví hỗ trợ phóng đến một địa chỉ đầy đủ.
- Thêm `--no-open` nếu chỉ muốn xuất HTML. Ví dụ sát ảnh mẫu: `python T08_Dynamic_Transaction_Graph.py --show-only --date 2026-10-15 --all-edges`.

### 2. Phân hệ Gán Nhãn Ví (Task T07)
```bash
python T07_Wallet_Labeling.py
# Sau khi có bảng hoạt động đầy đủ và public enrichment:
python T07_Complete_Wallet_Labels.py
```

T08 đọc bảng `t07_complete_wallet_labels.parquet` theo config, gồm mọi địa chỉ,
nhãn có bằng chứng và trạng thái contract từ BigQuery. Các thực thể chưa xác minh
giữ Unknown hoặc Contract, không suy tên tổ chức từ volume.

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
    labels_parquet_path="data/processed/t07/t07_complete_wallet_labels.parquet"
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


