# Kiểm tra T17 trên main — 26/10/2026

Commit kiểm tra: `f402d166b2db2faca22f963c4cee66ac2fad07b3` lấy trực tiếp từ GitHub. Đã đọc ba ảnh góp ý và blueprint. Kết luận: code chạy được và đã sửa một số lỗi nguồn đầu vào, nhưng chưa đủ điều kiện nghiệm thu toàn bộ T17.

## Kết quả chạy thật

- Hai tiến trình CLI riêng, output đặt trong `.cache/t17_latest_review/`; lần thứ hai dùng `PYTHONHASHSEED=137`.
- Mỗi lần: 40 dòng hồi quy, 30 dòng event study, 74 PASS và 0 FAIL; `computation_validated=true`.
- Cả 8 file đầu ra giống nhau theo SHA-256, gồm Parquet, JSON, Markdown và PNG.
- Kịch bản gốc khớp T15/T16; kiểm tra đại số ma trận beta/SE HAC và mutation/truncation quá khứ đều PASS trên dữ liệu hiện hành.
- Không hệ số flow nào có p Holm dưới 0,05 trong các họ kịch bản hồi quy hiện tại. Kết quả này không chứng minh khả năng dự báo ngoài mẫu.
- Hash nguồn và dữ liệu chính thức được kiểm tra lại sau các thử nghiệm; không thay đổi.

## Những phần đã sửa đúng

`T17_Robustness.py:63–74` đối chiếu hash config T15/T16 với release. Ca đổi một comment trong bản config sao chép bị từ chối.

`T17_Robustness.py:84–98` đối chiếu hash snapshot tuần với cả hai lần tái lập T11 và kiểm tra số snapshot/CCI. Bản sao giữ nguyên tên file nhưng sửa CCI bị từ chối. Như vậy, hai lỗi thiếu kiểm tra config và thiếu xác minh snapshot tuần của bản trước đã được xử lý.

Đối chiếu tập ngày mẫu gốc T15 cũng đã được thêm. Tuy nhiên, quy tắc cho các cửa sổ flow dài hơn vẫn có lỗi dưới đây.

## Các phát hiện cần xử lý

### 1. Ưu tiên cao — Validator mẫu flow giả định sai về k−1 ngày

Vị trí: `src/robustness.py:374–393`, đặc biệt `expected_dropped = set(base_sorted[:k-1])`; đặc tả cũng ghi cùng giả định.

Ca có kiểm soát trên bản sao dữ liệu thật: đặt raw cohort flow ngày 28/10/2025 thành NaN. Với h=1, mẫu cơ sở có 593 ngày; k=3 có 589 ngày, giảm 4 ngày thay vì 2; k=7 có 581 ngày, giảm 12 thay vì 6. Hai ngày 29–30/10 bị ảnh hưởng bởi cửa sổ 3 ngày là hệ quả hợp lệ của dữ liệu thiếu, không phải bằng chứng gán ngày sai.

Một ca khác chỉ cho eligibility bắt đầu từ dòng 200: các cửa sổ đã đủ lịch sử trước ngày đủ điều kiện, nên k=1,3,7 đều có 454 ngày ở h=1. Validator vẫn báo FAIL vì đòi mất k−1 ngày đầu. Các ca này dùng bộ fit giả để tách kiểm tra chọn mẫu khỏi OLS/HAC; không coi chúng là hồi quy đạt trên mẫu có khoảng trống.

Cần dựng tập ngày kỳ vọng theo từng k từ readiness, controls hữu hạn, target hữu hạn và z-score rolling hợp lệ; so tập ngày thực tế chính xác với tập kỳ vọng. Không áp đặt tập con hoặc số ngày mất cố định như một định luật chung. Nếu dữ liệu thiếu tạo khoảng trống, phải giữ chính sách xử lý HAC rõ ràng; không lấp NaN bằng 0.

### 2. Ưu tiên cao — Chưa xác minh artifact T15/T16 theo release

Vị trí: `T17_Robustness.py:60–74,101–105`. Code ghi hash file hiện tại và kiểm tra file không đổi trong lúc chạy, nhưng chưa đối chiếu hash các Parquet T15/T16 được đọc với `output_sha256` của release đã nghiệm thu; cũng chưa kiểm tra toàn bộ trạng thái/source/input lineage của release T15/T16.

Thử trên thư mục T16 sao chép: sửa một threshold từ 151,2 thành 12.496,2, giữ nguyên summary đã nghiệm thu. File đã khác hash (`94074d...` thay vì `229b1c...`) nhưng loader vẫn nhận. Hai phép đối chiếu T16 vẫn PASS vì ngày được chọn và tổng số ứng viên không đổi. Đây là thử loader và reconciliation; không tuyên bố đã chạy toàn bộ CLI với bản sửa giả.

Cần kiểm tra readiness/review của release, source/config/input lineage và hash từng artifact thực sự tiêu thụ trước khi tính grid. Có thể dùng validator T15/T16 hiện có hoặc một hàm kiểm tra release chỉ đọc phù hợp.

### 3. Ưu tiên vừa — Đối chiếu ứng viên T16 chỉ so tổng số

Vị trí: `src/robustness.py:342–349`.

Đảo một ngày có candidate=true với một ngày candidate=false trong cùng loại sự kiện, giữ nguyên bảng selection, vẫn nhận PASS. Cần đối chiếu theo khóa `(event_type, date)`, gồm candidate, signal availability và threshold, xử lý NaN/sai số số học rõ ràng. Việc xác minh hash ở mục 2 và đối chiếu nội dung ở mục này có mục đích bổ trợ nhau.

### 4. Phạm vi nghiệm thu — Token vẫn chưa chạy; PASS chưa thể hiện hoàn thành

Vị trí: `config/t17.yaml:41–43`, `T17_Robustness.py:124–125,154,240–244`.

Token luôn được ghi not_run; kiểm tra `token_axis_not_run_and_declared` lại luôn PASS với chuỗi `other_tokens=[]`. Đổi cấu hình sang USDC không tạo kịch bản token; logic không triển khai token và cũng không từ chối cấu hình này ngay. Không được hiểu `computation_validated=true` là toàn bộ các trục giao việc đã hoàn thành.

Blueprint cho phép chọn một token/asset, nên không thể kết luận bắt buộc đa token chỉ từ blueprint. Nhưng nếu bảng phân công T17 yêu cầu token sensitivity như ảnh phản ánh, cần chạy pipeline thật cho token khác hoặc có quyết định chấp nhận giới hạn USDT được ghi rõ. Tách trạng thái tính toán, trạng thái từng trục và trạng thái nghiệm thu; cấu hình token chưa hỗ trợ phải bị từ chối rõ ràng.

### 5. Phạm vi nghiệm thu — Cửa sổ đồ thị chỉ là ngày và tuần ISO

Vị trí: `src/robustness.py:200–235`, `config/t17.yaml:38–39`.

Chỉ số tuần lấy từ snapshot T11 thật, đặt vào Chủ nhật của tuần đầy đủ, không nhân bản sang mọi ngày. Cách gán thời gian này phù hợp cutoff D+1 UTC. `weekly_minimum_history_values: 8` là số quan sát tuần tối thiểu để tính threshold trong lịch sử 90 ngày, không phải đồ thị 8 tuần.

Rolling flow k=3,7 không phải graph window mới. Nếu nghiệm thu chỉ yêu cầu so ngày/tuần thì có thể chấp nhận khi ghi rõ. Nếu yêu cầu graph windows 1/7/30 ngày thì còn thiếu snapshot 30 ngày và chỉ số tương ứng. Chốt phạm vi và token waiver trước lượt nghiệm thu tiếp theo; thay đổi phương pháp/phạm vi thực chất phải có phiên bản protocol mới, không chỉ đổi cờ PASS.

### 6. Ưu tiên thấp — Thứ tự chạy không đúng mô tả fail-fast

Vị trí: `T17_Robustness.py:219–221`, docstring `src/robustness.py:3–5`.

Tài liệu nói tái tạo base trước rồi mới chạy grid. Thực tế compute toàn bộ grid hai lần rồi mới reconciliation. Khi base sai, cuối cùng vẫn FAIL, nhưng tốn chi phí và đã tính các kịch bản chưa đủ điều kiện. Tách bước kiểm tra base, dừng ngay khi không khớp, rồi mới tính sensitivity.

## Các điểm cần diễn giải chính xác

- Không yêu cầu mọi kịch bản phải có hệ số hoặc ngày sự kiện khác nhau. Ngưỡng khác có thể chọn cùng tập sự kiện hợp lệ. Điều cần xác minh là tham số đã đi vào đúng phép tính và mọi kịch bản được báo cáo.
- z-score hiện tại chuẩn hóa raw flow theo lịch sử flow; volume chỉ dùng cho scaled flow, không dùng cho z-score mà `trailing_flow_z` trả về. Thử đặt volume một ngày thành NaN không làm thay đổi bất kỳ z-score nào. Vì vậy, góp ý “NaN raw flow hoặc volume đều bắt buộc làm z-score NaN” không đúng với công thức hiện hành. Nếu muốn volume là điều kiện bắt buộc, phải chốt quy tắc và thêm mask; không tự đổi công thức khi chỉ sửa validator.
- Các mẫu k khác nhau hiện có số ngày khác nhau. Có thể bổ sung so sánh trên giao các ngày hợp lệ để tách tác động đổi cửa sổ khỏi tác động đổi mẫu; đây là kiểm tra độ nhạy bổ sung, không lý do thay đổi kết quả để đạt ý nghĩa thống kê.
- T17 là liên hệ trong mẫu và robustness; không thay thế T18 hoặc yêu cầu untouched out-of-sample của blueprint và không tự hoàn tất RQ3.

## Bằng chứng và dọn dẹp

`docs/T17_latest_review_evidence.json` giữ commit, hash nguồn/input/output, 74 dòng validation, kích thước mẫu và kết quả các ca kiểm tra có kiểm soát. Mã test, bản dữ liệu sửa giả và hai thư mục output đối chiếu được xóa sau khi kiểm tra; không phải bộ test còn được lưu để chạy lại tự động. Không sửa code T17, không thay output chính thức và không upload GitHub/HF trong đợt review này.
