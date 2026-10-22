# T12 — Điểm thăm dò địa chỉ hoạt động lớn

**Cập nhật v2:** đã ban hành [protocol v2](T12_protocol_v2.md), giữ nguyên scoring/ngưỡng v1 và
tách cohort hoạt động lớn khỏi suy luận nhà đầu tư cá nhân. [Báo cáo v2](T12_v2_completion_report.md)
và gate `data/processed/t12/v2/t12_downstream_gate.json` là nơi xem nghiệm thu mới.
Phần dưới ghi lại raw/audit/v1; các phát biểu gate đóng bên dưới áp dụng cho v1.

**Hoàn thành kiểm tra số học và audit bổ sung; chưa đủ điều kiện dùng biến
WhaleFlow theo cohort hoặc diễn giải là nhà đầu tư cá nhân.** T14 có các nhánh
độc lập không bị gate này chặn. Phụ thuộc T07 đầy đủ và T09
trên T08 netted. Bảng bàn giao chỉ dùng Parquet; metadata dùng JSON.

Cập nhật 22/10/2026: đã thêm kiểm định độc lập cohort 655 ngày và gate theo bằng
chứng thực tế. Còn 79 địa chỉ overlap hạ tầng T07 hồi cứu và 40 địa chỉ cần thành
viên review; gate chưa mở. Xem [nghiệm thu cohort](T12_cohort_acceptance.md).

## Dân số và độ phủ nhãn theo USDT

| Bảng | Cửa sổ | Dòng node–cửa sổ | Qua bộ lọc | Bị loại |
|---|---:|---:|---:|---:|
| Ngày | 655 | 712.519 | 574.502 | 138.017 |
| Tuần | 94 | 388.557 | 338.313 | 50.244 |

Hai tuần thiếu ngày giữ để đối chiếu, không dùng làm quan sát hồi quy.
Trong 114.940 địa chỉ, 912 có định danh (0,7935%), 114.028 chưa có định danh.
Định danh dùng is_entity_attributed; biết is_contract không có nghĩa biết thực thể.

| Dân số toàn kỳ | Địa chỉ unique | Có định danh | Độ phủ định danh theo volume node |
|---|---:|---:|---:|
| Toàn mạng con | 114.940 | 912 | 44,5098% |
| Qua bộ lọc | 107.258 | 147 | 0,1365% |
| Bị loại | 7.682 | 765 | 79,6035% |

Volume node là tổng USDT vào + ra: khoảng 11.683,44 tỷ USDT, đếm mỗi transfer
hai đầu. Bộ lọc loại 55,8387% volume node; **99,8635% volume còn lại thuộc địa
chỉ chưa định danh**. Bộ lọc có tác dụng với nhãn đã biết, nhưng không đủ để
gọi dân số còn lại là nhà đầu tư.

Mẫu số transfer đếm mỗi cạnh một lần: khoảng 5.841,72 tỷ USDT. Cả hai đầu có
định danh chiếm 22,7353%; ít nhất một đầu 66,2843%; không đầu nào 33,7157%.
“Cả hai” và “ít nhất một” chồng nhau, không cộng chúng. Có ít nhất một đầu hạ
tầng theo cờ T07 chiếm 75,4555% transfer volume. Tổng Value node bằng hai lần
volume cạnh tại từng cửa sổ. Bảng coverage có ngày, tuần, tháng và toàn kỳ.

## Raw và log

Bản trước **chưa log**. Giữ công thức raw:
z(Value) + z(WeightedDegree) + z(PageRank), ddof=0 theo cửa sổ và dân số.
Value là USDT vào + ra; WeightedDegree là tổng transaction_count trên cạnh
vào + ra, không phải số transaction_hash unique của cả ví.

Biến thể cũ để đối chiếu:
z(log1p(Value)) + z(log1p(WeightedDegree)) + z(PageRank).
PageRank không log và không tính lại. Bảng whale_scores_* giữ raw; bảng
exploratory_scores_* giữ cả raw/log để không đổi ngầm ý nghĩa cột cũ.

| Cửa sổ | Spearman trung vị | Min–max Spearman | Giao nhau top 50 raw–log, trung vị |
|---|---:|---:|---:|
| Ngày | 0,952633 | 0,843235–0,978398 | 92% |
| Tuần | 0,927372 | 0,886743–0,946560 | 92% |

Trung vị z(Value) lớn nhất mỗi ngày giảm từ 15,336 xuống 4,067; mỗi tuần từ
29,884 xuống 4,739. Log giảm ảnh hưởng đuôi volume/tần suất, không chọn
theo kết quả T14/T15. Log không sửa được thiếu nhãn hoặc ảnh hưởng ngoại lệ
của PageRank. Spearman cao vẫn đi cùng thay đổi thứ hạng.

## Tương quan và ổn định

Trung vị Pearson giữa ba thành phần:

| Cửa sổ / bản | Value–tần suất | Value–PageRank | Tần suất–PageRank |
|---|---:|---:|---:|
| Ngày / raw | 0,627 | 0,803 | 0,697 |
| Ngày / log | 0,732 | 0,574 | 0,567 |
| Tuần / raw | 0,716 | 0,903 | 0,812 |
| Tuần / log | 0,809 | 0,477 | 0,504 |

Các thành phần không độc lập; cộng ba z-score có thể khuếch đại hoạt động chung.
Spearman thành phần ngày lần lượt khoảng 0,732/0,605/0,598, tuần
0,799/0,651/0,640; không đổi dưới log đơn điệu. Bảng giữ cả hai hệ số.

| Cửa sổ / bản | Jaccard top 50 liền kề, trung vị | Retention, trung vị |
|---|---:|---:|
| Ngày / raw | 0,2821 | 44% |
| Ngày / log | 0,2987 | 46% |
| Tuần / raw | 0,4706 | 64% |
| Tuần / log | 0,4706 | 64% |

Thống kê tuần chỉ lấy cặp hai tuần đầy đủ. Không suy thay đổi top 50 đồng nghĩa
mua/bán hoặc thay đổi tài sản.

## Top đầu và lọc hành vi

Chọn 20 địa chỉ có **nhiều ngày nằm top 10 nhất** cho mỗi bản raw/log; hòa thì
địa chỉ tăng dần. Hợp hai tập gồm 22 địa chỉ. Đây là mẫu kiểm tra tính dai dẳng,
không giả định có một điểm toàn kỳ cộng được qua ngày.
Xem [từng địa chỉ, nguồn và kết quả không xác định](T12_address_review.md).

AI ghi nhận ứng viên nhãn tổ chức cho 8/20 địa chỉ raw và 6/20 log. **Đây chưa
phải nhãn đã xác minh.** Ví dụ AI ghi nhận một kết quả tra cứu cho
0x18e296053cbdf986196903e889b7dca7a73882f6 tại
[báo cáo PoR Bybit tháng 6/2025](https://www.bybit.com/common-static/cht-static/por/Bybit_PoR_Audit_2025_Jun_19.pdf#page=14).
Thành viên nhóm cần mở nguồn và kiểm chứng trước khi chấp nhận liên hệ Bybit.
Địa chỉ này ở top 10 raw 454 ngày, chuỗi liên tục 191 ngày; các số hoạt động
không xác nhận quan hệ sở hữu hoặc nhãn tổ chức.

0x14681e4e26f1b5b5774ae3b7f694ff08bbbeb65c chưa xác định được thực thể, nhưng
ở top 10 raw 360 ngày; net/gross toàn kỳ khoảng 2,41e-11, gắn cờ chuyển tiếp
ứng viên 332 ngày. Đây là phát hiện hành vi, không xác nhận bot.

Prototype: net/gross <=5% và tần suất >= max(20, phân vị 95%) trong cửa sổ.
Đã thử chín tổ hợp ratio 1/5/10% và phân vị 90/95/99%. Mặc định gắn cờ trung
vị 11 địa chỉ/ngày, 120,5 địa chỉ/tuần, gồm trung vị 5/10 vị trí top ngày và
8/10 top tuần của cả raw/log. Đổi ngưỡng làm thay đổi kết quả; cờ không là
nhãn chuẩn. Profile giữ số ngày top 10, chuỗi liên tục, net/gross, tần suất
và cờ lặp lại trong bảy ngày quá khứ.

Bảng exploratory giữ prototype chuẩn hóa lại sau khi loại cờ chuyển tiếp;
đã bỏ việc loại theo nhãn AI chưa được người xác minh. **Chưa chấp nhận prototype làm cohort WhaleFlow**:
cần kiểm tra top sau lọc, tác động ngưỡng và định nghĩa dòng tiền kinh tế.
Không ghi đè T07 hoặc che dữ liệu raw. Review là desk review công khai bởi trợ
lý; không xác nhận danh tính khi nguồn không kết luận hoặc trang bị chặn.

## Kiểm định và tái lập

749/749 cửa sổ raw đạt đối chiếu nguồn, nhãn, cờ, dân số chuẩn hóa và rank.
Tham chiếu mới dùng math.fsum cho moment dân số, khác đường cộng pandas;
sai số score lớn nhất 2,84217e-14. Sáu bảng raw đã khớp hash hai lượt.
Audit log đạt 749/749 cửa sổ; 11/11 Parquet khớp SHA-256 giữa hai lượt;
kết quả lưu ở t12_audit_validation và t12_audit_reproducibility.

**23 pytest đã đạt trước khi dọn mã test**: nhóm rỗng, một node, std=0, đồng hạng,
dân số bị loại, đáp án tính tay, bất biến, log, coverage và ranh giới ngày.
Các kiểm tra chứng minh hợp đồng toán học và tính tái lập, không phải đánh giá
độc lập về ý nghĩa kinh tế hoặc quyền sở hữu. Không dùng “sai số bằng 0” để
chứng minh công thức đo đúng cá voi. Theo yêu cầu bàn giao mới nhất, đã xóa
cả mã pytest, dữ liệu giả và cache. Kết quả lịch sử/hash giữ trong t12_tests.json;
pipeline không coi những ca đã xóa là vừa chạy lại. Kiểm định dữ liệu thật vẫn giữ.

## Giới hạn và bàn giao

Đồ thị chỉ chứa transfer giữ lại sau netting và ngưỡng **500.000 USDT**:
“số giao dịch” chỉ đếm giao dịch lớn, không phải mọi giao dịch của địa chỉ.
Net/gross trên mạng bị cắt ngưỡng không thay số dư hoặc toàn bộ dòng tiền.
Transfer ERC-20 không luôn là dòng tiền kinh tế độc lập; vòng nhiều bước có
thể còn. Nhãn và profile toàn kỳ hồi cứu không phải thông tin point-in-time.
High-centrality chưa chắc là nhà đầu tư cá nhân.

Đầu ra ở data/processed/t12: sáu Parquet raw, 11 Parquet audit/exploratory,
cùng JSON summary/review/repro/tests/gate. Xem [đặc tả](T12_whale_score_specification.md).
Chạy T12_Whale_Score.py cho toàn bộ hoặc T12_Whale_Score_Audit.py khi raw không đổi.
Manifest cho phép lưu trữ thăm dò đã kiểm tra, ghi riêng
downstream_eligibility.cohort_whaleflow=false. Phát hành theo manifest; trạng thái
remote và receipt xác nhận lần upload, không suy từ việc tính toán đã xong.

Tên diễn giải: **địa chỉ hoạt động lớn chưa được định danh**. Gate WhaleFlow còn
đóng vì các ứng viên nhãn chưa được người xác minh và cohort sau lọc chưa được kiểm định.
Không dùng T12 hiện tại làm bằng chứng tài sản cá nhân hoặc biến WhaleFlow
của nhà đầu tư trước khi giải quyết các phát hiện này.

Review tiếp theo đã thêm log PageRank, cohort 30 ngày kết thúc t−1, quy tắc lọc
đóng băng và tách CEX/DEX. Xem [kết quả mới và coverage CEX](T12_lagged_cohort_and_CEX_report.md).
