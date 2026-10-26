# Review T15, T16 và T19 — 2026-10-24

> Review lịch sử trước sửa. T15/T16 đã có bản thay thế ngày 25/10/2026; xem [báo cáo sửa lỗi](T15_T16_fix_completion_report.md) và bằng chứng kiểm định đính kèm. Các vị trí code GitHub bên dưới trỏ phiên bản cũ có chủ đích.

Kết luận: **T15 cần sửa trước nghiệm thu; T16 cần sửa trước nghiệm thu; T19 đạt kiểm tra tính toán trong phạm vi phân loại hồi cứu CEX/DEX.** Đây là review code và chạy đối chiếu trên dữ liệu local, không phải nghiệm thu output trên Hugging Face hoặc phát hành output mới.

## Phiên bản và cách kiểm tra

- GitHub: `Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis`.
- `main`: `b59985d305c9492f2d00cf5bf70c2f1f7de2a864`, đã có T19. Local được fast-forward tới bản này.
- T15/T16 nằm trên `feature/t15-t16-analysis`: `182cea78f9a55efde63cce708094610287d750b8`, chưa có trên main. Đọc đúng byte nguồn từ nhánh này để chạy trong cache, không merge nhánh.
- Python 3.12.5, interpreter do PyCharm cấu hình. Không sửa mã pipeline trong review.
- T14 local: 655 ngày, 70 cột. Chạy `scripts/validate_t14_release.py`: xác minh 9 artifact, hợp đồng `t14_inputs_v1` hợp lệ; cả hai nhánh đầu vào CEX và activity cohort sẵn sàng.
- Chạy đầy đủ T15 với đầu vào T14 chuẩn và output trong cache. Với T16, tái hiện lỗi đường dẫn mặc định trước; sau đó chỉ thay đường dẫn T14/T11 và output ở runtime để kiểm tra phần tính toán. Với T19, chỉ đổi `output_dir` trong bản config dùng cho review; giữ nguyên các tham số và đầu vào.
- Bằng chứng số liệu, hash nguồn, summary T19 và các phép kiểm tra bổ sung: [T15_T16_T19_review_evidence.json](T15_T16_T19_review_evidence.json).
- Các script/bảng/biểu đồ chạy tạm được xóa sau review. Không thay output chính thức, không upload hoặc commit thay người dùng.

## T15 — cần sửa

### 1. So sánh baseline chưa cùng mẫu và cùng bộ kiểm soát (P1)

[Dòng 226 và 283–286](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/182cea78f9a55efde63cce708094610287d750b8/T15_Volatility_Regression.py#L226): mỗi mô hình tự `dropna`; baseline không có WhaleFlow nên có thêm 30 ngày. Mô hình chính mặc định còn dùng bốn extended controls mà baseline không dùng. Vì vậy chênh lệch R² trên README chưa đo riêng phần đóng góp của WhaleFlow.

| h | n mô hình chính | n baseline hiện tại | R² chính | R² baseline hiện tại | R² baseline tính lại cùng ngày và cùng controls |
|---|---:|---:|---:|---:|---:|
| 1 | 594 | 624 | 0,449332 | 0,440227 | 0,448242 |
| 3 | 592 | 622 | 0,234061 | 0,219162 | 0,233194 |
| 7 | 588 | 618 | 0,293263 | 0,300854 | 0,292846 |

Cần cố định mẫu theo horizon trước khi fit; mô hình đối chứng dùng cùng controls và chỉ bỏ WhaleFlow. Có thể giữ HAR thuần như một benchmark riêng, nhưng phải phân biệt với phép kiểm tra đóng góp gia tăng của WhaleFlow. Tính lại bảng và diễn giải README/report sau khi sửa. Hệ số/p-value chính đã tái hiện được; ba p-value hiện tại khoảng 0,305; 0,441; 0,382, chưa cho bằng chứng có ý nghĩa ở mức 5%. Đây là hồi quy trong mẫu, chưa phải đánh giá dự báo ngoài mẫu.

### 2. Chưa thực thi hợp đồng bàn giao T14 (P1, áp dụng cả T16)

[T15 dòng 489](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/182cea78f9a55efde63cce708094610287d750b8/T15_Volatility_Regression.py#L489) đọc Parquet trực tiếp. T16 cũng đọc trực tiếp trong loader. Hai script chưa gọi validator, ràng buộc phiên bản/hash, kiểm tra readiness theo nhánh hoặc dùng bảng eligibility/predictor_sets. T14 local hiện hợp lệ, nên lỗi tích hợp này không có nghĩa số liệu vừa chạy dùng input sai; nó khiến những lần sau vẫn có thể nhận input cũ hoặc đã thay đổi mà không phát hiện.

Cần xác minh release trước khi tính, lấy đúng nhánh và eligibility theo horizon, giữ chính sách `observed_approved_cex_subset` và `unidentified_high_activity_addresses`/`t12_v2_research_knowledge` trong metadata. Không diễn giải activity cohort thành nhà đầu tư cá nhân hoặc cohort chỉ dựa trên thông tin công khai lịch sử. Thiếu control bắt buộc phải báo lỗi thay vì âm thầm đổi mô hình.

### 3. Đường dẫn và CSV trái quy ước (P2)

[Dòng 54](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/182cea78f9a55efde63cce708094610287d750b8/T15_Volatility_Regression.py#L54) hard-code output thành `data/market_data/data/processed/t15`; [dòng 543](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/182cea78f9a55efde63cce708094610287d750b8/T15_Volatility_Regression.py#L543) xuất CSV. Cần config đường dẫn tương đối, output chuẩn `data/processed/t15` và summary Parquet.

### 4. Boolean trong metadata bị ghi thành chuỗi (P2)

[Dòng 247](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/182cea78f9a55efde63cce708094610287d750b8/T15_Volatility_Regression.py#L247) tạo NumPy boolean; `json.dumps(default=str)` tại dòng 566 biến thành `"whale_sig5": "False"`. Đã tái hiện trên output. Cần chuyển sang `bool` trước khi serialize; giá trị phải là JSON `false`. Chuỗi không rỗng có thể bị downstream hiểu là truthy. Metadata cũng cần ghi đúng extended controls thực sự đã fit.

## T16 — cần sửa

### 1. Loader mặc định không chạy được trên bố cục chuẩn (P1)

[Dòng 52–59 và 98–102](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/182cea78f9a55efde63cce708094610287d750b8/T16_Event_Study.py#L98) tìm T11 dưới `data/market_data/data/processed/t11`. Máy có file chuẩn tại `data/processed/t11` nhưng script vẫn `FileNotFoundError`. T14 còn ưu tiên bản trong thư mục lồng nếu tồn tại, tạo rủi ro đọc bản cũ. Cần cấu hình đường dẫn chuẩn và xác minh hash, output `data/processed/t16`.

### 2. “Whale inflow” đang dùng tín hiệu khác (P1)

[Dòng 165–177](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/182cea78f9a55efde63cce708094610287d750b8/T16_Event_Study.py#L165) lấy `pit_cex_netflow_z`, là dòng ròng vào CEX của toàn bộ endpoint được duyệt, không phải dòng của activity cohort và cũng không phải gross inflow.

Trên T14 mới, điều kiện CEX z > 2 cho **16 ngày**, còn `whaleflow_pit_z > 2` cho **8 ngày**; hai tập khác nhau ở **16 ngày**. Cần chọn rõ câu hỏi: đổi tên thành sự kiện CEX net inflow nếu giữ tín hiệu hiện tại; hoặc dùng biến cohort thích hợp và gọi đúng là dòng ròng cohort → CEX. Không tự động thay netflow bằng gross inflow hay gán danh tính cá voi.

### 3. Cùng seed vẫn không tái lập giữa các tiến trình (P1)

[Dòng 276](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/182cea78f9a55efde63cce708094610287d750b8/T16_Event_Study.py#L276) cộng `hash(var)` vào seed. Hash chuỗi mặc định phụ thuộc tiến trình Python.

Đã chạy hai tiến trình với cùng dữ liệu `[1, 2, 3, 4, 10, 20, 80]`, `seed=42`, 1.000 bootstrap, lần lượt `PYTHONHASHSEED=1/2`: mean cùng 17,142857 nhưng cận trên CI lần lượt **38,289286** và **39,285714**. Cần seed theo thứ tự biến cố định hoặc digest ổn định, rồi kiểm tra lại qua hai tiến trình độc lập.

### 4. CI chưa xử lý phụ thuộc giữa các cửa sổ sự kiện (P2)

[Dòng 245](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/182cea78f9a55efde63cce708094610287d750b8/T16_Event_Study.py#L245) resample IID từng giá trị theo tau. Với k=5, trong 74 sự kiện concentration có 56 khoảng cách liên tiếp ≤10 ngày; với 42 large-transfer có 30; với 16 CEX-netflow có 4. Có cửa sổ chồng nhau và phụ thuộc thời gian nên CI hiện tại chưa có cơ sở để coi các sự kiện là các quan sát độc lập.

Cần đóng băng quy tắc gộp cụm/cooldown hoặc bootstrap theo block/cụm thích hợp và báo độ nhạy. Quy tắc ngưỡng hiện vẫn ghi `[DEFAULT] chưa xác nhận`; cần đưa thành protocol trước khi diễn giải kết quả.

### 5. Calendar và thiếu dữ liệu chưa được kiểm tra chặt (P2)

[Dòng 219](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/182cea78f9a55efde63cce708094610287d750b8/T16_Event_Study.py#L219) dùng độ lệch hàng làm độ lệch ngày; loader không xác minh lịch ngày liên tục/khóa duy nhất. Ví dụ giả ngày 01/01 và 03/01 vẫn bị coi là tau=0 và tau=1. Dữ liệu thật đang dùng đủ ngày nên ví dụ này chứng minh thiếu guard, không chứng minh lịch output thật vừa chạy sai.

Cần calendar UTC duy nhất/liên tục, merge one-to-one; thiếu tín hiệu bắt buộc phải dừng hoặc ghi trạng thái unavailable, không coi thành không có sự kiện. Sau khi chỉnh đường dẫn ở runtime, pipeline chạy hết và tạo kết quả cho 42 large-transfer, 16 CEX-netflow đang mang tên whale-inflow, 74 concentration; đây chỉ là kiểm tra vận hành, chưa nghiệm thu phương pháp.

## T19 — đạt tính toán theo phạm vi đã đặc tả

Chạy đủ daily/weekly, mỗi loại tính hai lần và kiểm tra truncation/mutation tương lai tại ba cutoff: **70 PASS, không FAIL/WARN**; hash nội dung hai lần khớp.

| Cửa sổ | Số cửa sổ | Dòng node-window | Feature | Lớp đủ điều kiện |
|---|---:|---:|---:|---|
| Weekly | 94 | 388.557 | 41 | CEX, DEX |
| Daily | 655 | 712.519 | 41 | CEX, DEX |

Kiểm tra bổ sung ngoài validator của pipeline: tổng volume nút bằng hai lần volume cạnh cho mọi cửa sổ; không trùng khóa; từ điển feature không chứa nhãn/id/split; đối chiếu lag bằng lookup cửa sổ lịch trước cho 200 dòng ngẫu nhiên mỗi loại, đều khớp. Hai tuần lẻ bị loại khỏi split. Cả hai `computation_validated` và `node_classification_ready` là true trong lượt chạy review; `pit_label_forecast` đúng là false.

Giới hạn phải giữ khi bàn giao T20:

- Đây là phân loại hồi cứu CEX/DEX trên feature cùng cửa sổ, không dự báo nhãn lịch sử và không phân loại “cá voi cá nhân”. Nhãn hiếm/unknown không thành lớp âm.
- Rất nhiều dòng test thuộc địa chỉ đã thấy trong train: weekly CEX 87,46%, DEX 96,70%; daily CEX 90,56%, DEX 99,01%. Phải báo riêng kết quả ví mới và quy mô mẫu; kết quả tổng không chứng minh khái quát tốt sang ví mới.
- T20 chỉ lấy predictor từ `t19_feature_dictionary.parquet`, chỉ dùng label hợp lệ và split train/validation/test, fit preprocessing trên train. Không đưa các cột `label_*`, address, split hoặc metadata vào predictor.
- Nên bổ sung provenance source-code hash và validator release T19 độc lập trước phát hành: summary hiện ghi hash config/input và sáu bảng chính, chưa ghi hash mã nguồn hay toàn bộ artifact. Đây là cải thiện cơ chế phát hành; chưa phát hiện sai số feature trên dữ liệu review.

Các output review T19 được tạo trong cache và xóa theo quy ước; kết luận trên không có nghĩa đã chạy thay thế hoặc upload output T19 chính thức.
