# T07 — Hoàn thiện nhãn và trạng thái contract

Chạy `T07_Complete_Wallet_Labels.py` sau bước public enrichment. File đầu ra chuẩn
đọc từ `processed_labels_parquet` trong config, chứa tất cả địa chỉ và không bỏ Unknown.

Trạng thái contract lấy độc lập từ BigQuery contracts (bản ghi tạo trước mốc kết thúc).
Có cache theo toàn bộ tập địa chỉ và mốc thời gian, truy vấn dry-run trước và giới hạn
scan trong config. Không ghi key hay nội dung service-account vào kết quả.
Không suy is_contract từ tên hoặc entity_type; lỗi truy vấn để null và complete=False.

Kết quả chạy được lưu ở `data/processed/t07/t07_complete_summary.json`, gồm độ phủ,
số contract, số địa chỉ chưa xác minh và số thực thể đã có nhãn có bằng chứng.
Unknown không có nghĩa là EOA; Contract không phải danh tính tổ chức. Các nhóm nhãn
không có bằng chứng vẫn có thể rỗng, không tự tạo nhãn để lấp đủ danh mục.

Nguồn bảng: `bigquery-public-data.crypto_ethereum.contracts`.
Cơ chế dry run và giới hạn scan theo tài liệu chính thức Google Cloud:
https://docs.cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.job.QueryJobConfig
