# T20–T22 — Graph ML bắt buộc và RQ5

**Trạng thái:** T20 (tabular MLP + Node2Vec), T21 (GCN + GraphSAGE) và T22 (GAT + so sánh) đã chạy và đạt kiểm định kỹ thuật trên bảng T19 tuần chính. Giao thức `graph_ml_stage4_v1` được ghi tại `config/graph_ml_stage4.yaml`; mọi mô hình dùng cùng 41 predictor, 54 tuần train, 18 tuần validation, 18 tuần test. Test có 2.199 hàng từ 248 địa chỉ (2.017 CEX, 182 DEX). Phần ví chưa thấy trong train chỉ có 57 địa chỉ/259 hàng, trong đó **6 DEX/6 hàng**.

| Mô hình | Macro F1 validation | Macro F1 test toàn bộ | Macro F1 test ví mới |
|---|---:|---:|---:|
| Tabular MLP | 0,834920 | 0,696718 | 0,602412 |
| Tabular + Node2Vec MLP | 0,989082 | 0,998506 | 1,000000 |
| GCN | 0,942840 | 0,796687 | 0,726815 |
| GraphSAGE | 0,967023 | 0,826479 | 0,677398 |
| GAT | 0,936213 | 0,851192 | 0,653743 |

Quy tắc cố định chọn **GraphSAGE** là GNN có macro F1 validation cao nhất; GAT tuy cao hơn trên test nhưng không được đổi lựa chọn theo test. So GraphSAGE với tabular MLP trên đúng hàng test: chênh lệch macro F1 **+0,129761**. Khoảng tin cậy 95% bootstrap theo cụm địa chỉ **[0,068828; 0,202705]**; độ nhạy khối 3 tuần **[0,081208; 0,178851]**. Trong phạm vi này, có bằng chứng GNN được chọn tốt hơn tabular MLP. Node2Vec + MLP lại có điểm cao hơn mọi GNN: kết luận không phải “GNN là mô hình tốt nhất”.

Kết quả Node2Vec gần hoàn hảo cần được đọc cùng thiết kế mẫu. Vector được học không giám sát từ graph train và giữ nguyên qua test; nhãn CEX/DEX của T07 là nhãn hồi cứu gắn cố định theo địa chỉ. Nhiều địa chỉ test đã xuất hiện trước đó, nên vector có thể hoạt động như dấu vết nhận diện thực thể. Nhóm ví DEX mới chỉ có 6 địa chỉ; điểm 1,0 của nhóm này **không chứng minh khả năng khái quát rộng**. Các phép bootstrap có thể không mô tả hết phụ thuộc mạng giữa các địa chỉ. Không dùng kết quả làm dự báo nhãn point-in-time, nhận diện cá voi cá nhân hoặc hiệu quả ngoài mạng USDT transfer từ 500.000 USDT.

Kiểm định: runner kiểm tra SHA byte T19 với summary local rồi ràng buộc bằng hash nội dung bảng; label và split không có trong 41 predictor; graph GNN chỉ nối trong cùng tuần; model fit train, chọn epoch validation. Validator riêng `scripts/validate_stage4_mandatory.py` đọc lại output và tính độc lập cùng mẫu, xác suất, macro F1, precision/recall/F1 từng lớp, số cửa sổ embedding, lựa chọn GNN và khoảng tin cậy: **112/112 PASS**. Hai tiến trình với `PYTHONHASHSEED=73/137` cho **17/17 artifact trùng SHA-256**; lượt cuối giai đoạn 4 với seed `211` vẫn khớp byte-for-byte. Không xuất CSV. Các bảng chính tại `data/processed/t20`, `t21`, `t22`; summary và independent review đi kèm. T23 chỉ được mở sau gate này. Xem biên bản giai đoạn: `docs/Stage4_T19_T23_completion_report.md`.
