# T12 — Whale Score theo node và cửa sổ

Chạy `T12_Whale_Score.py` ở gốc dự án. Cấu hình riêng `config/t12.yaml` giữ
nguyên config đã ký hash của T09/T10. Chỉ đọc T07 đầy đủ và T09 trên T08 netted
đã nghiệm thu; kiểm tra hash, lịch, code và cấu hình nguồn trước/sau tính.
T12 không cần T10 hoặc T11.

## Ba thành phần

Với mỗi node hoạt động trong một cửa sổ ngày UTC hoặc tuần ISO:

`WhaleScore = z(Value) + z(WeightedDegree) + z(PageRank)`.

| Thành phần | Cột T09 mặc định | Ý nghĩa |
|---|---|---|
| Value | weighted_degree_usdt | Tổng USDT ròng của các transfer vào + ra node trong cửa sổ |
| WeightedDegree | weighted_degree_tx | Tổng transaction_count trên các cạnh vào + ra |
| PageRank | pagerank | PageRank có hướng, trọng số USDT của toàn bộ mạng T09 |

Phân biệt quy mô tiền và tần suất để tránh đưa cùng volume vào công thức hai
lần. WeightedDegree ở đây là trọng số tần suất, không phải số đối tác hoặc số
transaction_hash duy nhất của cả ví: một transaction qua nhiều cạnh có thể
được đếm trên nhiều cạnh. Value là volume tham gia, không phải số dư, tài sản
hay giá trị nắm giữ của ví. Tổng volume node vào + ra đếm hai đầu mỗi transfer.
T07 chỉ cung cấp nhãn, không dùng volume toàn kỳ của T07 để chấm điểm cửa sổ.

`z(x) = (x - mean(x)) / std(x, ddof=0)`, tính riêng theo cửa sổ. Bản raw gốc
không log, winsorize hoặc thêm trọng số ngoài công thức. Nếu std=0, thành phần z=0 và
is_degenerate=true trong bảng standardization. Nhóm rỗng không thêm node giả;
nhóm chỉ một node có score=0 và rank=1. Không cộng/so điểm như thước đo tài sản
tuyệt đối giữa các ngày: mỗi cửa sổ có dân số và chuẩn hóa riêng.

## Hai dân số và quy tắc gắn cờ

Giữ mọi node T09 trong cùng bảng, ghép nhãn many-to-one theo địa chỉ lowercase:

- `whale_score_all`, `z_*_all`, `rank_all`: chuẩn hóa trên mọi node hoạt động,
  bao gồm hạ tầng, để đối chiếu ảnh hưởng của bộ lọc.
- `whale_score`, `z_value`, `z_weighted_degree`, `z_pagerank`, `whale_rank`:
  chuẩn hóa lại trên nhóm `eligible_for_whale_ranking=true`. Node bị loại có
  các cột này là null, có `exclusion_reason`; không gán điểm 0 cho node bị loại.

Loại khỏi dân số xếp hạng chính nếu bất kỳ điều kiện nào đúng:
exchange (CEX hoặc DEX), bridge, contract, địa chỉ zero, nhãn có xung đột cần
review, thiếu dòng nhãn, hoặc chưa biết trạng thái contract. Các cờ exchange và
bridge dùng entity_type, class, public_category từ T07, không suy từ centrality
hay tên ví mơ hồ. Contract dùng cả trạng thái BigQuery và nhãn Contract.
Cờ có thể chồng nhau; tổng các cờ không bằng số node bị loại duy nhất.

`flag_other_attributed_entity` giữ dấu các nhãn khác. Mặc định không loại tất
cả nhãn khác; có thể bật `exclude_other_attributed_entities` để sàng lọc chặt
hơn. `flag_unattributed=true` nghĩa chưa có định danh, không chứng minh là EOA
của cá nhân. `eligible_for_whale_ranking` chỉ có nghĩa qua bộ lọc đã nêu.

PageRank vẫn là PageRank gốc của mạng T09, kể cả tương tác với exchange/bridge;
lọc dân số xếp hạng không có nghĩa tính lại đồ thị hoặc PageRank.

Nhãn T07 được dùng tĩnh và hồi cứu theo bản cuối kỳ. Trạng thái contract là
creation record trước kết thúc nghiên cứu, không phải current bytecode hoặc
quyền sở hữu kinh tế. Nhãn này không phải bằng chứng point-in-time cho từng
ngày lịch sử; không dùng kết quả như mô hình dự báo tránh được look-ahead.

**High-centrality chưa chắc là nhà đầu tư cá nhân.** Score cao chỉ mô tả
hoạt động và vị trí trong mạng transfer cá voi ≥500.000 USDT. Ví lưu ký,
dịch vụ, MEV, tổ chức chưa có nhãn hoặc ví của nhiều người vẫn có thể qua bộ
lọc. Không có cột tự động xác nhận cá nhân, không suy tài sản hoặc chủ sở hữu.

## Đầu ra và nghiệm thu

Trong `data/processed/t12/`:

- whale_scores_daily/weekly.parquet: khóa window_type,time_window,address;
  thành phần gốc, z, score, rank, nhãn, cờ, lý do loại và metadata cửa sổ.
- snapshot_metrics_daily/weekly.parquet: đủ 655/94 cửa sổ, số node qua/bị loại,
  số node theo từng cờ. Tuần đầu/cuối giữ eligible_for_regression=false.
- t12_standardization.parquet: mean/std/ddof, quy mô dân số, cột nguồn và cờ
  suy biến cho từng thành phần, cửa sổ và dân số all/eligible.
- t12_validation.parquet: một dòng mỗi cửa sổ, bảo toàn node và sai số z.
- t12_summary.json, t12_review.json, t12_reproducibility.json: provenance,
  định nghĩa, kiểm định độc lập và hash hai lượt.

Kiểm định số học tham chiếu dùng `math.fsum` đối chiếu z/score, rank đồng hạng, tham số chuẩn
hóa, join nhãn và các cờ; mọi cột gốc T09 phải còn nguyên. Cùng điểm có cùng
minimum rank; địa chỉ sắp xếp ổn định để đọc bảng, không phá đồng hạng.
Chương trình tính hai lượt, so SHA-256 cả sáu bảng, tự xóa bản đối chiếu trong
cache. Kiểm định số học không chứng minh địa chỉ thuộc nhà đầu tư cá nhân.
Theo yêu cầu bàn giao mới nhất, xóa mã pytest sau khi đạt; giữ bằng chứng lịch
sử trong t12_tests.json và kiểm định dữ liệu thật, không tự nhận đã chạy lại ca giả.
Thay cấu hình phải chạy lại và tạo lại manifest. Không tự upload hoặc push code.

## Audit ý nghĩa và độ nhạy

Chạy toàn bộ bằng `T12_Whale_Score.py`; nếu các bảng raw không đổi, chỉ chạy
`T12_Whale_Score_Audit.py`. Cấu hình audit: `config/t12_audit.yaml`.

Biến thể cũ để đối chiếu (PageRank còn thô):

`score_log1p = z(log1p(Value)) + z(log1p(WeightedDegree)) + z(PageRank)`.

Log tự nhiên, đầu vào USDT và số đếm ở đơn vị gốc; PageRank giữ nguyên. Chuẩn hóa
ddof=0 lại trong cùng dân số eligible mỗi cửa sổ, không lấy log của z-score.
Bảng `whale_scores_*` giữ công thức raw; `exploratory_scores_*` chứa cả hai để
tránh đổi ngầm ý nghĩa cột cũ. Log giảm ảnh hưởng đuôi volume/tần suất; không
khắc phục nhãn thiếu, sự tương quan giữa các thành phần hay thiên lệch PageRank.
Spearman raw–log dùng mọi node eligible, xử lý đồng hạng theo scipy; nhóm không
đủ biến thiên trả null. Top-k dùng score giảm dần rồi địa chỉ tăng dần để chọn
đúng k; quy tắc này chỉ cắt tập top-k, không thay minimum rank của điểm đồng hạng.

Độ phủ định danh dùng `is_entity_attributed` của T07; biết is_contract không có
nghĩa biết thực thể. Báo cáo ngày/tuần/tháng/toàn kỳ, cho all/eligible/excluded:
địa chỉ unique và tỷ lệ sum(Value) thuộc địa chỉ định danh. Sum(Value) đếm hai
đầu transfer. Bảng `t12_transfer_coverage` dùng tổng total_value cạnh, đếm mỗi
transfer một lần: cả hai đầu, ít nhất một đầu và không đầu nào có định danh.
Tổng Value của node được đối chiếu bằng hai lần tổng volume cạnh từng cửa sổ.

Kiểm tra ba cặp z-score bằng Pearson và Spearman, raw và log. Độ ổn định top 50
giữa cửa sổ kế tiếp: Jaccard=intersection/union; retention=intersection/top-k
cửa sổ trước. Thống kê tuần dùng cặp có cả hai tuần đầy đủ; giữ các cặp tuần
thiếu trong bảng để đối chiếu. Không diễn giải sự ổn định cao là bằng chứng cá nhân.

Cờ chuyển tiếp ứng viên trong từng cửa sổ:
`abs(in-out)/(in+out) <= 0.05` và tần suất >= max(20, quantile_0.95).
Thử độ nhạy ratio 0.01/0.05/0.10 và quantile 0.90/0.95/0.99, chín tổ hợp
mỗi cửa sổ. Cờ bền vững khi có ít nhất ba ngày gắn cờ trong bảy ngày lịch đến
ngày hiện tại; ngày vắng tính zero, không dùng ngày tương lai. Profile toàn kỳ
chỉ dùng mô tả hồi cứu. Vị thế ròng gần zero không chứng minh ví trung chuyển:
đồ thị đã cắt ngưỡng, không có số dư hay toàn bộ giao dịch nhỏ.

Prototype `eligible_postscreen_prototype` chỉ loại ứng viên chuyển tiếp,
rồi chuẩn hóa lại bản log. Nhãn do AI tra cứu không tham gia bộ lọc. Đây
chỉ là thử độ nhạy, chưa được chấp nhận làm dân số nhà đầu tư cho WhaleFlow.
Không suy bot hoặc chủ sở hữu từ tần suất. Tra cứu AI chỉ là hàng chờ xác minh
trong T07, không phải nhãn mới hoặc phân loại độc lập của T12.

Rà soát công khai chọn 20 địa chỉ có số ngày nằm top 10 nhiều nhất cho mỗi
biến thể raw/log (hòa thì địa chỉ tăng dần); lấy hợp hai tập và xem từng địa chỉ.
Nguồn, ngày, mức bằng chứng, lookup không kết luận được đều giữ trong
`t12_address_review.parquet` và báo cáo Markdown. Đây là desk review bởi trợ lý,
không thay việc nhóm xác minh quyền sở hữu. Nhãn ở chain khác chỉ là gợi ý.

**Giới hạn đầu vào:** “số giao dịch” chỉ đếm giao dịch lớn trên các cạnh giữ lại
sau netting và áp ngưỡng 500.000 USDT; không phải tổng số giao dịch của ví.
Value là volume ròng theo từng cặp trong transaction, không phải net inflow ví.
Các transfer nhỏ và vòng nhiều bước chưa được mô hình hóa đầy đủ, nên số đo
hành vi và centrality chỉ mô tả mạng con này.

Đầu ra bổ sung gồm 11 Parquet diagnostic/exploratory và JSON audit/repro/tests/gate.
Các bài pytest đã kiểm tra đáp án tính tay, nhóm rỗng, một nút, std=0, đồng hạng, dân số
bị loại, hoán vị, log, mẫu số coverage và ranh giới bảy ngày. Hai lượt khớp hash
chứng minh tính tái lập; không chứng minh công thức đo đúng tài sản/nhà đầu tư.
Mã pytest đã được xóa sau khi đạt theo yêu cầu bàn giao; kết quả này là lịch sử.

`ready_for_exploration` cho phép chia sẻ kết quả đã kiểm tra. Gate chỉ chặn biến
WhaleFlow theo cohort, không chặn toàn T14. CEX NetFlow, sự kiện transfer lớn
theo phân vị quá khứ và tập trung mạng là các nhánh độc lập. Chỉ xây WhaleFlow sau khi xử lý
các phát hiện và kiểm định cohort mới. Tên diễn giải phù hợp: **địa chỉ hoạt động
lớn chưa được định danh**, không gọi mặc định là cá voi cá nhân.

## Biến thể log PageRank và cohort t−1 (protocol v1)

Biến thể ưu tiên mới: `score_log_all = z(log1p(Value)) +
z(log1p(WeightedDegree)) + z(log(PageRank))`. Dùng log tự nhiên; PageRank không
tính lại. Floor số dương nhỏ nhất float64 nếu PR=0 để tránh log(0); PR thực tế
có teleportation nên dương. Không dùng log1p(PR) vì với xác suất rất nhỏ phép
biến đổi đó gần tuyến tính. Giữ raw và bản chỉ log Value/tần suất để so sánh.
Audit xuất Spearman cả ba cặp, Pearson/Spearman thành phần và ổn định top 50
cho ba biến thể; kiểm tra số học tham chiếu cho cả hai bản log.

Cohort cho ngày t dùng duy nhất 30 ngày UTC `[t−30, t)`. Cộng volume vào/ra và
tần suất; PageRank là trung bình 30 snapshot ngày, ngày không hoạt động góp zero.
Đây không phải PageRank tính trên đồ thị gộp 30 ngày. Chỉ những node đã xuất
hiện trong 30 ngày trước được xem xét; thông tin ngày t không vào score/bộ lọc.
Không tạo cohort ở 30 ngày đầu thiếu lịch sử. Chọn top 50 score sau lọc, hòa thì
địa chỉ tăng dần; không dùng score cùng ngày để dự báo cùng ngày.

Đóng băng tại `config/t12_design.yaml`, protocol `t12_lagged_v1`:
net/gross 30 ngày <=0.05 và tần suất 30 ngày >=max(20, phân vị 0.95) bị loại.
Chuẩn hóa log-all lại sau lọc. Loại zero, contract có first_contract_timestamp
trước t (thông tin on-chain lịch sử), và nhãn thực thể đã được người xác minh
có cả label_available_at và effective_from trước t. Không sử dụng cờ entity
tĩnh cuối kỳ của T07 trong cohort dự báo. Nhãn Other đã xác minh cũng bị loại
để tránh đưa tổ chức/dịch vụ đã biết vào cohort ứng viên cá nhân.

`t12_protocol_freeze.json` giữ SHA-256 cấu hình. Mã từ chối cấu hình khác hash,
không đọc kết quả T15 để chọn ngưỡng. Muốn đổi phải tạo protocol mới và ghi
deviation, giữ kết quả v1. Chín tổ hợp chỉ báo độ nhạy trên cùng dữ liệu quá khứ,
không chọn lại theo hệ số/p-value hồi quy. Cờ bảy ngày trước đây chỉ là mô tả
audit; không thêm ngầm vào bộ lọc cohort v1.

`cohort_members_daily.parquet` giữ thành viên, score và information_cutoff;
`cohort_snapshot_daily.parquet` giữ đủ ngày, warm-up, số ứng viên/bị loại và
Jaccard; `cohort_filter_sensitivity.parquet` so tập top 50 ở chín cấu hình với
cấu hình đã đóng băng. Cơ chế thời gian đúng không xác minh được chủ sở hữu;
cohort vẫn là prototype, chưa được dùng làm WhaleFlow.

## Nhãn bậc hai và CEX

Mọi tra cứu AI nằm trong `data/processed/t07/t07_label_review_candidates.parquet`
với verification_status=pending_human_review. `review_organization_tag=false`
trong T12; candidate_organization_claim chỉ mô tả nội dung AI tìm được.
Không loại node hoặc tăng coverage định danh bằng các ứng viên này.

Một thành viên phải mở từng URL, xác nhận đúng địa chỉ Ethereum và thực thể,
chọn CEX/DEX/Bridge/Other/... và confidence low/medium/high, ghi verified_by,
verified_at, label_available_at, effective_from, đặt source_opened_by_human và
ethereum_address_confirmed=true, decision=approve trong một Parquet quyết định.
Chạy `T07_Secondary_Label_Review.py --decisions <đường-dẫn-tương-đối.parquet>`.
Chương trình kiểm tra metadata, không tự xác minh nguồn thay con người; từ chối
backdate ngày khả dụng trước ngày xác minh. T07 lưu sidecar
`t07_secondary_verified_labels.parquet`, source_tier=2, dùng chung cho các bước.
Không ghi đè bảng T07 đã ký hash và không nhận ứng viên AI thành nhãn mặc định.
T07_Complete_Wallet_Labels.py tự đọc sidecar đã xác minh khi rebuild; hàng chờ
AI không được đọc vào complete. Muốn hợp nhất phải version/rebuild T07 và các
bước phụ thuộc, không sửa file complete đang được bản T08/T09 cũ tham chiếu.

NetFlow RQ3 chỉ lấy entity_type=CEX, không lấy generic exchange hoặc DEX;
label_conflict_review bị loại. Coverage CEX xuất ngày/tháng/toàn kỳ với mẫu số
volume endpoint và transfer đếm một lần. Chỉ số này là tỷ trọng volume được
nhãn CEX bao phủ, **không phải recall của tất cả ví CEX thật**. Không biết bao
nhiêu Unknown thực ra là CEX. Giữ confidence, URL và ngày tải trong inventory.

`CEX NetFlow = external_in − external_out`: chuyển giữa hai ví CEX đã biết
không vào in/out, ghi cex_internal riêng. Đây là tổng NetFlow nhóm CEX; không
phải số dư sàn hoặc dòng tiền toàn mạng. Chuyển CEX–DEX vẫn là chuyển qua ranh
giới nhóm CEX, nhưng router DEX không được coi là ví sàn tập trung.
Nhãn hiện tại chỉ hỗ trợ mô tả hồi cứu; RQ3 dự báo PIT cần lịch sử nhãn.

Nhánh T14 khác được phép phát triển song song: sự kiện transfer vượt phân vị
ước lượng từ quá khứ (không dùng phân vị toàn kỳ cho dự báo), tập trung mạng
từ T08. Đợt này bàn giao CEX NetFlow/coverage, không tự nhận đã hoàn thành mọi
biến T14. Các cờ ready_for_t14_t15 cũ chỉ giữ tương thích; đọc
ready_for_cohort_whaleflow và t14_independent_branches_allowed để biết phạm vi.
