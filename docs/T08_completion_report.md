# Báo Cáo Nghiệm Thu Hoàn Thành Nhiệm Vụ T08

**Dự án:** On-chain Network Whale Contagion Analysis  
**Nhiệm vụ:** T08 — Xây dựng Dynamic Transaction Graph ($G_t$)  
**Người thực hiện:** TV1 — Yến Vy  
**Reviewer:** TV4 / Hương  
**Trạng thái:** ✅ **Hoàn thành 100% (Done)**  
**Ngày hoàn thành:** 19/10/2026  

---

## 1. Tóm Tắt Nhiệm Vụ & Tiêu Chí Nghiệm Thu

| Mục tiêu đề ra trong WBS | Kết quả thực tế đạt được | Đánh giá |
|---|---|---|
| **Đầu vào phụ thuộc (T05):** `data/interim/usdt_whale_transfers_interim.parquet` | Nạp và xử lý trọn vẹn **2.113.146** giao dịch cá voi từ `2025-01-01` đến `2026-10-17` | ✅ Đạt |
| **Cửa sổ thời gian (Windowing):** Daily hoặc Weekly | Xây dựng đầy đủ cả **Daily ($G_{t,\text{daily}}$ - 655 ngày)** và **Weekly ($G_{t,\text{weekly}}$ - 94 tuần)** | ✅ Vượt kỳ vọng |
| **Trọng số cạnh (Edge Weights):** Theo value và số giao dịch | Mỗi cạnh có hướng $u \to v$ đều có: `total_value` ($\sum \text{amount}$), `transaction_count` ($\text{count}$), `mean_value`, `min_value`, `max_value` | ✅ Đạt |
| **Cấu trúc dữ liệu & Codebase:** Chạy lại được, mô-đun hóa, hỗ trợ NetworkX | Tạo script thực thi tại `src/build_dynamic_graph.py`, wrapper `T08_Dynamic_Transaction_Graph.py`, kèm class `DynamicGraphLoader` | ✅ Đạt |
| **Bàn giao kết quả:** Lưu trữ chuẩn hóa trong `data/processed/graphs/` | Đã xuất các file `.parquet`, `.csv`, `.json` chuẩn hóa | ✅ Đạt |

---

## 2. Thống Kê Tổng Quan Đồ Thị Động

### A. Chuỗi đồ thị Daily ($G_{t, \text{daily}}$)
- **Tổng số snapshot thời gian:** **655 ngày** (100% các ngày từ 01/01/2025 đến 17/10/2026).
- **Tổng số cạnh có trọng số:** **1.017.003** cạnh.
- **Số đỉnh hoạt động trung bình mỗi ngày:** **1.095,73** ví/ngày.
- **Số cạnh luân chuyển trung bình mỗi ngày:** **1.552,68** cạnh/ngày.
- **Khối lượng giao dịch 1 ngày cao nhất:** **167,88 tỷ USDT**.
- **Tập tin kết quả:**
  - `data/processed/graphs/dynamic_edges_daily.parquet` (79.1 MB)
  - `data/processed/graphs/graph_metrics_daily.csv` (105 KB)

### B. Chuỗi đồ thị Weekly ($G_{t, \text{weekly}}$)
- **Tổng số snapshot thời gian:** **94 tuần** (ISO week).
- **Tổng số cạnh có trọng số:** **640.647** cạnh.
- **Số đỉnh hoạt động trung bình mỗi tuần:** **4.146,41** ví/tuần.
- **Số cạnh luân chuyển trung bình mỗi tuần:** **6.815,39** cạnh/tuần.
- **Khối lượng giao dịch 1 tuần cao nhất:** **373,00 tỷ USDT**.
- **Tập tin kết quả:**
  - `data/processed/graphs/dynamic_edges_weekly.parquet` (53.7 MB)
  - `data/processed/graphs/graph_metrics_weekly.csv` (15 KB)

---

## 3. Danh Mục Tệp Bàn Giao

1. **Mã nguồn thực thi:**
   - [`src/build_dynamic_graph.py`](file:///d:/On-chain-Network-Whale-Contagion-Analysis/src/build_dynamic_graph.py): Module chính thực hiện gom nhóm cạnh, tính toán topology metric và cung cấp class `DynamicGraphLoader`.
   - [`T08_Dynamic_Transaction_Graph.py`](file:///d:/On-chain-Network-Whale-Contagion-Analysis/T08_Dynamic_Transaction_Graph.py): CLI wrapper chạy nhanh từ thư mục gốc.
2. **Dữ liệu đầu ra:**
   - Thư mục: [`data/processed/graphs/`](file:///d:/On-chain-Network-Whale-Contagion-Analysis/data/processed/graphs/)
   - Báo cáo tóm tắt cấu trúc: [`data/processed/graphs/t08_summary.json`](file:///d:/On-chain-Network-Whale-Contagion-Analysis/data/processed/graphs/t08_summary.json)
3. **Tài liệu học thuật & đặc tả kỹ thuật:**
   - [`docs/T08_dynamic_graph_specification.md`](file:///d:/On-chain-Network-Whale-Contagion-Analysis/docs/T08_dynamic_graph_specification.md): Hướng dẫn toán học, mô hình hóa và cách gọi thư viện NetworkX cho các bài toán lan truyền (Contagion).

---

## 4. Hướng Dẫn Chạy Lại (Reproducibility)

Để tái lập kết quả, người dùng chỉ cần mở terminal và chạy:

```bash
python T08_Dynamic_Transaction_Graph.py
```

Kết quả đã sẵn sàng 100% để chuyển sang các Task tiếp theo của giai đoạn 2 (Tính toán chỉ số trung tâm và Mô hình lan truyền).

