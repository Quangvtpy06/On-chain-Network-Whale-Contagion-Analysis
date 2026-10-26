# Giai đoạn 4 — T19 đến T23 (Graph ML & anomaly)

Ngày nghiệm thu local: 27/10/2026. Chuỗi thống nhất từ feature/split đóng băng (T19) qua phân loại bắt buộc (T20–T22, RQ5) đến phần mở rộng bất thường chuỗi (T23).

## Phạm vi đã khóa

- Token/mạng: transfer USDT ≥ 500.000; graph tuần ISO từ T08.
- T19 `t19_v1`: 41 predictor, nhãn CEX/DEX hồi cứu T07, split 54/18/18 tuần + 1 tuần gap; `pit_label_forecast=false`.
- T20–T22 `graph_ml_stage4_v1`: cùng mẫu, macro F1, chọn GNN chỉ bằng validation.
- T23 `t23_temporal_graph_anomaly_v1`: chỉ mở sau gate T20–T22; stress T13 không vào mô hình.

Hợp đồng nguồn T19: kiểm tra SHA byte của từng Parquet với summary **của bản T19 đang đọc**, rồi ràng buộc T20–T23 bằng hash nội dung (tên cột + giá trị). Bản HF revision `25becf91d38a38ef7998d26b3b148e4109ef1f05` và bản pandas 2.2.3 local có thể khác byte Parquet nhưng cùng nội dung bảng vẫn được chấp nhận.

## Kết quả số học (không đổi giữa các lượt tái lập)

| Mô hình | Macro F1 val | Macro F1 test | Macro F1 test ví mới |
|---|---:|---:|---:|
| Tabular MLP | 0,834920 | 0,696718 | 0,602412 |
| Tabular + Node2Vec MLP | 0,989082 | 0,998506 | 1,000000 |
| GCN | 0,942840 | 0,796687 | 0,726815 |
| GraphSAGE | 0,967023 | 0,826479 | 0,677398 |
| GAT | 0,936213 | 0,851192 | 0,653743 |

Test: 2.199 hàng / 248 địa chỉ (2.017 CEX, 182 DEX); ví mới 57 địa chỉ / 259 hàng, **6 DEX**. GraphSAGE được chọn bằng validation; delta vs tabular MLP trên test **+0,129761**. CI bootstrap cụm địa chỉ **[0,068828; 0,202705]**; độ nhạy khối 3 tuần **[0,081208; 0,178851]**. Node2Vec cao hơn mọi GNN nhưng dễ phản ánh dấu vết thực thể trên nhãn hồi cứu lặp theo thời gian — không tuyên bố khái quát rộng.

T23 (GraphSAGE): 17 tuần test scoreable, **1** tuần bất thường, **0** trùng stress cùng tuần.

## Gate nghiệm thu

| Bước | Kết quả |
|---|---|
| Validator bắt buộc T20–T22 | **112/112 PASS** |
| Validator mở rộng T23 | **567/567 PASS** |
| Tái lập artifact T20–T22 (seed 73/137 trước đó) | 17/17 trùng SHA-256 |
| Tái lập cuối T20–T23 với `PYTHONHASHSEED=211` | **18/18** artifact output trùng baseline |
| Môi trường pin | `requirements-stage4.txt` (torch 2.14.1+cpu, PyG 2.8.1, sklearn 1.9.1, gensim 4.4.0, pandas 2.2.3) |

## Giới hạn giai đoạn (bắt buộc ghi trong báo cáo học thuật)

Đây là phân loại CEX/DEX hồi cứu và phát hiện lệch cấu trúc mạng trong mẫu USDT đã lọc — không phải dự báo nhãn point-in-time, không nhận diện cá voi cá nhân, không chứng minh GNN luôn tốt nhất (Node2Vec+MLP cao hơn trên mẫu này), và T23 chưa phải tín hiệu dự báo stress. RQ5 được trả lời trong phạm vi: GNN được chọn (GraphSAGE) tốt hơn tabular MLP trên test với CI dương; bảng đủ năm mô hình vẫn phải trình bày.

## Bàn giao

- Config: `config/graph_ml_stage4.yaml`, `config/t23.yaml`
- Code: `T19_Graph_ML_Features.py`, `T20_Tabular_Node2Vec.py`, `T21_GCN_GraphSAGE.py`, `T22_GAT_RQ5_Comparison.py`, `T23_Temporal_Graph_Anomaly.py`, `src/stage4_common.py`, `src/stage4_gnn.py`
- Validator: `scripts/validate_stage4_mandatory.py`, `scripts/validate_t23_extension.py`
- Đặc tả/báo cáo: `docs/T19_graph_ml_features_specification.md`, `docs/T20_T22_graph_ml_specification.md`, `docs/T20_T22_completion_report.md`, `docs/T23_temporal_anomaly_specification.md`, `docs/T23_completion_report.md`
- Bằng chứng hash: `docs/stage4_acceptance_evidence.json`
- Output: `data/processed/t19` … `t23` (chỉ Parquet + JSON/PNG báo cáo)

Chưa upload GitHub/HF cho gói T20–T23. File chạy tạm trong `.cache/stage4_final_repro/` đã xóa sau khi ghi bằng chứng.
