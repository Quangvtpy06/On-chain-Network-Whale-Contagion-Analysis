# T04: Báo Cáo Lựa Chọn Dữ Liệu & Chiến Lược Lấy Mẫu (Sampling Strategy)
**Dự án:** On-chain Network Whale Contagion Analysis (Phân tích Lan truyền Rủi ro Cá voi trên Mạng On-chain)  
**Phụ trách:** TV1 - Yến Vy (Reviewer: TV4)  
**Mã Task:** T04  

---

## 1. Lựa chọn Token ERC-20
Dự án tập trung vào phân tích mạng lưới lây lan / tác động của cá voi (Whale Contagion Analysis). Để đạt hiệu quả mô hình hóa đồ thị (Graph/Network Analysis) và độ tin cậy thực tế, chúng tôi chọn:

- **Token lựa chọn:** **USDT (Tether USD)** hoặc **UNI (Uniswap)** / **WBTC / SHIB**
  - *Lựa chọn chính:* **USDT (Tether USD)**
  - *Contract Address:* `0xdac17f958d2ee523a2206206994597c13d831ec7`
  - *Decimals:* 6
  - *Lý do chọn:* 
    1. USDT là stablecoin có khối lượng giao dịch lớn nhất và mật độ tương tác giữa các cá voi (Whales), các sàn giao dịch (CEXs/DEXs), quỹ đầu tư và người dùng cá nhân cực kỳ cao.
    2. Các dòng tiền lớn từ cá voi USDT phản ánh trực tiếp hành vi rút/nạp, chốt lời hoặc thanh lý tài sản khi thị trường biến động, rất lý tưởng để nghiên cứu mô hình lây lan (Contagion/Diffusion Model).

---

## 2. Khoảng thời gian (Time Window)
- **Mốc thời gian:** Từ `2025-01-01` đến nay (`2026-10-18`) (~22 tháng).
- **Lý do:**
  - Đảm bảo đủ dài (>12-24 tháng) để quan sát các chu kỳ biến động lớn và sự thay đổi cấu trúc đồ thị mạng lưới.
  - Phù hợp với mốc dữ liệu mà nhóm đã thống nhất và tối ưu được quota BigQuery Sandbox (1TB/tháng).

---

## 3. Chiến lược Lấy Mẫu (Sampling Strategy)
Bảng `bigquery-public-data.crypto_ethereum.token_transfers` chứa hàng tỷ bản ghi. Để phân tích lây lan của cá voi (Whale Contagion), việc tải toàn bộ là không khả thi và gây nhiễu lớn bởi các giao dịch micro/bot nhỏ.

Nhóm lựa chọn phương pháp **Top Addresses & Ego-Network Sampling (Lấy mẫu theo Ego-network của Cá voi)**:

### 3.1. Định nghĩa Cá Voi (Whale Identification)
- Lọc các địa chỉ ví thực hiện các giao dịch chuyển token giá trị cực lớn (ví dụ: chuyển từ 500.000 USDT đến 1.000.000+ USDT trong 1 giao dịch) hoặc lọt vào **Top 100 - 500 ví có volume/số dư lớn nhất**.

### 3.2. Ego-Network Sampling (Đồ thị mạng con 1-hop / 2-hop)
- **Seed Nodes (Ego):** Danh sách Top cá voi được chọn làm các nút hạt giống.
- **Transfers (Edges):** Trích xuất toàn bộ các giao dịch chuyển token mà `from_address` HOẶC `to_address` thuộc danh sách Whale Seeds trong khung thời gian chỉ định (1-hop ego network).
- **Lý do lựa chọn chiến lược này:**
  1. Tập trung tối đa vào luồng lây lan bắt nguồn hoặc hướng về các thực thể trọng yếu (Whales).
  2. Giảm dung lượng dữ liệu từ hàng trăm GB xuống mức MBs/GBs mà vẫn giữ nguyên được cấu trúc liên kết và sự truyền tải rủi ro.
  3. Tiết kiệm tài nguyên BigQuery, tốc độ xử lý đồ thị (NetworkX/PyVis) nhanh hơn và có ý nghĩa thống kê cao hơn.

