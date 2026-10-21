# T12 — Rà soát công khai địa chỉ top thường xuyên

Ngày rà soát: 21/10/2026. Chọn 20 địa chỉ có nhiều ngày ở top 10 nhất cho từng
bản raw/log, hòa thì địa chỉ tăng dần. Hợp hai tập có 22 địa chỉ.

Đây là desk review công khai bởi trợ lý. Mỗi địa chỉ được tìm theo địa chỉ đầy
đủ và đối chiếu nguồn truy xuất. Nguồn search_index là nội dung được công cụ
tìm kiếm lập chỉ mục, không giả vờ đã mở được trang trực tiếp; một số trang
bị chặn hoặc không kết luận được. Nhãn tổ chức là bằng chứng rà soát hiện tại,
chưa xác nhận quyền sở hữu xuyên suốt lịch sử. Gợi ý khác chain không chuyển
thành nhãn Ethereum; chưa xác định không đồng nghĩa cá nhân hoặc bot.

**Tất cả 22 bản ghi đang pending_human_review.** Các tên và nội dung nguồn bên
dưới là kết quả AI tra cứu chưa được thành viên kiểm chứng, không phải nhãn
T07 đã xác minh; không tham gia bộ lọc T12 hoặc coverage định danh. Hàng chờ
dùng chung ở T07: t07_label_review_candidates.parquet. Chỉ quyết định có người
xác minh, source_url, confidence và thời điểm khả dụng mới được nhập vào
t07_secondary_verified_labels.parquet dưới source_tier=2.

Thứ tự dưới đây theo xếp hạng số ngày top 10 raw, rồi các địa chỉ chỉ thuộc
top 20 của bản log. Net/gross tính từ dòng vào–ra quan sát được, không phải
số dư; ngày gắn cờ dùng ngưỡng prototype 5% và max(20, phân vị 95%).

## 0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4

Unverified AI candidate: **Binance deposit**. Category: exchange_tag.

Raw/log selection rank: 1/1; top-10 days: 506/534; longest streak: 104/88 days.

Net/gross full period: 0.0041438607; large-edge transaction count: 38,129; forwarding-candidate days: 530.

[Source for a team member to verify](https://etherscan.io/address/0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4?age=24H) (search_index, 2026-10-21). Explorer page title attributes a Binance deposit; direct page returned 403.

## 0x18e296053cbdf986196903e889b7dca7a73882f6

Unverified AI candidate: **Bybit**. Category: exchange_primary_document.

Raw/log selection rank: 2/2; top-10 days: 454/461; longest streak: 191/191 days.

Net/gross full period: 0.035231012; large-edge transaction count: 36,742; forwarding-candidate days: 59.

[Source for a team member to verify](https://www.bybit.com/common-static/cht-static/por/Bybit_PoR_Audit_2025_Jun_19.pdf#page=14) (primary_pdf, 2026-10-21). Address listed among Ethereum reserves on printed page 13; audit 2025-06-19, report 2025-06-27.

## 0xaa8ba7d4611437141192e7ceced531bc0a133efb

Unverified AI candidate: **Kraken 5**. Category: exchange_tag.

Raw/log selection rank: 3/3; top-10 days: 379/383; longest streak: 59/59 days.

Net/gross full period: 0.036252043; large-edge transaction count: 34,660; forwarding-candidate days: 76.

[Source for a team member to verify](https://ethereum.routescan.io/address/0xaA8ba7D4611437141192e7ceCed531Bc0A133efb/nft-transfers) (search_index, 2026-10-21). Explorer explicitly labels Kraken 5 / hot wallet.

## 0x14681e4e26f1b5b5774ae3b7f694ff08bbbeb65c

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: 4/4; top-10 days: 360/326; longest streak: 42/22 days.

Net/gross full period: 2.4084993e-11; large-edge transaction count: 17,091; forwarding-candidate days: 332.

[Source for a team member to verify](https://usdt.tokenview.io/en/address/0x14681e4e26f1b5b5774ae3b7f694ff08bbbeb65c) (search_index, 2026-10-21). Address/transfer records found; no defensible economic identity established.

## 0xed0c6079229e2d407672a117c22b62064f4a4312

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: 5/5; top-10 days: 252/251; longest streak: 18/14 days.

Net/gross full period: 0.00010823314; large-edge transaction count: 8,052; forwarding-candidate days: 149.

[Source for a team member to verify](https://etherscan.io/address/0xEd0C6079229E2d407672a117c22b62064f4a4312) (search_index, 2026-10-21). DeFi token/debt positions are visible, but holdings do not identify a person or institution.

## 0x549d835356d92983abb76e4cae639f7857963425

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: 6/6; top-10 days: 218/250; longest streak: 11/11 days.

Net/gross full period: 0.0040393422; large-edge transaction count: 13,416; forwarding-candidate days: 195.

[Source for a team member to verify](https://etherscan.io/address/0x549d835356d92983abb76e4cae639f7857963425) (search_index, 2026-10-21). Many token transfers/counterparties; no identity inferred from exchange interactions.

## 0xc333e80ef2dec2805f239e3f1e810612d294f771

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: 7/7; top-10 days: 191/226; longest streak: 13/13 days.

Net/gross full period: 0.0069232855; large-edge transaction count: 15,302; forwarding-candidate days: 225.

[Source for a team member to verify](https://www.blockchain.com/eth/address/0xc333e80ef2dec2805f239e3f1e810612d294f771) (search_index, 2026-10-21). Ethereum address record found; Etherscan direct lookup blocked; no identity conclusion.

## 0xb99a2c4c1c4f1fc27150681b740396f6ce1cbcf5

Unverified AI candidate: **Abraxas Capital Management / Heka Funds**. Category: fund_tag.

Raw/log selection rank: 8/8; top-10 days: 180/184; longest streak: 7/10 days.

Net/gross full period: 6.5130765e-05; large-edge transaction count: 5,015; forwarding-candidate days: 57.

[Source for a team member to verify](https://blockscan.com/Address/0xb99a2c4c1c4f1fc27150681b740396f6ce1cbcf5) (direct_page, 2026-10-21). Blockscan entity label links to the asset manager; this is institutional labeling, not an individual.

## 0x6aea888bcf4fd52213e9d03e7c69a45d98b35065

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: 9/11; top-10 days: 131/121; longest streak: 7/7 days.

Net/gross full period: 5.7820811e-06; large-edge transaction count: 2,130; forwarding-candidate days: 11.

[Source for a team member to verify](https://etherscan.io/address/0x6aea888bcf4fd52213e9d03e7c69a45d98b35065) (search_index, 2026-10-21). Exchange transfers alone do not establish ownership or intermediary status.

## 0xef686ec84eea2eae6f59cbc704d05b939f8fb385

Unverified AI candidate: **HTX-associated explorer icon**. Category: exchange_hint.

Raw/log selection rank: 10/12; top-10 days: 113/115; longest streak: 6/6 days.

Net/gross full period: 1.1810682e-05; large-edge transaction count: 5,527; forwarding-candidate days: 88.

[Source for a team member to verify](https://etherscan.io/address/0xef686ec84eea2eae6f59cbc704d05b939f8fb385) (search_index, 2026-10-21). HTX icon on address in transaction rows; weaker hint than an explicit reserve record.

## 0xf8191d98ae98d2f7abdfb63a9b0b812b93c873aa

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: 11/9; top-10 days: 108/138; longest streak: 4/4 days.

Net/gross full period: 0.0065718961; large-edge transaction count: 9,914; forwarding-candidate days: 243.

[Source for a team member to verify](https://eth.tokenview.io/cn/address/0xf8191d98ae98d2f7abdfb63a9b0b812b93c873aa) (search_index, 2026-10-21). Active address found; no defensible Ethereum economic identity established.

## 0x0b2fdf416cf2951499de9a1adac65c8e9907c8c2

Unverified AI candidate: **Binance deposit**. Category: exchange_tag.

Raw/log selection rank: 12/-; top-10 days: 105/68; longest streak: 5/4 days.

Net/gross full period: 0.01619327; large-edge transaction count: 14,395; forwarding-candidate days: 239.

[Source for a team member to verify](https://etherscan.io/address/0x0b2fdf416cf2951499de9a1adac65c8e9907c8c2?age=30D) (search_index, 2026-10-21). Explorer explicitly identifies Binance deposit address.

## 0x17dc4d78e8abca9408c43541beb3c8215655403a

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: 13/19; top-10 days: 104/72; longest streak: 8/6 days.

Net/gross full period: 0; large-edge transaction count: 2,114; forwarding-candidate days: 12.

[Source for a team member to verify](https://etherscan.io/address/0x17dc4d78e8abca9408c43541beb3c8215655403a) (search_index, 2026-10-21). Address page found without defensible entity label in retrieved content.

## 0xad6eaa735d9df3d7696fd03984379dae02ed8862

Unverified AI candidate: **Cumberland**. Category: fund_tag.

Raw/log selection rank: 14/14; top-10 days: 88/108; longest streak: 3/5 days.

Net/gross full period: 0.0009450781; large-edge transaction count: 6,653; forwarding-candidate days: 114.

[Source for a team member to verify](https://blockscan.com/Address/0xad6eaa735d9df3d7696fd03984379dae02ed8862) (search_index, 2026-10-21). Blockscan labels Cumberland / Fund; Etherscan COMP holder page corroborates same label.

## 0x05d9617595e69ff577076355abc5e7c51ed0bdf3

Unverified AI candidate: **OKX 191**. Category: exchange_tag.

Raw/log selection rank: 15/17; top-10 days: 87/86; longest streak: 12/10 days.

Net/gross full period: 0.0069719127; large-edge transaction count: 7,370; forwarding-candidate days: 53.

[Source for a team member to verify](https://etherscan.io/address/0x05d9617595e69ff577076355abc5e7c51ed0bdf3) (search_index, 2026-10-21). Explorer page title labels OKX 191.

## 0xa3c9204c856ba6c5c56e32bfc44b4c8203fea930

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: 16/16; top-10 days: 86/89; longest streak: 17/20 days.

Net/gross full period: 0.00054481413; large-edge transaction count: 5,882; forwarding-candidate days: 109.

[Source for a team member to verify](https://blockscan.com/Address/0xa3c9204c856ba6c5c56e32bfc44b4c8203fea930) (lookup_inconclusive, 2026-10-21). Exact-address search did not establish identity; direct explorer lookup inaccessible.

## 0xa29e963992597b21bcdcaa969d571984869c4ff5

Unverified AI candidate: **B2C2 (document attribution)**. Category: institution_document_hint.

Raw/log selection rank: 17/10; top-10 days: 80/123; longest streak: 4/5 days.

Net/gross full period: 0.0081420765; large-edge transaction count: 11,789; forwarding-candidate days: 181.

[Source for a team member to verify](https://ecf.flmd.uscourts.gov/cgi-bin/show_public_doc?2024-00809-56-6-cv=) (search_index, 2026-10-21). Public court exhibit groups address under B2C2; not an adjudication of ownership or wrongdoing.

## 0x11dbf181dd5c075c2abd92cb9579c4809406b5be

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: 18/15; top-10 days: 79/89; longest streak: 7/7 days.

Net/gross full period: 0.0058576237; large-edge transaction count: 4,739; forwarding-candidate days: 86.

[Source for a team member to verify](https://etherscan.io/address/0x11dbf181dd5c075c2abd92cb9579c4809406b5be) (search_index, 2026-10-21). Transfers and fee-recipient record do not by themselves establish economic owner or bot status.

## 0x8f0ee0393eae7fc1638bd7860a3fec6a663786ae

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: 19/18; top-10 days: 77/77; longest streak: 14/14 days.

Net/gross full period: 2.7135297e-11; large-edge transaction count: 8,614; forwarding-candidate days: 80.

[Source for a team member to verify](https://blockscan.com/Address/0x8f0ee0393eae7fc1638bd7860a3fec6a663786ae) (lookup_inconclusive, 2026-10-21). No defensible attribution from exact-address lookup; direct lookup inaccessible.

## 0x3a3c006053a9b40286b9951a11be4c5808c11dc8

Unverified AI candidate: **Ceffu custody hot wallet 1**. Category: custody_tag.

Raw/log selection rank: 20/-; top-10 days: 76/51; longest streak: 4/4 days.

Net/gross full period: 0.0013648604; large-edge transaction count: 2,189; forwarding-candidate days: 1.

[Source for a team member to verify](https://routescan.io/address/0x3a3C006053a9B40286B9951A11bE4C5808c11dc8/multichain-portfolio) (search_index, 2026-10-21). Explorer explicitly labels Ceffu custody hot wallet.

## 0xcd531ae9efcce479654c4926dec5f6209531ca7b

Unverified AI candidate: **Coinbase Prime 1 (Monad only)**. Category: cross_chain_hint.

Raw/log selection rank: -/13; top-10 days: 72/111; longest streak: 5/5 days.

Net/gross full period: 0.01550376; large-edge transaction count: 9,493; forwarding-candidate days: 174.

[Source for a team member to verify](https://monadscan.com/address/0xcd531ae9efcce479654c4926dec5f6209531ca7b) (search_index, 2026-10-21). Label observed on Monad; do not automatically transfer that attribution to Ethereum.

## 0x65c340eb0688d8f8b64e9c6d580f312a97b615d8

Unverified AI candidate: **Unresolved**. Category: unresolved.

Raw/log selection rank: -/20; top-10 days: 71/72; longest streak: 5/4 days.

Net/gross full period: 6.1666981e-05; large-edge transaction count: 10,993; forwarding-candidate days: 222.

[Source for a team member to verify](https://blockscan.com/Address/0x65c340eb0688d8f8b64e9c6d580f312a97b615d8) (lookup_inconclusive, 2026-10-21). No defensible attribution from exact-address lookup; direct lookup inaccessible.
