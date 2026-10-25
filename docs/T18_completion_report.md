# Hoàn thành triển khai T18 riêng — 25/10/2026

Đã tạo `T18_Time_Split_Backtest.py`, `config/t18.yaml` và các module/validator riêng trên nền main hiện tại. Không dùng T15/T16 cũ ở nhánh T18 trước đó và không sửa pipeline T14/T15/T16 hoặc T17. Thông tin nghiệm thu cuối cùng và hash được giữ tại [T18_validation_evidence.json](T18_validation_evidence.json).

## Đã xử lý các điểm review

- Có runner thực thi, output Parquet và provenance, không chỉ báo cáo Markdown.
- Cố định cutoff cũ và fit_at rõ ràng; loại nhãn chưa khả dụng ở h=3/h=7 trước fit.
- Chạy cả hai nhánh activity cohort/CEX với baseline cùng mẫu; thêm HAR, train-mean và persistence benchmark khả dụng.
- Xuất từng dự báo, loss, train/test/purge ledger; giữ cả ngày dự báo chưa có outcome, không dùng chúng tính score.
- Ràng buộc đúng release T14/T15/T16, source và cả ba config; giữ policy research-knowledge và scope CEX quan sát được.
- T16 dùng đúng primary selection mới và loại cửa sổ qua biên train/test; báo thiếu mẫu, không tự hạ ngưỡng.
- Ghi rõ đây là pseudo-OOS hồi cứu vì test đã được xem trong các kết quả toàn mẫu trước đây.

## Kết quả trên dữ liệu hiện tại

Train feature date đến 08/06/2026; test từ 09/06; fit tại 10/06/2026 00:00 UTC. Hệ số cố định sau fit. Mỗi nhánh/horizon có 131 ngày dự báo; scoring chỉ dùng 130/128/124 ngày có outcome tương ứng h=1/3/7.

| Nhánh | h | Train sau purge | Ngày bị purge | RMSE controls | RMSE flow | Cải thiện SSE tương đối controls |
|---|---:|---:|---:|---:|---:|---:|
| Activity cohort | 1 | 464 | 0 | 0,709281 | 0,707961 | 0,3720% |
| Activity cohort | 3 | 462 | 2 | 0,841506 | 0,840728 | 0,1848% |
| Activity cohort | 7 | 458 | 6 | 0,761324 | 0,761032 | 0,0766% |
| CEX | 1 | 494 | 0 | 0,711596 | 0,709356 | 0,6285% |
| CEX | 3 | 492 | 2 | 0,840651 | 0,841468 | −0,1944% |
| CEX | 7 | 488 | 6 | 0,751551 | 0,751525 | 0,0068% |

Cải thiện trên mẫu nhỏ và không đồng nhất. Cả sáu CI block 95% của chênh lệch squared loss đều chứa zero; CI Bonferroni cũng vậy. **Chưa có bằng chứng mạnh rằng flow cải thiện dự báo so với controls trên giai đoạn này.** Đây không phải bằng chứng về việc hoàn toàn không có quan hệ, không phải causal effect và không chứng nhận nhà đầu tư cá nhân.

T16 primary: test có **0 activity-cohort flow, 0 CEX flow, 5 concentration, 3 large-transfer**. Một cửa sổ concentration 11/06 đi qua biên nên bị loại khỏi cả hai phần. Những nhóm test primary này đều không đủ n≥6 để báo CI theo protocol; chỉ giữ mô tả và trạng thái. Không thể tạo bằng chứng OOS event-flow bằng cách bỏ qua nhóm rỗng.

## Bàn giao

Kiểm định cuối: **76/76 kiểm tra pipeline PASS**, **17/17 bài test PASS**, **14/14 file khớp SHA-256** giữa hai tiến trình có `PYTHONHASHSEED=73/137`. Validator riêng với seed 211 PASS, gồm 7 kiểm tra độc lập theo mask thời điểm, OLS/predictions/loss và event partition. Timestamp UTC được chuẩn hóa ns; bài kiểm tra ghi/đọc Parquet giữ nguyên schema/hash đã PASS. Hai biểu đồ đã được xem kiểm tra.

Output được chạy mới tại `data/processed/t18`, kèm hai biểu đồ, report, summary và independent review. Đặc tả đầy đủ: [T18_specification.md](T18_specification.md). Validator dữ liệu thật được giữ; mã/bản chạy test tạm đã xóa sau nghiệm thu. Sau khi người dùng cho phép phát hành, code đã lên main tại `c1c3017`, output đã lên HF và tải lại xác minh **17/17 file khớp SHA-256**, 10 bảng Parquet đọc được. Xem [biên nhận và revision chính xác](T18_release_receipt.md).
