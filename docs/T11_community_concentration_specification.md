# T11 — Community Detection và Network Concentration (RQ4)

Chạy `python T11_Community_Concentration.py` từ thư mục gốc dự án. Cấu hình chung đọc từ `config/config.yaml`, cấu hình tham số riêng của T11 nằm tại `config/t11.yaml`. Việc tách file cấu hình riêng giúp T11 không làm thay đổi các file cấu hình đã được ký hash của T08, T09 và T10. T11 phụ thuộc trực tiếp vào dữ liệu T08 đã nghiệm thu.

---

## 1. Mục Tiêu Nghiên Cứu và Câu Hỏi Nghiên Cứu (RQ4)

* **Câu hỏi nghiên cứu cốt lõi (RQ4):** *"Community concentration có tăng trước stress events không?"*
* **Ý nghĩa tài chính và mạng lưới:** 
  Trong điều kiện thị trường bình thường, dòng vốn cá voi luân chuyển phân tán qua nhiều cụm thanh khoản (DEX pools, CEX market makers, OTC brokers, lending protocols). Khi thị trường bước vào giai đoạn biến động mạnh (market stress / liquidity crisis), mạng lưới có xu hướng:
  1. Phân mảnh thành các cụm biệt lập với độ kết nối nội bộ cao (tăng **Modularity $Q_t$**).
  2. Dòng tiền tập trung cực đoan vào một vài cộng đồng đầu não hoặc một số ít ví cá voi cốt lõi (tăng **HHI**, tăng **Gini**, tăng **Top-k Concentration Ratios**).
  3. Chỉ số tập trung cộng đồng tổng hợp (**$CCI_t = Q_t \times HHI_{\text{comm\_volume}}$**) tăng vọt, báo hiệu sự tích tụ rủi ro hệ thống trước khi các cú sụp đổ thanh khoản diễn ra.

---

## 2. Dữ Liệu Đầu Vào

* Đọc trực tiếp các cạnh có hướng đã netting từ T08:
  * `data/processed/graphs/dynamic_edges_daily.parquet` (655 ngày UTC từ `2025-01-01` đến `2026-10-17`).
  * `data/processed/graphs/dynamic_edges_weekly.parquet` (94 tuần ISO bắt đầu thứ Hai).
* Kiểm tra xác thực tính toàn vẹn (SHA256) của T08 qua hàm `verified_t08_inputs()` trước khi tính toán.
* Giữ nguyên lịch chuẩn 655 ngày và 94 tuần; các cửa sổ rỗng vẫn có 1 dòng snapshot với các chỉ số bằng 0. Tuần đầu/cuối thiếu ngày có cờ `eligible_for_regression=false`.

---

## 3. Định Nghĩa Toán Học Các Chỉ Số

### A. Phát hiện cộng đồng và Modularity ($Q$)
* **Thuật toán Louvain có trọng số:** Tìm phân hoạch cộng đồng $\mathcal{C} = \{C_1, C_2, \dots, C_K\}$ tối ưu hóa hàm Modularity có hướng của NetworkX:
  $$Q = \frac{1}{m} \sum_{i,j} \left( A_{ij} - \gamma \frac{k_i^{out} k_j^{in}}{m} \right) \delta(c_i, c_j)$$
  với $A_{ij}$ là trọng số chuyển tiền USDT từ $i \to j$, $m = \sum_{ij} A_{ij}$, $\gamma$ là resolution parameter (mặc định = 1.0).
* **Deterministic Seeding:** Seed ngẫu nhiên của từng snapshot được băm cố định bằng SHA-256 từ `seed|window_type|time_window` để đảm bảo 100% tái lập.
* **Sắp xếp cộng đồng:** Các cộng đồng được sắp xếp giảm dần theo số lượng node, sau đó theo tổng volume. Cộng đồng lớn nhất luôn mang `community_id = 0` (*Giant Community*).
* **Giant Community Metrics:**
  * `giant_community_nodes`: Số node thuộc cộng đồng lớn nhất.
  * `giant_community_node_ratio`: Tỷ lệ $N_{\text{giant}} / N_{\text{total}}$.
  * `giant_community_volume`: Tổng throughput volume của cộng đồng lớn nhất.
  * `giant_community_volume_ratio`: Tỷ trọng $V_{\text{giant}} / V_{\text{total}}$.
* **Internal Volume Ratio:** Tỷ trọng volume các giao dịch diễn ra hoàn toàn nội bộ trong cùng một cộng đồng:
  $$\text{InternalRatio} = \frac{\sum_{(u,v) \in E, c(u)=c(v)} w(u,v)}{\sum_{e \in E} w(e)}$$

### B. Chỉ số tập trung mạng lưới (Network Concentration)
1. **Herfindahl-Hirschman Index (HHI):**
   * **$HHI_{\text{volume}}$:** Đo lường mức độ tập trung dòng tiền ở cấp độ từng ví:
     $$HHI_{\text{volume}} = \sum_{i \in V} \left( \frac{\text{Volume}_i}{\sum_j \text{Volume}_j} \right)^2 \in [0, 1]$$
   * **$HHI_{\text{degree}}$:** Đo mức độ tập trung số liên kết bậc ở cấp độ ví.
   * **$HHI_{\text{community\_volume}}$:** Đo mức độ tập trung dòng tiền ở cấp độ cộng đồng:
     $$HHI_{\text{community\_volume}} = \sum_{c=1}^K \left( \frac{V_c}{V_{\text{total}}} \right)^2 \in [0, 1]$$
   * **$HHI_{\text{community\_nodes}}$:** Đo mức độ tập trung số lượng node vào các cộng đồng lớn.

2. **Hệ số Bất bình đẳng Gini (Gini Coefficient):**
   * Tính theo công thức chuẩn đại số tuyến tính:
     $$Gini(x) = \frac{2 \sum_{i=1}^n i \cdot x_{(i)}}{n \sum_{i=1}^n x_{(i)}} - \frac{n+1}{n}$$
   * Được tính riêng cho phân phối Volume ($Gini_{\text{volume}}$) và phân phối Degree ($Gini_{\text{degree}}$).

3. **Tỷ Lệ Tập Trung Top-k (Concentration Ratios):**
   * $CR_1, CR_5, CR_{10}, CR_{20}$: Tỷ trọng volume của top 1, 5, 10, 20 ví cá voi lớn nhất.
   * $CR_{\text{top1pct}}, CR_{\text{top5pct}}$: Tỷ trọng volume của top 1% và top 5% ví cá voi.

4. **Shannon Entropy Chuẩn Hóa:**
   * Đo lường mức độ đa dạng hóa / phân tán dòng vốn:
     $$\text{Entropy}_{\text{volume}} = - \frac{\sum_i p_i \ln(p_i)}{\ln(N)} \in [0, 1]$$
   * Giá trị tiến về 1 nghĩa là dòng tiền phân tán đều; tiến về 0 nghĩa là dòng tiền siêu tập trung.

5. **Community Concentration Index ($CCI_t$):**
   $$CCI_t = \text{Modularity}_t \times HHI_{\text{community\_volume}, t}$$
   Chỉ số đo lường đồng thời tính phân cụm và độ tập trung dòng vốn vào các cụm cá voi đầu não.

---

## 4. Danh Mục Sản Phẩm Bàn Giao

Toàn bộ dữ liệu xuất ra tại thư mục `data/processed/t11/`:
1. `community_nodes_daily.parquet` & `community_nodes_weekly.parquet`:
   Khóa: `(window_type, time_window, address)`.
   Gồm các cột: `community_id`, `community_size`, `community_volume_usdt`, `is_giant_community`, `node_volume_usdt`, `node_degree` cùng các cờ lịch.
2. `snapshot_metrics_daily.parquet` & `snapshot_metrics_weekly.parquet`:
   Khóa: `(window_type, time_window)`.
   Gồm đầy đủ các chỉ số: `num_nodes`, `num_edges`, `num_communities`, `modularity`, `giant_community_*`, `hhi_*`, `gini_*`, `cr*`, `entropy_*`, `community_concentration_index`.
3. `t11_validation.parquet`: Bảng kết quả kiểm tra chất lượng và ràng buộc toán học cho 749 cửa sổ.
4. `t11_summary.json`: Tóm tắt tổng thể, metadata SHA256 và bằng chứng nghiệm thu sẵn sàng cho downstream.
5. `t11_reproducibility.json`: Đối chiếu SHA256 hai lượt chạy độc lập (bit-for-bit identical).

---

## 5. Quy Trình Chạy và Nghiệm Thu

```bash
# 1. Chạy pipeline tính toán và tự động đối chiếu tái lập lần 2
python T11_Community_Concentration.py

# 2. Chạy bộ kiểm định độc lập
python scripts/validate_t11_current.py
```

