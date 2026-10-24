# T16 — phân tích phản ứng quanh sự kiện

Protocol `t16_event_blocks_v2`, cấu hình `config/t16.yaml`. Các giá trị dưới đây được cố định trước lượt chạy sửa lỗi, giữ các ngưỡng đã có từ bản gốc; không chọn lại theo kết quả phản ứng.

## Input và phạm vi

Xác minh toàn bộ release/hợp đồng T14 như T15. Dùng eligibility predictor hiện tại, không dùng eligibility có target tương lai để quyết định tín hiệu sự kiện. Bắt buộc readiness cả CEX và activity cohort; giữ nguyên policy và phạm vi T14. T11 phải sẵn sàng downstream, có independent review, snapshot khớp hash hai lần chạy và dùng cùng daily-edge lineage T14. Mọi input được hash và kiểm tra lại sau tính.

Lịch ngày T14/T11 phải UTC midnight, duy nhất, liên tục và khớp hoàn toàn; merge one-to-one. Chấp nhận timestamp khác đơn vị lưu trữ sau chuẩn hóa về ns, không chấp nhận thời điểm bị lệch trong ngày.

## Bốn tín hiệu riêng

| Sự kiện | Tín hiệu | Ngưỡng |
|---|---|---|
| `large_transfer` | `large_transfer_count` | > p95 của tối đa 90 ngày trước |
| `cex_net_inflow` | `pit_cex_netflow_z` | > 2 |
| `activity_cohort_net_inflow` | `whaleflow_pit_z` | > 2 |
| `concentration` | `community_concentration_index` T11 | > p90 của tối đa 90 ngày trước |

Quantile yêu cầu ít nhất 30 giá trị lịch sử hợp lệ, cửa sổ `[D−90,D)`, không gồm chính D. Flow z đã chuẩn hóa quá khứ tại T14. Signal thiếu/warm-up không phải không có giao dịch; ghi `signal_available=false`/`signal_unavailable`. Thiếu cột bắt buộc thì dừng.

Hai sự kiện flow là **dòng ròng**, không gross inflow. CEX NetFlow không được gọi là WhaleFlow. Activity cohort không được gọi là nhà đầu tư cá nhân. Tín hiệu của D khả dụng D+1 00:00 UTC; tau=0 chứa phản ứng cùng ngày D, không phải dự báo sau khi nhận biết sự kiện.

## Chọn cửa sổ

Response cố định: `log_rv`, `log_volume_usdt`, `spread_cs_proxy`, `ret_1d`; k=5 ngày. Tra response bằng **ngày UTC**, không độ lệch số hàng. Yêu cầu đầy đủ 11 ngày và cả bốn response, loại cửa sổ biên hoặc thiếu dữ liệu, ghi rõ lý do. Giữ cùng mẫu qua tau và variable.

Primary: theo từng loại sự kiện, chọn ứng viên đầy đủ sớm nhất, chỉ chọn tiếp khi cách tâm trước **hơn 10 ngày**. Như vậy các cửa sổ primary không chồng nhau. Đây là lựa chọn theo ngày/tính khả dụng, không theo độ lớn phản ứng. Việc yêu cầu response đủ là lựa chọn mẫu retrospective phục vụ event study, không được dùng như quy tắc giao dịch thời gian thực.

Sensitivity: giữ tất cả ứng viên có cửa sổ đầy đủ, kể cả chồng nhau; không chọn lại ngưỡng. Bảng selection ghi cả ứng viên không chọn, cooldown và ngày không đủ tín hiệu/cửa sổ.

## Khoảng tin cậy và độ nhạy

Bootstrap circular moving blocks trên chuỗi **sự kiện theo thời gian**. Mỗi đơn vị là toàn bộ ma trận 11 ngày × 4 response của một sự kiện, được resample đồng thời. Primary block length=3 sự kiện; sensitivity length=1 và 5, cho cả chính sách nonoverlap/all-events. 2.000 lần, seed 20261025. Seed từng event/policy/block lấy từ SHA-256 ổn định, không dùng Python `hash()`.

CI percentile pointwise 95%, chỉ tính khi n ≥ max(5, 2 × block length); nếu thiếu ghi `insufficient_events` và CI null. Vẫn báo mean/median/n khi không thể báo CI. Không có sự kiện vẫn sinh bảng trạng thái đủ cấu trúc, không thoát thành công mà mất sản phẩm.

Các block là số sự kiện, không số ngày nên khoảng cách lịch trong block không đều. Nonoverlap xử lý việc tái sử dụng ngày; blocking xử lý một phần phụ thuộc giữa sự kiện gần nhau. Cách này không đảm bảo CI đã hiệu chỉnh mọi phụ thuộc dài hạn hoặc chế độ thị trường; mẫu ít sự kiện đặc biệt yếu. CI là thăm dò, không simultaneous confidence band, không kiểm định causal effect hay abnormal response so với phản thực. Không dùng việc CI không chứa zero để suy ra chênh lệch so với no-event baseline.

## Sản phẩm và kiểm định

`data/processed/t16/`: results, candidates (mọi ngày/loại), selection (mọi chính sách), windows và validation (Parquet); bốn biểu đồ PNG; report Markdown; summary/independent review JSON. Có `available_at` và `event_available_at` để xác định cutoff.

Kiểm tra nonoverlap, số ngày/tau, đủ response và tính tái lập. Validator riêng tính lại historical quantile bằng slice mảng và response bằng lookup ngày. Lượt sửa lỗi này đã kiểm tra rằng sửa hiện tại/tương lai không đổi ngưỡng quá khứ; mã test tạm không được giữ sau nghiệm thu. Nghiệm thu đối chiếu hai tiến trình có Python hash seed khác nhau. Giữ bằng chứng kiểm định JSON, xóa script/bảng test tạm sau khi đạt.

```text
python T16_Event_Study.py
python scripts/validate_t15_t16_release.py --task t16
```
