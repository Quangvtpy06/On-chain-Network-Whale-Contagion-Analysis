# T08 — Báo cáo chạy lại và nghiệm thu

**Trạng thái:** Đủ điều kiện sử dụng.

Đầu vào gốc: `data/interim/usdt_whale_transfers_interim.parquet`; file gốc được giữ nguyên, đối soát bằng SHA-256.
Netted: **2,113,146 → 1,878,332 dòng**; volume **9,685,105,185,709.98 → 5,841,719,933,212.04 USDT**.
Giữ lại 60.3165% volume; loại 298 self-loop.

Daily: **655 snapshot**, **998,663 cạnh**; volume ngày cao nhất **33,943,665,167.71 USDT**.
Weekly: **94 snapshot**, **633,921 cạnh**; **92 tuần đủ ngày** dùng cho hồi quy.
Reciprocity trung bình ngày: raw=0.14324603, netted=0.12388858.

| Kiểm tra | Kết quả | Ghi nhận |
|---|---|---|
| B.1 | PASS | Daily + full-period volume conserved. Edge tx-count versus global unique tx-count comparison omitted per user instruction. |
| B.2 | PASS | All weekly edge keys and values checked; max positive diff=4.76837158203125e-07 |
| B.3 | PASS | 655 daily snapshots, including empty windows |
| B.4 | PASS | Raw UTC day mismatches=0; windows recomputed from timestamp |
| B.5 | PASS | Raw duplicate keys=0; invalid/nonlowercase addresses=0; raw self-loops=298; raw zero-address rows=1; label coverage=True; contract status complete=True |
| B.6 | PASS | 5 deterministic random raw transactions checked against netted directions and daily edge membership |
| B.7 | PASS | Top10 node share=24.988459%; measured explanations + full cycle audit exported; team decision needed=False |
| B.8 | PASS | Density, reciprocity, SCC, WCC compared on all daily/weekly windows; numerical decrease is measured, not assumed |
| B.9 | PASS | Two raw-to-graph executions: 11 artifact hashes match=True; independent review exit=0 |

B.1 bỏ đối chiếu tổng transaction_count cạnh với unique transaction toàn ngày theo yêu cầu người dùng.
B.7: xem top 10 ngày (kèm các tác nhân đo được), top 20 nút và audit chu trình trong thư mục kết quả. Không khẳng định nguyên nhân kinh tế khi chưa có bằng chứng.
Review độc lập được thực hiện bằng chương trình riêng không import hàm production; đây là kiểm tra tính toán, không thay chữ ký reviewer của nhóm.
Nếu B.7 cần quyết định: nhóm phải phê duyệt chính sách loại chu trình nhiều bước trước T09–T12.

Tái lập: chạy `python T08_Dynamic_Transaction_Graph.py` tại thư mục crypto. Mặc định chạy hai lần và review độc lập.
Các hash kết quả nằm trong `data/processed/graphs/t08_reproducibility.json`.
