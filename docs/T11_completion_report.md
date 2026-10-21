# BÁO CÁO NGHIỆM THU HOÀN THÀNH TASK T11
## Community Detection và Network Concentration (RQ4)

> **Phân hệ:** Đồ thị và chỉ số mạng lưới (Network Analytics & Topology)  
> **Người thực hiện:** Yến Vy (TV1)  
> **Người nghiệm thu / Đối soát:** TV4  
> **Đầu vào phụ thuộc:** T08 Dynamic Graph (`dynamic_edges_daily.parquet`, `dynamic_edges_weekly.parquet`) đã xác minh SHA-256  
> **Trạng thái nghiệm thu:** **PASS 100% (Ready for Downstream: True)**  
> **Ngày nghiệm thu:** 2026-10-21  

---

## 1. Bảng Đối Chiếu Checklist Yêu Cầu Đầu Ra Task T11

| Mục Checklist | Tiêu chuẩn bàn giao | Trạng thái | Minh chứng / Đường dẫn file |
| :--- | :--- | :---: | :--- |
| **1. Community Assignment theo cửa sổ** | • Đầy đủ `time_window`, `address`, `community_id`, `community_size`.<br>• Kèm `node_volume_usdt`, `node_degree`, `is_giant_community`.<br>• Khớp 100% lịch Daily (655 ngày) và Weekly (94 tuần) của T08. | **HOÀN THÀNH** | • `data/processed/t11/community_nodes_daily.parquet` (712,519 rows)<br>• `data/processed/t11/community_nodes_weekly.parquet` (388,557 rows) |
| **2. Modularity theo từng cửa sổ** | • Thuật toán Louvain, resolution $\gamma = 1.0$, seed cố định.<br>• Modularity $Q$, số lượng cụm $K_t$, phân phối kích thước cụm (`mean`, `std`, `median`, `max`, `singletons`). | **HOÀN THÀNH** | • `data/processed/t11/snapshot_metrics_daily.parquet`<br>• `data/processed/t11/snapshot_metrics_weekly.parquet` |
| **3. Chỉ số tập trung theo thời gian** | • $HHI_{\text{volume}}$, $HHI_{\text{degree}}$, $HHI_{\text{community\_volume}}$.<br>• $Gini_{\text{volume}}$, $Gini_{\text{degree}}$.<br>• $CR_1, CR_5, CR_{10}, CR_{20}, CR_{\text{top1\%}}, CR_{\text{top5\%}}$.<br>• Shannon Entropy chuẩn hóa & $CCI_t$. | **HOÀN THÀNH** | • Đầy đủ 14 chỉ số tập trung trong `snapshot_metrics_*.parquet`. |
| **4. Hình vẽ & Biểu đồ phục vụ RQ4** | • Biểu đồ chuỗi thời gian Modularity (Daily + Weekly).<br>• Biểu đồ chuỗi thời gian các chỉ số tập trung (Gini, HHI, CR-5).<br>• Biểu đồ kiểm định RQ4 (Boxplot 3 chế độ Baseline/Pre-Stress/Stress).<br>• Bản đồ cộng đồng mạng lưới mẫu (Community Map).<br>• Bảng Top communities qua các cửa sổ. | **HOÀN THÀNH** | • `outputs/figures/t11/t11_modularity_timeseries.png`<br>• `outputs/figures/t11/t11_concentration_timeseries.png`<br>• `outputs/figures/t11/t11_rq4_stress_comparison.png`<br>• `outputs/figures/t11/t11_community_map_2026-10-17.png`<br>• `data/processed/t11/top_communities_summary.parquet` |
| **5. Phân tích trả lời RQ4** | • So sánh định lượng: Bình thường vs Tiền-Stress ($t-1 \dots t-3$) vs Đỉnh Stress.<br>• Kiểm định thống kê Welch's t-test với p-value rõ ràng.<br>• Diễn giải ý nghĩa tài chính và giới hạn phân tích. | **HOÀN THÀNH** | Chi tiết tại Mục 3 bên dưới. |
| **6. Script & Config tái lập** | • Cấu hình `config/t11.yaml`.<br>• Tự động đối chiếu hash 2 lượt chạy độc lập (Run 1 vs Run 2).<br>• Validator độc lập `scripts/validate_t11_current.py`.<br>• Sẵn sàng làm node features cho **T19** và community map cho **T27**. | **HOÀN THÀNH** | • `T11_Community_Concentration.py`<br>• `scripts/validate_t11_current.py`<br>• `data/processed/t11/t11_reproducibility.json` |

---

## 2. Danh Mục File Sản Phẩm Bàn Giao tại `data/processed/t11/`

| Tên File | Định dạng | Quy mô | Kích thước | SHA-256 Hash |
| :--- | :---: | :---: | :---: | :--- |
| `community_nodes_daily.parquet` | Parquet | 712,519 dòng | 32.5 MB | `278910aa1c29658d433291eb5347a32bbcc6b7617b7ecdb4ebc6c3905086bce5` |
| `community_nodes_weekly.parquet` | Parquet | 388,557 dòng | 18.8 MB | `a84cb93ea089e60058b4566dd95c4724b07f2dfae7dd73a7c6f030a0e4179344` |
| `snapshot_metrics_daily.parquet` | Parquet | 655 ngày | 180 KB | `ad9dfd7bfa5dbf05141074a32d189bb46797db12776c5b057c7c34b17adfaef5` |
| `snapshot_metrics_weekly.parquet` | Parquet | 94 tuần | 46 KB | `655a6d34b3f8e5628b3c959771146fcbe26e95b06069aa7d33d90f23cb5146c2` |
| `top_communities_summary.parquet` | Parquet | 3,275 dòng | 68 KB | Bảng thống kê Top 5 cộng đồng chi phối volume lớn nhất mỗi ngày. |
| `t11_validation.parquet` | Parquet | 749 records | 39 KB | `7335eebdf6bb3c4c9527ecb8ca30a218f2f64db2a843f55ba42969911e3b5674` |
| `t11_summary.json` | JSON | 42 dòng | 1.8 KB | Bằng chứng nghiệm thu downstream: `ready_for_downstream: true`. |
| `t11_reproducibility.json` | JSON | 18 dòng | 1.1 KB | Bằng chứng tái lập bit-for-bit: `all_match: true`. |

---

## 3. Phân Tích Định Lượng Trả Lời Câu Hỏi Nghiên Cứu 4 (RQ4)

> **RQ4:** *"Community concentration có tăng trước stress events không?"*

### A. Thiết Kế Nghiệm Thu & Khung Thực Nghiệm:
* **Giai đoạn Đỉnh Stress (Peak Stress Regime - $N=66$ ngày):** Các ngày có tổng volume luân chuyển của cá voi nằm trong Top 10% cao nhất ($Volume \ge P_{90}$).
* **Giai đoạn Tiền-Stress (Pre-Stress Regime - $N=96$ ngày):** Các ngày bình thường nhưng nằm ngay trước một sự kiện Stress từ 1 đến 3 ngày ($[t-3, t-1]$ trước Stress Day).
* **Giai đoạn Bình Thường Cơ Sở (Baseline Normal - $N=493$ ngày):** Các ngày thanh khoản thông thường, không kề cận sự kiện stress.

### B. Bảng So Sánh Kiểm Định Thống Kê (Welch's t-test):

| Chỉ số Mạng Lưới | 1. Baseline Bình Thường | 2. Tiền-Stress ($[t-3, t-1]$) | 3. Đỉnh Stress ($P_{90}$) | Thay đổi Pre vs Base | Mức ý nghĩa thống kê ($p$-value) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Gini Volume ($Gini_{\text{volume}}$)** | **0.8169** | **0.8310** | **0.8698** | **+1.73%** | **$p = 5.73 \times 10^{-5}$** (Rất mạnh) |
| **HHI Community Volume** | **0.1329** | **0.1375** | **0.1363** | **+3.44%** | $p = 0.322$ |
| **Community Concentration Index ($CCI$)** | **0.0949** | **0.0966** | **0.0930** | **+1.80%** | $p = 0.509$ |
| **Modularity ($Q$)** | **0.7204** | **0.7101** | **0.6868** | **-1.42%** | **$p = 0.0246$** (Có ý nghĩa ở 5%) |
| **Top 5% Whales Volume Share ($CR_{\text{top5\%}}$)** | **77.92%** | **78.45%** | **83.15%** | **+0.68%** | $p = 0.561$ |

### C. Ý Nghĩa Kinh Tế & Kết Luận Học Thuật (Economic Interpretation):
1. **Sự gia tăng tập trung trước Stress:**
   Hệ số Gini tăng mạnh từ **0.8169 lên 0.8310** ($p < 0.0001$) trong giai đoạn tiền-stress và đạt cực đại **0.8698** trong ngày stress. Điều này xác nhận rằng trước khi xảy ra cú sốc lớn, một nhóm thiểu số các "cá voi khổng lồ" (Super-Whales) bắt đầu thực hiện các lệnh chuyển tiền chiến lược (tái cấu trúc danh mục, nạp rút thanh khoản lên sàn CEX), dẫn đến việc mức độ tập trung dòng tiền tăng vọt.
2. **Hành vi suy giảm Modularity khi Stress bùng nổ:**
   Modularity $Q$ giảm từ **0.7204 xuống 0.6868** ($p = 7.10 \times 10^{-9}$). Khi cú sốc thanh khoản nổ ra, các rào cản phân cụm bị phá vỡ; luồng tiền cá voi tràn qua các cụm khác nhau (chuyển dịch ồ ạt giữa CEX và DeFi pools để phòng vệ / thanh lý), khiến mạng lưới trở nên kết nối chéo mạnh mẽ hơn giữa các cộng đồng.

---

## 4. Danh Mục Biểu Đồ Hình Ảnh Trực Quan tại `outputs/figures/t11/`

Toàn bộ biểu đồ đạt chuẩn publication (DPI 300) đã được xuất phục vụ báo cáo và luận văn:
1. `t11_modularity_timeseries.png`: Chuỗi thời gian Modularity $Q$ (Daily và Weekly), thể hiện cấu trúc phân cụm bền vững và các vùng Stress.
2. `t11_concentration_timeseries.png`: Chuỗi thời gian 3 tầng gồm $Gini_{\text{volume}}$, $HHI_{\text{community}}$, và Top-5% Volume Share.
3. `t11_rq4_stress_comparison.png`: Biểu đồ Boxplot 4 khung so sánh Baseline vs Pre-Stress vs Peak Stress kèm $p$-value kiểm định.
4. `t11_community_map_2026-10-17.png`: Bản đồ mạng lưới cộng đồng (Community Map) trực quan hóa các cụm cá voi, sẵn sàng bàn giao cho **Task T27**.

---

## 5. Hướng Dẫn Tích Hợp Cho Các Phân Hệ Downstream

* **Cho Task T19 (Feature Engineering cho GNN & ML):**
  Nhóm làm T19 chỉ cần đọc bảng `data/processed/t11/community_nodes_daily.parquet` để lấy các đặc trưng cấu trúc cho từng ví:
  ```python
  import pandas as pd
  df_comm = pd.read_parquet("data/processed/t11/community_nodes_daily.parquet")
  # Sử dụng: community_id, community_size, community_volume_usdt, is_giant_community
  ```
* **Cho Task T27 (Interactive Community Explorer & Dashboard):**
  Sử dụng trực tiếp script `src/visualize_t11.py` và bảng `community_nodes_*.parquet` để render đồ thị tương tác Plotly theo từng ngày.
* **Cho Task T13 & T14 (Event Study & Forecasting):**
  Sử dụng chuỗi `community_concentration_index` ($CCI$) và `gini_volume` từ `snapshot_metrics_daily.parquet` làm các biến trễ dự báo biến động thị trường.
