# Báo Cáo Tiến Độ Nhiệm Vụ T04 & T05
**Dự án:** On-chain Network Whale Contagion Analysis  
**Người thực hiện:** TV1 - Yến Vy  
**Reviewer:** TV4  
**Trạng thái:** ✅ **Hoàn thành (Done)**

---

## 1. Nhiệm vụ T04: Truy cập BigQuery và chọn mẫu (Sampling)
- **Token ERC-20:** **USDT (Tether USD)** — Contract `0xdac17f958d2ee523a2206206994597c13d831ec7` (Decimals: 6).
- **Khoảng thời gian:** Từ `2025-01-01` đến `18/10/2026` (~22 tháng).
- **Chiến lược lấy mẫu (Sampling Strategy):** **Whale Ego-Network Sampling**
  - Lọc các giao dịch chuyển token giá trị lớn ($\ge 500.000$ USDT) để nắm bắt các nút mạng trọng yếu (Cá voi, Quỹ đầu tư, Smart Contracts của CEX/DEX).
  - Lý do: Loại bỏ nhiễu từ các micro-transaction, tối ưu quota BigQuery Sandbox (<500GB/lần chạy) và tạo mạng đồ thị có ý nghĩa phục vụ mô hình lan truyền (Contagion Model).
- **Tài liệu chi tiết:** [T04_data_sampling_strategy.md](file:///D:/On-chain-Network-Whale-Contagion-Analysis/docs/T04_data_sampling_strategy.md)

---

## 2. Nhiệm vụ T05: Script tải và chuẩn hóa transfer
- **Script pipeline:** [download_and_normalize_transfers.py](file:///D:/On-chain-Network-Whale-Contagion-Analysis/src/download_and_normalize_transfers.py)
  - Chạy lại được (idempotent / reproducible).
  - Tích hợp kiểm tra chi phí truy vấn (Dry-run) trước khi scan.
- **Dữ liệu thô (Raw Data):** Ghi tại `data/raw/`
  - `data/raw/usdt_whale_transfers_raw.csv` (5.0 MB)
  - `data/raw/usdt_whale_transfers_raw.parquet` (185 KB)
- **Dữ liệu chuẩn hóa (Interim Data):** Ghi tại `data/interim/`
  - `data/interim/usdt_whale_transfers_interim.csv` (5.7 MB)
  - `data/interim/usdt_whale_transfers_interim.parquet` (213 KB)
  - *Chuẩn hóa thực hiện:* Chuyển đổi amount thực tế qua decimals, đưa địa chỉ ví về lowercase, chuẩn hóa timestamp UTC, trích xuất `tx_date`, `tx_hour`, khử trùng lặp và sắp xếp theo chuỗi thời gian.
- **Thống kê dữ liệu thu thập được:**
  - Tổng số giao dịch cá voi: **20.000** transfers.
  - Tổng khối lượng luân chuyển: **73,097,261,814.11 USDT** (~73 tỷ USD).
  - Số địa chỉ gửi duy nhất (Senders): **315** addresses.
  - Số địa chỉ nhận duy nhất (Receivers): **303** addresses.

