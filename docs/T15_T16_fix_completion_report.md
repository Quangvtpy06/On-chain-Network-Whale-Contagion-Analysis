# Hoàn tất sửa T15/T16 — 25/10/2026

Đã thay hai script trên nhánh `feature/t15-t16-analysis` phiên bản `182cea7` bằng entrypoint có cấu hình và các module tính toán/kiểm định. Bản sửa nằm trong working tree local trên nền main mới nhất đã tải; chưa commit/push GitHub hoặc upload Hugging Face.

## T15

- Dùng validator và hợp đồng `t14_inputs_v1`, đúng hash, policy, predictor sets và eligibility theo nhánh/horizon.
- Có riêng nhánh activity cohort và CEX; nhánh hồi cứu chỉ robustness. Không sửa cờ RQ3 upstream hoặc suy diễn ví cá nhân.
- Baseline và mô hình có flow dùng cùng ngày và cùng 9 control. Có sample membership, SHA-256 ngày mẫu, guard thiếu control, infinity, zero variance, rank và lịch HAC.
- Holm cho 6 kiểm định chính, giữ p thô. Summary Parquet và boolean JSON thật; không CSV hoặc đường dẫn output lồng.

| Nhánh | h | n | R² baseline khớp mẫu | R² primary | p thô | p Holm |
|---|---:|---:|---:|---:|---:|---:|
| Activity cohort | 1 | 594 | 0,448242 | 0,449332 | 0,304614 | 1,000000 |
| Activity cohort | 3 | 592 | 0,233194 | 0,234061 | 0,440603 | 1,000000 |
| Activity cohort | 7 | 588 | 0,292846 | 0,293263 | 0,381747 | 1,000000 |
| CEX | 1 | 624 | 0,445516 | 0,447543 | 0,177228 | 0,886140 |
| CEX | 3 | 622 | 0,235257 | 0,239812 | 0,049994 | 0,299964 |
| CEX | 7 | 618 | 0,313275 | 0,313280 | 0,937393 | 1,000000 |

Không có flow chính đạt ý nghĩa 5% sau Holm. Trường hợp CEX h=3 chỉ vừa dưới 0,05 ở p thô; không được chọn riêng để kết luận có bằng chứng mạnh. Các kết quả này là liên hệ trong mẫu, chưa phải kiểm định khả năng dự báo ngoài mẫu.

## T16

- Đọc đúng `data/processed/t11` và `t14`, xác minh release/lineage/hash; kiểm tra lịch UTC và merge duy nhất.
- Tách `cex_net_inflow` và `activity_cohort_net_inflow`, không gọi CEX NetFlow là whale inflow.
- Giữ ngưỡng cũ, ghi cố định trong config; lưu candidates, tính khả dụng, selection và cửa sổ để kiểm tra.
- Primary không chồng cửa sổ k=5; bootstrap block toàn bộ event path, seed SHA-256 ổn định, có sensitivity block 1/5 và tập all-events.

| Sự kiện | Ứng viên | Primary đầy đủ/không chồng | Sensitivity đầy đủ/tất cả |
|---|---:|---:|---:|
| Activity cohort net inflow | 8 | 7 | 8 |
| CEX net inflow | 16 | 12 | 15 |
| Concentration | 74 | 31 | 74 |
| Large transfer | 42 | 14 | 41 |

Không lấp dữ liệu biên; cửa sổ thiếu được loại có lý do. CI thăm dò pointwise, không phải causal effect hoặc abnormal response. Đặc biệt nhánh cohort chỉ có 7 sự kiện primary: sensitivity block=5 không đủ mẫu nên CI được để trống và gắn trạng thái, không cố tạo khoảng tin cậy.

## Kiểm định và bàn giao

Kết quả cuối, SHA-256 và danh sách ca kiểm tra được giữ tại [T15_T16_fix_validation.json](T15_T16_fix_validation.json). Hai lượt CLI có Python hash seed khác nhau được đối chiếu, kèm validator thực chạy trong tiến trình riêng. Validator T15 còn tính beta/HAC SE bằng đại số ma trận độc lập; validator T16 tính quantile bằng slice lịch sử và lookup response theo ngày.

- **15/15 bài kiểm tra PASS**, gồm cả từ chối output bị sửa, thiếu hash artifact và snapshot T11 không khớp bằng chứng tái lập.
- **18/18 file khớp SHA-256** giữa các lượt CLI với `PYTHONHASHSEED=2` và `73`, bao gồm Parquet, Markdown, PNG và summary JSON.
- Tiến trình validator riêng với hash seed `137`: cả T15/T16 PASS; 18 kiểm tra ma trận OLS/HAC và 3 kiểm tra quantile/lookup độc lập PASS.
- Đã xem biểu đồ hệ số T15 và biểu đồ cohort T16; manifest local có 22 file đúng hash. Không xuất CSV mới.

Output mới ở `data/processed/t15` và `data/processed/t16`, bảng chỉ Parquet, có biểu đồ/report và JSON provenance. Giữ validator dữ liệu thật, xóa script/dữ liệu test tạm sau nghiệm thu. Manifest chuẩn bị tại `data/hf_t15_t16_release_manifest.json`; chưa upload. Các bài kiểm tra giả là bằng chứng lịch sử của lần này, không được coi là vẫn tồn tại cho các lần chạy sau.

Xem [đặc tả T15](T15_specification.md), [đặc tả T16](T16_specification.md). Review ngày 24/10 giữ nguyên như lịch sử trước sửa; báo cáo này mô tả phiên bản thay thế.
