# Biên nhận phát hành T18 — 25/10/2026

Code T18 mới đã push trực tiếp lên **main**, commit [c1c3017](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/commit/c1c3017977c815afb181e871a88d944fc50d263d). Chạy entrypoint `T18_Time_Split_Backtest.py`; không dùng báo cáo/config T18 cũ từ nhánh `feature/t18-analysis`.

Gói dữ liệu được phát hành lên HF tại revision `3bfb61848e1ac9bcfb0809d3aef334d1885a84a1`:

- [Output T18](https://huggingface.co/datasets/team-crypto/Market-data-crypto-project/tree/3bfb61848e1ac9bcfb0809d3aef334d1885a84a1/data/processed/t18).
- [Manifest T18](https://huggingface.co/datasets/team-crypto/Market-data-crypto-project/blob/3bfb61848e1ac9bcfb0809d3aef334d1885a84a1/data/hf_t18_release_manifest.json).

Có 16 artifact/config và manifest, tổng **17 file**. Đã xác minh hash remote, rồi tải lại từng file qua HTTPS: **17/17 SHA-256 khớp local**, cả **10 bảng Parquet** đọc được bằng PyArrow. Có hai PNG, report, config và JSON provenance/review. Không upload CSV, test/cache hoặc xóa file remote.

Input T14/T15/T16 được ràng buộc bằng hash tại revision `d3cc595be2d452467e823596749a63723dfa2e1d`, giữ nguyên trong lần phát hành này. Không sửa gate upstream.

Phạm vi nghiệm thu là purged fixed-origin pseudo-OOS hồi cứu: test đã từng được nhóm xem trong phân tích toàn mẫu, không phải holdout chưa từng được xem. Không chứng nhận causal effect hoặc nhà đầu tư cá nhân. Hồ sơ kiểm tra trước phát hành ghi trạng thái local lúc đó; biên nhận này cập nhật trạng thái đã phát hành.

Chi tiết từng SHA-256 và row count tải lại: [T18_release_receipt.json](T18_release_receipt.json). Xem [đặc tả](T18_specification.md) và [báo cáo hoàn thành](T18_completion_report.md). Commit tài liệu sau phát hành không thay source/config đã gắn trong summary.
