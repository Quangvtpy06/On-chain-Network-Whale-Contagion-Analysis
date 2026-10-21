# Quy ước dự án crypto

- Bảng dữ liệu đầu ra dùng Parquet. CSV duy nhất được giữ là
  `eth_stats_from_2025.csv` tại gốc dự án; không tạo CSV mới.
- Sau khi kiểm tra thành công, xóa mã test dữ liệu giả, dữ liệu test tạm và bản
  chạy đối chiếu dư. Quy tắc áp dụng cả các bước trước. Đặt mọi dữ liệu tạm dưới
  `.cache/`, không dưới `data/processed/`.
- Theo yêu cầu bàn giao mới nhất, xóa cả mã pytest trong `tests/` sau khi đạt.
  Giữ kết quả kiểm tra lịch sử, hash và kiểm định dữ liệu thật; không trình bày
  các ca giả đã xóa như thể vừa chạy lại trong các lần nghiệm thu sau.
- Giữ kiểm định dữ liệu thật mà pipeline gọi khi chạy và bằng chứng nghiệm thu
  Parquet/JSON để các lần chạy sau vẫn kiểm tra được chất lượng và tái lập.
- Dữ liệu chính thức dùng chung trên Hugging Face theo cấu trúc đường dẫn dự
  án. Tạo lại `data/hf_release_manifest.json` sau khi nghiệm thu; không upload
  cache, test hoặc đầu ra chưa đạt. Việc tính/kiểm tra không tự upload.
- Đường dẫn cấu hình và báo cáo phải tương đối với gốc dự án. Giữ nguyên dữ
  liệu nguồn; T09–T12 chỉ dùng đúng T08 đã nghiệm thu và xác minh hash.
