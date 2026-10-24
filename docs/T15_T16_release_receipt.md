# Biên nhận phát hành T15/T16 — 25/10/2026

Code nghiệm thu đã push trực tiếp lên **main**, commit [f334ff5](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/commit/f334ff5d3c9d9003878505bfb1abd52cefe38b11). Nhánh `feature/t15-t16-analysis` giữ bản cũ, không dùng để chạy bản đã sửa.

Output được phát hành lên dataset `team-crypto/Market-data-crypto-project`, revision `d3cc595be2d452467e823596749a63723dfa2e1d`:

- [Output T15](https://huggingface.co/datasets/team-crypto/Market-data-crypto-project/tree/d3cc595be2d452467e823596749a63723dfa2e1d/data/processed/t15).
- [Output T16](https://huggingface.co/datasets/team-crypto/Market-data-crypto-project/tree/d3cc595be2d452467e823596749a63723dfa2e1d/data/processed/t16).
- [Manifest đúng phiên bản](https://huggingface.co/datasets/team-crypto/Market-data-crypto-project/blob/d3cc595be2d452467e823596749a63723dfa2e1d/data/hf_t15_t16_release_manifest.json).

Gói gồm 22 artifact/config và manifest, tổng **23 file**. Sau upload đã xác minh hash remote, rồi tải lại từng file qua HTTPS: **23/23 SHA-256 khớp local**, cả **9 bảng Parquet** đọc được bằng PyArrow. Không tạo CSV, không upload test/cache và không xóa file remote. T11/T14 được ràng buộc theo revision đầu vào `87bfe944925467fa74083ec0377c6b2579692bf0`; không thay các dữ liệu upstream đó.

Phạm vi nghiệm thu: hồi quy flow trong mẫu và phản ứng mô tả quanh sự kiện; không chứng nhận causal effect, khả năng dự báo ngoài mẫu hoặc nhà đầu tư cá nhân. Kiểm định trước phát hành: 15 bài kiểm tra PASS, 18 file khớp giữa hai tiến trình và validator dữ liệu thật PASS. Hồ sơ kiểm tra local ghi trạng thái tại thời điểm kiểm tra; biên nhận này ghi trạng thái phát hành sau đó.

Chi tiết SHA-256 và kết quả tải lại nằm trong [T15_T16_release_receipt.json](T15_T16_release_receipt.json). Chỉ bổ sung tài liệu biên nhận sau commit code, không thay source/config đã ràng buộc trong summary.
