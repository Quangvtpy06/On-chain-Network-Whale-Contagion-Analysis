# T11 — Kết quả xử lý review

**Đã xử lý năm điểm; nghiệm thu kỹ thuật đạt trên T08 hiện tại.**
RQ4 được báo cáo là mô tả hồi cứu quanh ngày volume cao, không khẳng định
stress thị trường, danh tính cá nhân hoặc hành vi đầu tư.

## Đối chiếu năm điểm

| Điểm review | Thay đổi | Bằng chứng |
|---|---|---|
| Đảo Baseline/Peak và so nhầm nhóm | Plot đọc regime theo tên, thứ tự baseline/pre/high-volume, N động; so đúng pre với baseline | PNG mới đã xem trực tiếp; cùng bảng rq4_comparison.parquet đã được validator kiểm tra |
| Báo cáo stale, sai CR top5%, thiếu bảng top | Sinh top community cho cả ngày/tuần; sinh bảng so sánh và báo cáo từ dữ liệu, lấy hash thật | 3.745 dòng top community; bảng thống kê 5 dòng; báo cáo sinh tự động |
| Kết luận RQ4 vượt bằng chứng | Gọi là high-volume proxy, bỏ suy luận Super-Whales/CEX/tái cơ cấu/khủng hoảng; nêu giới hạn Welch và thêm Holm | T11_completion_report.md và rq4_insights trong summary |
| Skip reproducibility vẫn ready | Summary giữ false trước kiểm định; skip luôn false, không in thông báo tái lập thành công | Kiểm tra nhánh skip với đầu ra thật tái sử dụng: ready=false, all_match=false |
| Validator chưa độc lập/đủ mạnh | Không nhập công thức production; kiểm tra mọi cửa sổ từ cạnh T08, hash file hiện tại, metadata, top, regime và thống kê | t11_review.json: all_pass=true, windows_checked=749 |

## Kết quả kiểm định

- 655 ngày và 94 tuần; 712.519/388.557 dòng node, đủ metadata lịch và hai tuần
  thiếu không dùng hồi quy.
- Đối chiếu node universe, khóa, volume/degree từ cạnh, partition, community
  size/volume, directed modularity bằng tổng theo community, HHI/Gini/entropy/CR,
  giant/internal metrics và thống kê size cho 749/749 cửa sổ.
- Gini tham chiếu dùng đường Lorenz; HHI dùng math.fsum từ volume đã tính lại.
  Không gọi hàm compute_gini/compute_hhi production.
- Tám Parquet được sinh trong hai tiến trình mới, cùng PYTHONHASHSEED=0;
  8/8 SHA-256 khớp. Đây là kiểm tra tái lập trong môi trường ghi nhận, không
  hứa giống mọi phiên bản NetworkX hoặc xác nhận phân hoạch tối ưu toàn cục.
- Chỉ validator thành công mới bật ready_for_downstream=true. Review lỗi phải
  lưu lý do và hạ ready=false. Manifest kiểm tra cả review, source và proof.

## Kiểm tra các trường hợp phải bị từ chối

Ba kiểm tra đã đạt, bằng bản sao dữ liệu thật trong .cache; đã xóa bản sao và
không giữ file mã test:

1. Sửa byte của Parquet: validator từ chối vì hash hiện tại không khớp proof,
   hạ ready=false.
2. Sửa HHI ngày 2025-02-17 (ngoài mẫu cũ), đồng thời cập nhật hash metadata
   trong bản sao để đi qua kiểm tra integrity: vẫn bị công thức tham chiếu
   phát hiện sai 0,01 và hạ ready=false.
3. Kiểm tra nhánh --skip-reproducibility bằng tái sử dụng các output thật đã
   kiểm định, không tính lại graph trong kiểm tra này: ready=false và proof
   all_match=false. Đây là kiểm tra điều kiện xuất bản, không phải thêm một
   lượt tái lập dữ liệu.

Kết quả lưu trong acceptance_controls của t11_review.json. Production Parquet
giữ nguyên hash qua các kiểm tra gây lỗi có kiểm soát.

## Các điều chỉnh bổ sung

- Dùng danh sách tám đầu ra chuẩn thay glob mọi Parquet, tránh lỗi run2 khi
  thêm bảng top. Run2 thực thi bằng tiến trình riêng.
- Tổng community volume sắp xếp địa chỉ trước khi cộng. Bỏ tham số
  min_community_size_for_stats không được sử dụng; thống kê bao gồm singleton.
- Ghi rõ community_id là ID trong từng snapshot, chưa có tracking qua thời gian.
- CCI được định nghĩa đúng code: max(Q,0) × HHI community volume.
- Đường dẫn ảnh thống nhất data/figures/t11; visualization là Matplotlib tĩnh.
- Bổ sung censor ba ngày cuối không đủ cửa sổ tương lai. Vì vậy baseline còn
  490 ngày, pre 96, high-volume 66, censored 3. Số liệu hiện tại khác lần review
  đầu do xử lý biên này, không phải lỗi cộng dữ liệu hoặc thay định nghĩa CR.
- Holm điều chỉnh năm phép so sánh, không xử lý phụ thuộc chuỗi thời gian.
  Không coi các p-value thăm dò là bằng chứng nhân quả/dự báo.

## Phạm vi kết luận

T11 hoàn tất ba sản phẩm: community theo cửa sổ, modularity và chỉ số tập trung
theo thời gian. **Chưa xác nhận giả thuyết tập trung cộng đồng tăng trước stress
thị trường.** HHI community và CCI vẫn chưa cung cấp bằng chứng đủ; Gini node
không thay được concentration cấp community.

Để nghiên cứu stress thị trường cần sự kiện độc lập và thiết kế thống kê phù
hợp. Để dự báo cần feature trễ, không đưa nhãn regime hồi cứu hoặc phân vị toàn
kỳ vào thông tin có sẵn tại t. Để theo dõi community cần alignment riêng.

Xem [báo cáo số liệu/hash hiện tại](T11_completion_report.md) và
[đặc tả](T11_community_concentration_specification.md). Bằng chứng chuẩn là
t11_summary.json, t11_review.json, t11_reproducibility.json và tám Parquet;
không dùng bản audit tạm của lần review đầu làm trạng thái hiện tại.
