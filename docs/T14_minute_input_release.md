# Phát hành đầu vào phút gộp cho T14

Đã phát hành file mà `config/t14.yaml` của commit `1774a71dd35265fc6b524fff75e3471ddca33136` yêu cầu.

- Dataset: `team-crypto/Market-data-crypto-project`.
- Revision phát hành: `de42b5dc4e5c3d63161b38ad4f528d97c47f5068`.
- File: `market/processed/ohlcv_1m/ETHUSDT_1m_2025-2026.parquet`.
- Manifest: `market/processed/ohlcv_1m/ETHUSDT_1m_2025-2026.manifest.json`.
- 943.200 dòng = 655 ngày × 1.440 phút; hai cột `datetime_utc`, `close`; 10.686.151 bytes.
- SHA-256: `46816308ad14b7491255150bd1bc484c6f54f2d4dca7a25a065f3767dabbb524`.

Nguồn là 655 file ngày T06 tại revision `5cd5603bd8493e60c6adabb96200266769929c40`. Mỗi file được kiểm tra hash, lịch UTC đầy đủ, giá hữu hạn/dương; timestamp minute/index được chuyển tên sang datetime_utc, ghép theo lịch. Không resample, fill, round hoặc thay giá close. Bản gộp khớp byte SHA-256 với đầu vào của lần kiểm định T14 đã có 64 dòng validation PASS và 5 bảng tái tính khớp hash.

Sau upload đã tải lại cả Parquet và manifest: khớp toàn bộ bytes; Parquet đọc được, đủ dòng/cột và không trùng timestamp. 655 file nguồn hiện tại trên HF được xác minh không đổi. Không xóa nguồn, không thay output T14 khác và không sửa bất kỳ cờ readiness nào.

Khi tải cho T14, giữ đúng đường dẫn tương đối trên. Khi dùng dữ liệu ngày cho T06/T13, tiếp tục lấy đúng tên theo YYYY-MM-DD; không gộp lại cả file tổng như một ngày bổ sung.

Phần còn lại về readiness được đề xuất trong [T14_readiness_contract_proposal.md](T14_readiness_contract_proposal.md). Đề xuất chưa thay đổi code gate T14. T15/T16 vẫn là bước trực tiếp trả lời RQ3.