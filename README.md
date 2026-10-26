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

V1 và gate bảo thủ của v1 được giữ nguyên: [T12 cohort acceptance](docs/T12_cohort_acceptance.md).
Protocol mới cho **địa chỉ hoạt động lớn chưa được định danh**:
[T12 protocol v2](docs/T12_protocol_v2.md). Chạy `python scripts/run_t12_v2.py`,
rồi review độc lập bằng `python scripts/validate_t12_v2.py`.
Kết quả ở `data/processed/t12/v2/`; T14 phải đọc gate v2 và đúng `cohort_path`
trong gate, không dùng cohort v1 mặc định. V2 giữ ngưỡng v1, báo cáo Unknown và
nhánh loại hạ tầng hồi cứu riêng; không xác nhận nhà đầu tư cá nhân hay endpoint CEX PIT.
Xem [kết quả nghiệm thu v2](docs/T12_v2_completion_report.md).

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
T11: `python T11_Community_Concentration.py` tính community Louvain có hướng,
modularity và chỉ số tập trung từ T08. Chạy hai tiến trình, so hash tám Parquet
và kiểm định độc lập đủ 749 cửa sổ; chỉ sau khi đạt mới bật ready_for_downstream.
`--skip-reproducibility` chỉ dùng khảo sát và luôn giữ ready=false.
Đầu ra có bảng top community, regime hồi cứu và so sánh RQ4; biểu đồ PNG ở
`data/figures/t11/`. “High-volume” là proxy từ volume transfer, không phải stress
thị trường được xác nhận. Ba ngày cuối thiếu cửa sổ tương lai không vào so sánh.
Welch/Holm là thăm dò, không chứng minh nhân quả hoặc danh tính cá nhân.
Xem [đặc tả T11](docs/T11_community_concentration_specification.md),
[báo cáo T11](docs/T11_completion_report.md) và [review](docs/T11_review_report.md).
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

Lịch sử nhãn CEX cho T14 được bổ sung riêng ở `data/processed/t07/cex_history/`.
Xem [bảng review nguồn lịch sử](docs/T07_CEX_history_review_packet.md),
[hướng dẫn duyệt và loader T14](docs/T07_CEX_history_handoff.md) và
[kết quả kiểm định](docs/T07_CEX_history_completion_report.md).
Chạy offline `python scripts/build_t07_cex_history.py`; chỉ hàng được người review
duyệt mới vào `t07_cex_label_history.parquet`. Không dùng candidates làm endpoint PIT.

Bản phát hành T07/T12 dùng manifest riêng `data/hf_t07_t12_release_manifest.json`,
được tạo bằng `python scripts/prepare_t07_t12_release.py`; publisher hỗ trợ
`--manifest data/hf_t07_t12_release_manifest.json`. Xem
[công việc T14 cần sửa sau bàn giao](docs/T14_fix_handoff_T07_T12.md).

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

### T14 — nghiệm thu đầu vào theo phạm vi

Chạy `python T14_Flow_Volatility.py`, rồi `python scripts/validate_t14_release.py`.
Hợp đồng `t14_inputs_v1` cấp riêng `forecast_inputs_ready_cex` và
`forecast_inputs_ready_activity_cohort`; không sửa cờ RQ3 T07/T12 và không chứng nhận danh tính cá nhân.
T15/T16 kiểm tra gate/hash trước khi dùng eligibility/predictor_sets. Xem
[đặc tả T14](docs/T14_flow_volatility_specification.md). Gói đã được phát hành lên GitHub/HF; xem [receipt và revision đầu vào](docs/T14_release_receipt.md).

### T15/T16 — hồi quy và phản ứng quanh sự kiện

```bash
python T15_Volatility_Regression.py
python T16_Event_Study.py
python scripts/validate_t15_t16_release.py
python scripts/prepare_t15_t16_release.py
```

T15 dùng OLS/HAC, so baseline và flow trên cùng ngày/cùng control, tách activity cohort và CEX;
báo cả p thô và Holm. T16 tách CEX NetFlow khỏi flow cohort, chọn cửa sổ UTC không chồng cho
phân tích chính, bootstrap block và báo độ nhạy. Cả hai xác minh release T14 trước khi đọc eligibility.
Output bảng chỉ Parquet tại `data/processed/t15` và `data/processed/t16`, kèm report, PNG và JSON hash.
Activity cohort là địa chỉ hoạt động lớn chưa định danh; không chứng nhận nhà đầu tư cá nhân.

Các kết quả là liên hệ trong mẫu và phản ứng mô tả; chưa phải bằng chứng causal hoặc forecast ngoài mẫu.
Sau sửa lỗi ngày 25/10, cả sáu kiểm định flow chính T15 chưa đạt mức 5% sau Holm.
Xem [đặc tả T15](docs/T15_specification.md), [đặc tả T16](docs/T16_specification.md) và
[báo cáo sửa/kiểm định](docs/T15_T16_fix_completion_report.md).
Lệnh prepare chỉ tạo manifest `data/hf_t15_t16_release_manifest.json`, không upload.
Code nghiệm thu đã có trên **main**; output đã phát hành và tải lại kiểm tra 23/23 file khớp.
Xem [biên nhận T15/T16 và revision cần dùng](docs/T15_T16_release_receipt.md); nhánh feature cũ không phải bản nghiệm thu.

### T18 — purged fixed-origin pseudo-OOS

```bash
python T18_Time_Split_Backtest.py
python scripts/validate_t18_release.py
python scripts/prepare_t18_release.py
```

T18 là pipeline riêng trên bản T14/T15/T16 đã nghiệm thu. Train/test được chia theo thời gian,
chỉ dùng nhãn đã khả dụng tại lúc fit và giữ hệ số cố định trong test. Hai nhánh flow được so
với controls/HAR, train mean và persistence trên cùng mẫu. T16 phân chia toàn bộ response window,
giữ rõ trạng thái nhóm không đủ sự kiện. Đây là backtest hồi cứu; test không được coi là chưa từng xem.
Output chỉ Parquet, cùng biểu đồ/report/JSON tại `data/processed/t18`; prepare không tự upload.
Xem [đặc tả](docs/T18_specification.md) và [báo cáo hoàn thành](docs/T18_completion_report.md).
T18 đã phát hành trên main/HF và tải lại xác minh 17/17 file khớp; xem [biên nhận/revision](docs/T18_release_receipt.md).

### T17 — sensitivity trong phạm vi USDT, protocol v2

```bash
python T17_Robustness.py
python scripts/validate_t17_release.py
python scripts/prepare_t17_release.py
```

Phạm vi được chủ dự án chốt: USDT, graph windows ngày/tuần ISO; chưa kiểm tra khả năng
khái quát sang token khác. V2 xác minh release T15/T16 và tái tạo base trước grid, kiểm tra
đúng tập ngày mỗi kịch bản, bổ sung flow k=1/3/7 trên cùng mẫu. Validator riêng kiểm tra
lại z-score, target, ngày mẫu và HAC. Output Parquet/PNG/MD/JSON tại `data/processed/t17`.
Prepare chỉ tạo manifest, không upload. Đây là robustness trong mẫu, không tự hoàn tất RQ3.
Xem [đặc tả T17](docs/T17_specification.md) và [báo cáo hoàn thành](docs/T17_completion_report.md).

### RQ4 — HHI/CCI cộng đồng trước stress thị trường

```bash
python RQ4_Stress_Lead.py
python scripts/validate_rq4_stress_lead.py
```

Dùng ngày stress RV P90 của T13 làm mốc và chỉ số HHI/CCI ngày của T11 ở 1–3 ngày trước.
Gộp các ngày stress gần nhau thành đợt, so với mốc yên bình, bootstrap theo khối lịch
và báo độ nhạy đối chứng cùng thứ trong tuần. Xem [đặc tả](docs/RQ4_stress_lead_specification.md)
và [kết quả](docs/RQ4_stress_lead_completion_report.md). Output Parquet/PNG/JSON/Markdown tại
`data/processed/rq4_stress_lead/`; đây là phép đối chiếu hồi cứu, không chứng nhận dự báo ngoài mẫu.

### Giai đoạn 4 — T19 đến T23 (Graph ML / RQ5)

Cài phụ thuộc ML riêng nếu môi trường hiện tại chưa có PyTorch/PyG:

```bash
pip install -r requirements-stage4.txt
python T19_Graph_ML_Features.py
python T20_Tabular_Node2Vec.py
python T21_GCN_GraphSAGE.py
python T22_GAT_RQ5_Comparison.py
python scripts/validate_stage4_mandatory.py
python T23_Temporal_Graph_Anomaly.py
python scripts/validate_t23_extension.py
```

T19 đóng băng 41 feature tuần và split CEX/DEX hồi cứu. T20–T22 so MLP, Node2Vec, GCN,
GraphSAGE, GAT trên cùng mẫu; chọn GNN bằng validation rồi so với tabular MLP (RQ5).
T23 chỉ chạy sau gate 112 kiểm tra bắt buộc: bất thường chuỗi không giám sát, stress T13
chỉ để đối chiếu mô tả. Loader chấp nhận T19 HF/local cùng nội dung bảng dù khác byte Parquet.
Xem [đặc tả T20–T22](docs/T20_T22_graph_ml_specification.md),
[báo cáo T20–T22](docs/T20_T22_completion_report.md),
[đặc tả T23](docs/T23_temporal_anomaly_specification.md),
[báo cáo T23](docs/T23_completion_report.md) và
[biên bản giai đoạn 4](docs/Stage4_T19_T23_completion_report.md).

### Giai đoạn 5 — T24 đến T27 (On-chain Explorer)

Ứng dụng Streamlit đọc Parquet local nếu có; nếu thiếu, tự tải đúng từng file
cần dùng từ dataset Hugging Face public và cache theo revision đã ghim. Không cần
tải toàn bộ dataset hoặc cấu hình token HF cho demo hiện tại.

```bash
pip install -r demo/requirements.txt
streamlit run app.py --server.address 127.0.0.1
```

Để tạo demo online trên Streamlit Community Cloud:

1. Đẩy code lên GitHub, bảo đảm có `app.py`, `demo/app.py`,
   `demo/requirements.txt` và `.streamlit/config.toml`.
2. Trong Streamlit Community Cloud, chọn **Create app**, repository/branch vừa
   đẩy và đặt **Main file path** là `demo/app.py`.
3. Chọn Python 3.12 trong **Advanced settings**, sau đó deploy. Entry point này
   dùng bộ dependency tối giản trong `demo/requirements.txt`;
   không cài PyTorch/PyG của các pipeline nghiên cứu. Dataset hiện public nên
   không cần khai báo Secrets hoặc HF token.

Dashboard dùng dữ liệu đã nghiệm thu: đồ thị giao dịch đầy đủ theo cửa sổ,
CEX/whale flow, realized volatility, community map, event-time plots và tab trả lời
RQ1–RQ5. Chuỗi thời gian có các preset 30/90/180 ngày hoặc toàn bộ đến ngày đã
chọn; biểu đồ hỗ trợ zoom bằng con lăn, pan bằng kéo và thanh chọn phạm vi. Đồ thị
mạng/cộng đồng có bộ chọn Top-N hoặc tất cả; bảng giữ trọn dữ liệu, có ô tìm kiếm
và CSV xuất theo kết quả lọc. Giao diện dùng theme sáng cố định. Tệp thiếu được tải on-demand từ revision
`3bfb61848e1ac9bcfb0809d3aef334d1885a84a1`; để cập nhật dataset, đổi
`HF_DATASET_REVISION` trong `app.py` sang commit HF đã kiểm tra. Ứng dụng hỗ trợ
ngày/tuần và USDT (tài sản duy nhất hiện có); các địa chỉ ví luôn được ẩn danh.
Số liệu mô tả trong mẫu, không nhận diện chủ ví, không chứng minh quan hệ nhân quả
và không phải khuyến nghị đầu tư. Xem [báo cáo hoàn thành T24–T27](docs/T24_T27_completion_report.md).
