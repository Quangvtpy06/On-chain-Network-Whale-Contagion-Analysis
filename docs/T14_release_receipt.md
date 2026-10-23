# T14 — receipt phát hành GitHub và HF

Ngày 24/10/2026. Đã hoàn tất phát hành theo chỉ thị của người dùng.

- Source/config đã kiểm định trên GitHub: `0c5e2685baff4d78ad4f0bde422d2823d3aca01e`.
- HF dataset: `team-crypto/Market-data-crypto-project`.
- Revision output: `87bfe944925467fa74083ec0377c6b2579692bf0`.
- Revision các input trực tiếp đã kiểm định: `de42b5dc4e5c3d63161b38ad4f528d97c47f5068`.
- Root manifest: `data/hf_t14_release_manifest.json`; SHA-256 `526029f91a32c30c570aece2a151b94e14ed83bb6bf98d40454aac3a05e9a57e`.
- 12 file được thay/thêm và tải lại kiểm chứng: 10 artifact T14 (6 Parquet + 4 JSON), config/t14.yaml và root manifest. Bytes của cả 12 file khớp local. Không xóa file từ xa, không ghi đè dữ liệu nguồn chung.

[Source GitHub](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/commit/0c5e2685baff4d78ad4f0bde422d2823d3aca01e)

[Output HF](https://huggingface.co/datasets/team-crypto/Market-data-crypto-project/tree/87bfe944925467fa74083ec0377c6b2579692bf0/data/processed/t14)

[Root manifest HF](https://huggingface.co/datasets/team-crypto/Market-data-crypto-project/blob/87bfe944925467fa74083ec0377c6b2579692bf0/data/hf_t14_release_manifest.json)

## Khi team tải về

Lấy code theo code_git_commit trong root manifest; output và config theo revision output trên.
Các input được lấy theo revision trong từng remote_dependency, giữ đúng path và SHA-256. Cần giữ đầy đủ
các artifact T07/T12/graph đã bàn giao trước đó vì validator xác thực cả gate upstream và các dependency
được gate đó tham chiếu.

Đặc biệt, market daily đã dùng kiểm định có hash 540b408c... tại de42b5dc..., khác bản latest 1682966f...
về serialization/rounding. Không mặc định tải latest cho input này; không thay input để khớp một output khác.
File phút gộp có hash 46816308... và không bị thay trong lần phát hành này.

Sau khi lấy đúng các phiên bản, chạy `python scripts/validate_t14_release.py`. Hai cờ input-ready đều true
trong scope CEX approved và activity cohort research-knowledge; các cờ RQ3 upstream vẫn false và không bị sửa.
Đây không phải chứng nhận nhà đầu tư cá nhân hoặc kết luận RQ3. T15/T16 tiếp tục dùng gate, eligibility và
predictor_sets đúng nhánh.

Các manifest ghi upload_performed=false ở thời điểm chuẩn bị; chúng không tự sửa sau upload để tránh thay
hash. Receipt này và commit HF ở trên là bằng chứng việc upload thực tế đã hoàn tất.

So với snapshot HF cũ 8163ab90..., gói mới thay RV/HAR/target xuất phát từ chuỗi phút nội suy bằng các giá trị
đã đối chiếu với nến phút T06 thật. Ngày 02/01/2025: RV=0,0006503000899874552.
Xem báo cáo đối chiếu lịch sử và completion report để biết chi tiết kiểm định.