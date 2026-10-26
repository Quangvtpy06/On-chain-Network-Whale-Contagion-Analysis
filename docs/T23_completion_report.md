# T23 — Phát hiện bất thường chuỗi graph tuần

**Trạng thái:** phần mở rộng sau gate T20–T22. Protocol `t23_temporal_graph_anomaly_v1`. Isolation Forest fit ngưỡng P95 chỉ trên 53 tuần train; chấm 17 tuần validation và 17 tuần test scoreable trên chuỗi 94 tuần. Tuần đầu sau gap không có embedding tuần liền trước nên không chấm được.

Mô hình chính GraphSAGE (đã chọn ở T22 bằng validation) gắn cờ **1 tuần test bất thường** (`2026-W40`); **0** tuần bất thường test trùng tuần có ngày stress T13. GCN không gắn cờ tuần test nào. Ba tuần train và một tuần validation của GraphSAGE vượt ngưỡng; đây là mô tả trong mẫu train/validation, không dùng để chọn ngưỡng.

| Kiểm định | Kết quả |
|---|---|
| Gate T20–T22 trước khi chạy | PASS (112/112) |
| Pipeline T23 | 6/6 PASS |
| Validator độc lập | **567/567 PASS** |
| Tái lập `PYTHONHASHSEED=211` vs baseline | **7/7 artifact trùng SHA-256** |

Giới hạn: đây là phát hiện thay đổi cấu trúc mạng / embedding tuần, chưa phải tín hiệu dự báo stress. Stress T13 là nhãn hồi cứu toàn kỳ; chồng lấp chỉ mang tính mô tả. Embedding lấy từ GNN đã fit trên nhãn CEX/DEX hồi cứu của giai đoạn bắt buộc, nên bất thường phản ánh lệch so với phân phối train của mạng USDT ≥ 500.000, không khái quát sang token khác hay toàn bộ Ethereum.

Code: `T23_Temporal_Graph_Anomaly.py`, `config/t23.yaml`, `scripts/validate_t23_extension.py`. Đặc tả: `docs/T23_temporal_anomaly_specification.md`. Output: `data/processed/t23/`.
