# T12 — Log PageRank, cohort t−1 và nhánh CEX độc lập

Review ngày 21/10/2026. T12 là điểm thăm dò; gate chỉ chặn **WhaleFlow theo
cohort**, không chặn toàn bộ T14. Chưa có kết quả hồi quy T15 được dùng chọn
quy tắc; cấu hình đã được cố định trước bước đó.

## Log PageRank

Đã thêm score_log_all = z(log1p(Value)) + z(log1p(WeightedDegree)) +
z(log(PageRank)), giữ cả raw và bản chỉ log Value/tần suất. Không tính lại
PageRank; log là biến đổi đơn điệu. Không dùng log1p(PageRank) vì với xác suất
nhỏ phép đó gần tuyến tính. Floor float64 dương chỉ để tránh log(0).

Bảng t12_rank_sensitivity giữ Spearman raw–log_all và log1p–log_all, cùng mức
giao nhau top 50; correlation và stability có cả ba biến thể. Log-all là lựa
chọn thăm dò/cohort v1, không được chọn theo kết quả hồi quy. Log giảm ảnh
hưởng đuôi, không xác minh danh tính hoặc loại được mọi dạng hạ tầng.

| So sánh điểm, Spearman trung vị | Ngày | Tuần |
|---|---:|---:|
| Raw – log Value/tần suất | 0,952633 | 0,927372 |
| Raw – log cả PageRank | 0,987020 | 0,982930 |
| Log Value/tần suất – log cả PageRank | 0,982024 | 0,974117 |
| Giao nhau top 50 raw – log cả PageRank | 92% | 90% |

Pearson Value–PageRank trung vị khi log cả hai là 0,710/ngày và 0,773/tuần:
cao hơn bản chỉ log Value (0,574/0,477), thấp hơn raw (0,803/0,903). Không
diễn giải log toàn bộ là làm các thành phần độc lập hoặc cải thiện dự báo.
Chọn log-all để giảm đuôi trên cả ba thành phần theo một quy tắc chung trước
T15, không tối ưu tương quan. Jaccard top 50 cùng-ngày liền kề của log-all
vẫn chỉ 0,299/ngày và 0,471/tuần; vì vậy cần đo riêng cohort 30 ngày quá khứ.

## Nhãn AI không phải nhãn đã xác minh

Tất cả 22 bản ghi tra cứu AI là **pending_human_review**. Việc từng tìm thấy
chuỗi địa chỉ trong một nguồn không được coi là xác nhận nhãn hoặc quyền sở
hữu; kể cả ứng viên liên quan Bybit. Đã bỏ việc loại node theo những ứng viên
này. T12 dùng phân loại T07 hiện tại; không có hệ phân loại AI riêng để lọc.

Hàng chờ chung: data/processed/t07/t07_label_review_candidates.parquet.
Một thành viên mở từng URL, xác nhận địa chỉ Ethereum và thực thể, điền
entity_type, confidence, verified_by, verified_at, label_available_at,
effective_from, source_opened_by_human=true, ethereum_address_confirmed=true,
decision=approve trong Parquet quyết định. Nhập bằng:

```powershell
python T07_Secondary_Label_Review.py --decisions <relative-path.parquet>
```

Metadata thiếu hoặc backdate ngày khả dụng trước ngày xác minh bị từ chối.
Chương trình không tự xác minh con người hay nguồn; đó là xác nhận do thành
viên chịu trách nhiệm. Kết quả vào t07_secondary_verified_labels.parquet,
source_tier=2, nguồn dùng chung cho T07/T12. Sidecar ban đầu rỗng; không ghi đè
complete T07 đã ký hash. Muốn hợp nhất vào complete phải version/rebuild T07
và các bước phụ thuộc. Sau quyết định cần chạy lại audit/design/manifest.

## Cohort dự báo dùng đến t−1

Ngày t dùng cửa sổ UTC [t−30,t), cộng Value/tần suất và trung bình PageRank
theo 30 ngày lịch; ngày vắng góp zero. Không dùng score ngày t, không lấy trung
bình có điều kiện chỉ trên ngày hoạt động. Đây không phải PageRank trên đồ
thị gộp 30 ngày. Chỉ chọn địa chỉ đã có hoạt động trong cửa sổ quá khứ.

Không tạo cohort ở 30 ngày đầu; sau warm-up lấy tối đa 50 địa chỉ. Lọc zero,
contract có thời điểm tạo on-chain trước t và nhãn thực thể được người xác
minh có ngày khả dụng/effective_from trước t. **Không dùng nhãn thực thể tĩnh
cuối kỳ T07 để hồi tố cohort dự báo.** Với nguồn hiện tại chưa có lịch sử nhãn
người xác minh, không thể xem cohort là tập nhà đầu tư đã loại hết hạ tầng.

Quy tắc v1 cố định: loại net/gross 30 ngày <=5% nếu tần suất 30 ngày >=
max(20, phân vị 95%) của ứng viên; log-all chuẩn hóa lại sau lọc. Hòa điểm
chọn địa chỉ tăng dần. Ngưỡng giữ mặc định trước đó để có một protocol rõ,
không tối ưu theo T15. Chín tổ hợp ratio 1/5/10% × phân vị 90/95/99% chỉ là
độ nhạy; không chọn lại sau khi xem hệ số hoặc p-value hồi quy.

config/t12_design.yaml và t12_protocol_freeze.json giữ protocol/hash. Mã từ
chối đổi cấu hình đã đóng băng; cần protocol mới và báo cáo deviation nếu đổi.
Cohort có thông tin cutoff, warm-up, Jaccard và độ nhạy trong Parquet riêng.
Độ ổn định cao hơn cũng không phải chứng minh danh tính hoặc năng lực dự báo.

Kết quả: 30 ngày warm-up, 625 ngày đủ lịch sử, 50 thành viên mỗi ngày đủ lịch
sử (31.250 dòng). Jaccard cohort liền kề trung vị **0,8182**, so với khoảng
0,299 của top 50 score cùng-ngày. Hai dân số/cách chuẩn hóa khác nhau nên đây
là đối chiếu mô tả, không chứng minh cửa sổ 30 ngày tối ưu. Không có nhãn thực
thể đã được người xác minh và khả dụng trước t trong kỳ dữ liệu hiện tại.

| Phân vị tần suất | Net/gross | Số bị loại trung vị | Jaccard với cấu hình cố định, trung vị |
|---|---:|---:|---:|
| 90% | 1% | 402 | 0,3333 |
| 90% | 5% | 552 | 0,9231 |
| 90% | 10% | 621 | 0,3699 |
| 95% | 1% | 268 | 0,3333 |
| 95% | 5% | 376 | 1,0000 |
| 95% | 10% | 424 | 0,4085 |
| 99% | 1% | 48 | 0,2500 |
| 99% | 5% | 72 | 0,3699 |
| 99% | 10% | 85 | 0,2195 |

**Thành viên cohort nhạy với quy tắc lọc.** Sự ổn định theo thời gian cao hơn
không bù được độ nhạy này; tiếp tục gate WhaleFlow và giữ toàn bộ chín kết quả.

## T14 và RQ3: CEX khác DEX

T07 có 465 CEX và 54 DEX trong nhóm 519 địa chỉ exchange trước đây. CEX
inventory dùng entity_type=CEX và không có xung đột nhãn; generic exchange
không tự chuyển thành CEX. Cả 465 CEX có hoạt động trong đồ thị. Confidence
nguồn T07: 333 high/High, 132 medium; không có nghĩa tất cả đã được thành viên
xác minh trong workflow mới. Giữ URL và ngày tải để review.

| Chỉ số toàn kỳ | Giá trị |
|---|---:|
| Tỷ trọng volume node thuộc CEX đã biết (vào + ra) | 33,9824% |
| Tỷ trọng transfer có ít nhất một đầu CEX đã biết, đếm một lần | 50,5130% |
| Vào tập CEX từ ngoài tập ví CEX đã biết | 971,217 tỷ USDT |
| Ra khỏi tập CEX đã biết | 960,118 tỷ USDT |
| NetFlow = vào − ra | +11,099 tỷ USDT |

Chuyển giữa hai CEX đã biết bị loại khỏi external in/out, giữ cex_internal
riêng. DEX router không thuộc tập CEX; chuyển CEX–DEX vẫn vượt ranh giới tập
CEX. Đây là NetFlow nhóm ví CEX đã biết trong mạng transfer lớn, không phải
số dư sàn hoặc mọi dòng tiền của mọi CEX.

**Các tỷ lệ trên không phải recall CEX thật.** Unknown có thể còn CEX; khi đó
chuyển nội bộ sàn qua ví Unknown có thể bị tính thành external flow. Mạng
đã netting và cắt ngưỡng 500.000 USDT, bỏ giao dịch nhỏ và có thể còn vòng
nhiều bước. RQ3 cần review các đối tác Unknown lớn và báo độ nhạy nhãn; không
thể kết luận nhận dạng tốt chỉ từ tỷ trọng volume đã đo.

Nhãn hiện tại là hồi cứu, không có ngày khả dụng lịch sử cho mọi CEX. Vì vậy
NetFlow đủ để mô tả nhóm ví được gắn nhãn hiện tại, **chưa đủ cho khẳng định
dự báo PIT RQ3**. Coverage có ngày/tháng/toàn kỳ; NetFlow có đủ ngày, kể cả zero.

T14 được phát triển song song ở ba nhánh độc lập: CEX NetFlow, sự kiện transfer
lớn vượt phân vị quá khứ và tập trung mạng. Đợt này bàn giao CEX diagnostics,
không nhận đã hoàn thành toàn bộ T14 hoặc hồi quy. Phân vị dự báo phải dùng
dữ liệu quá khứ, không ước lượng từ toàn kỳ. Chỉ WhaleFlow theo cohort còn gate.

## Kiểm tra và bàn giao

23 pytest đã đạt trước khi dọn mã, gồm log PageRank tính tay, loại DEX khỏi CEX, bỏ chuyển nội bộ,
nhãn chưa khả dụng và thay dữ liệu ngày t/tương lai mà cohort đến ngày t không
đổi. Theo yêu cầu bàn giao mới nhất, mã pytest và dữ liệu giả đã được xóa;
giữ t12_tests.json làm bằng chứng lịch sử, không còn thực thi các ca giả khi
chạy audit. Kiểm định dữ liệu thật vẫn giữ. Audit so hai lượt cho 11 Parquet; design so hai
lượt cho 7 Parquet mới: **11/11 audit và 7/7 design khớp SHA-256**. Audit đạt
749/749 cửa sổ, design đạt 655/655 ngày. JSON proof giữ hash; không dùng sự tái lập thay bằng
chứng công thức đo được nhà đầu tư. Dữ liệu/cache đối chiếu được dọn.

Chạy T12_Whale_Score_Audit.py khi raw T12 không đổi, hoặc T12_Whale_Score.py
cho cả raw. Chỉ tạo manifest sau khi audit/design đạt. Bảng đầu ra dùng Parquet,
metadata JSON; lệnh kiểm tra không tự upload. Phát hành dùng publisher riêng
theo manifest và lưu receipt sau khi đối chiếu hash remote.
