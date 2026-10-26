# Review T17/T18 — 25/10/2026

**T17 chạy đạt phần tính toán nhưng cần bổ sung kiểm tra nguồn trước nghiệm thu phát hành. T18 chưa đạt: thiếu mã thực thi và kết quả OOS hiện tại chưa xử lý nhãn train vượt thời điểm dự báo.**

## Phiên bản và phạm vi

- T17 đã ở main `7ba2c04e731eccb8fa45103bcb68fcb43fcbb800`, phần triển khai từ commit `94ae8bb`.
- T18 ở nhánh `feature/t18-analysis`, tip `841eaa6a095841f15f17815054fb7def1b10cd96`. Nhánh dựa trên bản T15/T16 cũ `182cea7`, không phải bản đã sửa/phát hành trên main.
- Commit T18 mới chỉ thêm `config/t18_train_test_split.yaml` và `t18_leakage_audit_report.md`; không có script train/predict/OOS hoặc mã audit tái chạy được trong commit đó.
- T17 chạy CLI hai tiến trình, Python hash seed 73 và 137, trên input local đã nghiệm thu. Tất cả output review nằm trong cache; không thay output chính thức hoặc sửa code pipeline.
- T18 được đối chiếu bằng phép tính riêng trên T14 thật để kiểm tra các số đã ghi trong báo cáo; đây không phải thực thi một script T18 có sẵn trong nhánh.
- Bằng chứng: [T17_T18_review_evidence.json](T17_T18_review_evidence.json). Cache, bản nguồn tải để đọc và fixture kiểm tra được xóa sau review; giữ tài liệu/bằng chứng, không push trong lượt này.

## T17 — kết quả chạy và điểm cần sửa

### Kết quả đạt

Hai lượt CLI hoàn tất: **40 dòng kịch bản hồi quy, 30 dòng robustness sự kiện, 52 kiểm tra PASS**. **8/8 file** giống SHA-256 giữa hai tiến trình, gồm cả bảng, report, PNG và summary.

Base T15/T16 khớp bản đã nghiệm thu; kiểm tra k=1, target single-day/cumulative h=1, edge percentile gốc, đại số HAC và mutation/truncation flow đều PASS. Grid phân biệt single-day và cumulative, không chọn kịch bản theo p-value, ghi rõ trục token chưa chạy. Không có kịch bản hồi quy đạt p Holm <0,05 trong từng trục.

### P1 — Chưa ràng buộc hash config T15/T16 đã dùng

[T17_Robustness.py:162](../T17_Robustness.py#L162) chỉ đưa `config/t17.yaml` và các file source vào `source_config_sha256`. `required_files()` cũng không đưa hai config phụ thuộc vào `input_sha256`. Đã kiểm tra summary thật: **cả `config/t15.yaml` và `config/t16.yaml` đều vắng mặt trong hai map hash**.

Hai config này quyết định controls, horizon cơ sở, ngưỡng sự kiện, bootstrap và quy tắc chọn sự kiện. Summary chỉ lưu đường dẫn của chúng trong parameters nên chưa đủ khóa đúng cấu hình đã tạo ra grid, cũng chưa phát hiện việc thay config trong lúc chạy.

Cần hash/check trước–sau mọi config thực sự đọc; gọi validator release T15/T16 hoặc đối chiếu các bảng tham chiếu với output hash trong release đã nghiệm thu. Hiện đọc các bảng tham chiếu rồi tự hash mới không đồng nghĩa xác minh chúng thuộc release đã chấp nhận.

### P1 — Snapshot tuần không được đối chiếu artifact T11 đã nghiệm thu

[T17_Robustness.py:61](../T17_Robustness.py#L61) đọc snapshot tuần trực tiếp. Kiểm tra T11 thông qua `events.load_concentration()` chỉ ràng buộc snapshot **ngày**. Snapshot tuần chỉ được kiểm tra cấu trúc/CCI trong [weekly_concentration_frame](../src/robustness.py#L199), chưa so với hash của bảng tuần trong `t11_reproducibility.json`.

Thử nghiệm có kiểm soát: tạo bản sao snapshot tuần trong cache, tăng CCI của `2025-W12` từ `0,0921712537` lên `0,0931712537`, giữ summary/repro T11 gốc. Loader T17 vẫn nhận bản sao và hàm dựng concentration tuần vẫn chấp nhận. Hash của bản sao khác rõ ràng hash tuần đã nghiệm thu. **Không sửa snapshot thật của dự án.**

Cần yêu cầu hash file tuần khớp cả run1/run2 của T11 và xác minh metadata T11 liên quan trước khi chạy grid. Kết quả baseline trên file chuẩn vừa chạy không bị chứng minh sai; lỗi là thiếu guard chống dùng sai phiên bản đầu vào.

### P2 — Kiểm tra “mẫu lồng trong base” chưa kiểm tra đúng điều đã đặt tên

[src/robustness.py:358](../src/robustness.py#L358) chỉ kiểm tra `sample_start >= ngày đầu toàn kỳ`. Không đối chiếu tập ngày với base cùng nhánh/horizon, không kiểm tra sample_end và không dùng sample date hash để chứng minh tập con.

Thử sửa metadata `sample_end` của các kịch bản k>1 thành năm 2030 trong một bản sao bảng ở bộ nhớ: kiểm tra này vẫn PASS. Cần lưu/tính lại tập ngày chọn và xác minh tập con đúng base tương ứng; không coi kiểm tra hiện tại là bằng chứng về mẫu lồng.

### P2 — Thứ tự thực hiện khác đặc tả “base trước, không khớp thì không chạy grid”

[T17_Robustness.py:164](../T17_Robustness.py#L164) tính toàn bộ grid hai lần rồi mới gọi reconciliation trong validation. Cuối cùng FAIL vẫn ngăn `computation_validated=true`, nên chưa phải bằng chứng về việc phát hành nhầm. Tuy vậy, nên kiểm tra base trước khi chạy grid đúng như đặc tả và lỗi sớm khi reference không hợp lệ.

Trục token vẫn `not_run` do chỉ có USDT. Đây là giới hạn được khai báo đúng; nếu tiêu chí nghiên cứu đòi token khác thì trục đó chưa hoàn thành, không được gọi là đã kiểm tra đa token.

## T18 — chưa đủ điều kiện nghiệm thu

### P1 — Chưa có pipeline thực thi và đang audit phiên bản cũ

[Commit T18](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/commit/841eaa6a095841f15f17815054fb7def1b10cd96) chỉ thêm report và config. Không có mã tái chạy split, xác minh release T14/T15/T16, fit, predict, xuất từng dự báo hoặc kiểm định leakage. Report còn dẫn các dòng của T15/T16 cũ, dùng tên `whale_inflow` đã được sửa bỏ.

Cần triển khai trên main mới, đọc đúng hai nhánh CEX/activity cohort và hợp đồng `t14_inputs_v1`, ghi phiên bản/hash/eligibility, xuất split và dự báo Parquet. Không dùng báo cáo Markdown thay bằng chứng tái chạy.

### P1 — R² công bố tái hiện bằng train không purge nhãn tương lai

[Bước 3 của report](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/841eaa6a095841f15f17815054fb7def1b10cd96/t18_leakage_audit_report.md#L151) chia feature dates train đến 08/06/2026 và test từ 09/06/2026. Tái hiện bằng fit trên mọi hàng train còn target đã tính sẵn cho ra đúng các số trong report.

Với feature date D, `available_at = D+1 00:00 UTC`; target `log RV[D+h]` chỉ khả dụng tại **D+h+1 00:00 UTC**. Dự báo test đầu tiên có feature date 09/06, cutoff sớm nhất 10/06 00:00 UTC. Ngay tại cutoff này:

| h | n train chưa purge | Nhãn train chưa khả dụng | R² công bố/tái hiện chưa purge | R² tính lại sau purge theo cutoff đầu tiên |
|---|---:|---:|---:|---:|
| 1 | 464 | 0 | 0,252486 | 0,252486 |
| 3 | 464 | 2 | −0,064769 | −0,063623 |
| 7 | 464 | 6 | 0,155680 | 0,144672 |

Ví dụ h=7: hàng train ngày 03–08/06 dùng RV ngày 10–15/06, chưa biết tại cutoff 10/06. Kết quả trên là phép đối chiếu của reviewer; vì thiếu script tác giả, không suy ra chính xác mọi thao tác mà tác giả đã làm. Tuy nhiên report hiện khớp tính toán không purge và không có bằng chứng kiểm soát điểm này nên chưa được gọi là OOS đã nghiệm thu.

Cần đóng băng `fit_at`, forecast origin và `target_available_at`, chỉ dùng nhãn có `target_available_at <= fit_at`; kiểm tra riêng theo h. Nếu fit sớm hơn cutoff đầu tiên thì phải purge thêm tương ứng. Kết quả h=1 trong bảng không có lỗi nhãn tương lai theo cutoff vừa nêu.

### P1/P2 — Số sự kiện T16 trong report không còn áp dụng

Report lấy 42/16/74 ứng viên của bản cũ để chia train/test, không phải primary event windows đã nghiệm thu. Đối chiếu `t16_event_selection.parquet` mới theo cutoff đề xuất:

| Primary event | Train | Test |
|---|---:|---:|
| Activity cohort net inflow | 7 | **0** |
| CEX net inflow | 12 | **0** |
| Concentration | 25 | **6** |
| Large transfer | 11 | **3** |

Một sự kiện concentration ngày 11/06 có cửa sổ pre/post đi qua ranh giới train/test. Nếu yêu cầu toàn bộ response window nằm trong test thì concentration test còn **5**. Cần ghi rõ quy tắc giữ/loại cửa sổ qua biên; không dùng cùng response train trong một “holdout” mà không khai báo. Các nhóm quá ít sự kiện phải báo không đủ mẫu, không tự hạ ngưỡng để tạo thêm sự kiện sau khi xem test.

### P2 — Cần benchmark và giới hạn diễn giải dự báo

R² dùng mean của y trong test làm mẫu số là metric đánh giá được, nhưng không phải benchmark dự báo có thể dùng tại forecast origin. R² >0 không chứng minh flow cải thiện HAR; R² <0 cũng không tự chứng minh overfitting là nguyên nhân duy nhất.

Cần cùng test rows cho baseline controls/HAR và mô hình thêm flow, báo loss/R² cải thiện tương đối và sample sizes, xử lý phụ thuộc thời gian của loss. Đối chiếu tạm sau purge, R² baseline so với mean test lần lượt 0,249695; −0,065592; 0,144017, còn mô hình flow 0,252486; −0,063623; 0,144672: chênh lệch nhỏ, chưa có kiểm định chứng minh giá trị dự báo gia tăng.

Phải giữ policy `t12_v2_research_knowledge`: việc z-score dùng quá khứ không biến cohort thành tập được biết hoàn toàn từ thông tin công khai lịch sử. Giai đoạn test đề xuất cũng đã xuất hiện trong kết quả toàn mẫu T15/T17 mà nhóm đã xem; nên gọi là retrospective/pseudo-OOS backtest, không tuyên bố là holdout chưa từng được xem. Điều này không cấm backtest, nhưng giới hạn mức độ khẳng định.

## Thứ tự xử lý đề nghị

1. Bổ sung ràng buộc config/release/snapshot tuần và kiểm tra sample membership cho T17; chạy lại guard và kiểm định độc lập. Không cần sửa T14/T15/T16 chỉ vì các lỗi tích hợp này.
2. Port phần T18 sang main hiện tại và thêm runner, freeze protocol/cutoff/fit policy, purge theo target availability, rồi xuất split/prediction/validation Parquet cùng manifest.
3. Chạy lại OOS cho cả hai nhánh T15 và phân loại sự kiện T16 mới; báo thiếu mẫu, benchmark và độ bất định. Không thay quy tắc theo kết quả test.
