# Quy ước dữ liệu dùng chung qua Hugging Face

Kho lưu trữ thống nhất: `team-crypto/Market-data-crypto-project` (dataset).
Mọi đường dẫn giữ cùng cấu trúc trên máy và Hugging Face, đọc từ `config/config.yaml`.
Tải đầu vào theo revision cố định; ghi repo/revision/hash để nhóm dùng đúng cùng bản.

## Bàn giao

Chạy tại thư mục `crypto`:

```powershell
& '../.venv/Scripts/python.exe' scripts/prepare_hf_manifest.py
```

`data/hf_release_manifest.json` là danh sách chính xác các file cần push trong
`upload_files`, gồm đường dẫn, SHA-256 và kích thước. Push manifest này cùng danh sách
`upload_files` (manifest không tự chứa hash của chính nó). Không cần copy sang thư mục
staging hoặc chọn thủ công trong `data/`. File `blocked_upload_files` là đầu ra
chưa được nghiệm thu hoặc không tương thích với đầu vào mới; chưa push các file đó.
`missing_files` chỉ ra các artifact bàn giao còn thiếu. Manifest không tự upload.
Bằng chứng review T09 có thể đi kèm release để nhóm biết bản remote cũ chưa khớp
T08 mới; các bảng chỉ số chưa đạt vẫn nằm trong blocked_upload_files.

Bảng dữ liệu chỉ dùng Parquet, báo cáo/metadata dùng JSON/Markdown. Ngoại lệ CSV
duy nhất là `eth_stats_from_2025.csv` ở gốc dự án. Không push service-account, key,
cache tải xuống, `__pycache__`, ảnh/HTML xem thử hoặc dữ liệu test tạm.
Sau khi kiểm tra đạt, xóa mã pytest/dữ liệu giả; không upload chúng lên dataset.

T07: bảng đầy đủ chuẩn là `t07_complete_wallet_labels.parquet`; bảng contracts và
summary đi kèm giúp kiểm tra nguồn thuộc tính is_contract. Các bảng Unknown vẫn
được giữ để không suy nhãn khi thiếu bằng chứng.

T08: cạnh ngày/tuần, metrics, validation, summary và báo cáo kiểm định là đầu ra chính.
Chạy tái lập lần hai trong `.cache/t08_repro_*`, lưu hash rồi tự dọn thư mục tạm;
không giữ bản duplicate trong `data/processed/graphs`.

T09: bảng node ngày/tuần và bảng tổng hợp cửa sổ ngày/tuần đều dùng Parquet. Chỉ bàn
giao bản đã khớp T08 netted hiện tại; không trộn T08 mới với T09 sinh từ đồ thị cũ.
Quy trình T09: chạy T09_Network_Centrality.py, scripts/validate_t09_current.py,
scripts/reproduce_t09.py, rồi tạo lại manifest. Bốn bảng phải khớp hash cả hai lần;
xem docs/T09_centrality_specification.md. Revision/hash remote cũ được lưu trong
replaces_remote_outputs của summary mới; không giữ bảng legacy trùng trong data/.

## Test và review

Theo yêu cầu bàn giao mới nhất: xóa cả mã pytest sau khi kiểm tra đạt.
Giữ kết quả lịch sử và SHA-256 mã đã chạy trong t12_tests.json; không trình bày
chúng như kiểm tra vừa thực thi lại. Không giữ bản chạy thứ hai trong data/.
Giữ bộ kiểm định dữ liệu thật đang được pipeline sử dụng (`src/t08_review.py`,
`src/t09_reference.py`, các lệnh nghiệm thu T09 và kiểm định tích hợp T10) để lần
chạy sau vẫn phát hiện sai dữ liệu. Validation Parquet và review JSON được giữ làm
bằng chứng nghiệm thu; đây là sản phẩm bàn giao, không phải dữ liệu test giả.

T10: chạy `T10_Heavy_Graph_Metrics.py` để tính và đối chiếu hai lần; cấu hình riêng
trong `config/t10.yaml` dùng cùng đường dẫn/lịch T08 từ `config/config.yaml`.
Đầu ra tại `data/processed/t10`; bảng sampling_quality công bố sai số xấp xỉ.
`--skip-reproducibility` chỉ dùng khảo sát, không đánh dấu sẵn sàng bàn giao.

T11: chạy `T11_Community_Concentration.py`, phụ thuộc T08 đã xác minh. Tính hai
lượt trong hai tiến trình, so hash tám Parquet và kiểm định độc lập đủ 749 cửa
sổ trước khi bật ready. Bàn giao node/snapshot ngày–tuần, validation, top
community, regime hồi cứu, comparison và ba JSON summary/review/reproducibility.
Bốn PNG Matplotlib chuẩn ở data/figures/t11 được bàn giao trên HF bằng allowlist
cùng Parquet/JSON; ảnh thử và cache bị loại. RQ4 chỉ mô tả ngày volume cao, chưa xác nhận stress thị
trường. Các nhãn pre và phân vị toàn kỳ không dùng làm predictor PIT.
Xem docs/T11_community_concentration_specification.md và T11_completion_report.md.

Sau khi push một release, các thành viên lấy đúng revision đã công bố rồi kiểm tra
hash theo manifest. Việc upload dữ liệu là một bước riêng, không diễn ra khi test.

Khi được yêu cầu xuất bản: đăng nhập `hf auth login`, chạy
`scripts/prepare_hf_manifest.py` rồi `scripts/publish_hf_release.py`.
Publisher chỉ upload allowlist, kiểm tra hash trên remote và lưu receipt tại
`.release/hf_publish_receipt.json`; không xóa các file remote khác.
GitHub chỉ lưu code/config/tài liệu; dữ liệu và receipt được `.gitignore` loại bỏ.
File nguồn raw Parquet thật cũng nằm trong allowlist và phải khớp hash nguồn T08;
không coi con trỏ Git LFS 134 byte là dữ liệu nguồn hợp lệ.

T12: chạy `T12_Whale_Score.py`; phụ thuộc T07 đầy đủ và T09 trên T08 mới.
Cấu hình `config/t12.yaml`, bảng Parquet và bằng chứng tại `data/processed/t12`.
WhaleScore dùng z theo từng cửa sổ; bảng all và ranking qua bộ lọc có dân số
chuẩn hóa riêng. Qua bộ lọc không có nghĩa đã xác nhận nhà đầu tư cá nhân.
Sau nghiệm thu, tạo lại manifest rồi mới chạy publisher khi cần xuất bản.

T12 hiện là điểm thăm dò. Lệnh đầy đủ chạy raw rồi audit; có thể chạy riêng
`T12_Whale_Score_Audit.py` nếu raw đã được nghiệm thu và không đổi. Audit xuất
độ phủ theo USDT, so sánh raw/log, tương quan, ổn định top 50, hành vi và bằng
chứng rà soát 20 địa chỉ cho mỗi biến thể. 23 pytest đã đạt trước khi xóa mã.
Những lần chạy audit sau vẫn kiểm định dữ liệu thật và so hash hai lượt;
không còn chạy lại các ca giả đã xóa.
Manifest chấp nhận T12 để lưu trữ thăm dò không có nghĩa biến WhaleFlow được dùng:
xem `downstream_eligibility` và `data/processed/t12/t12_downstream_gate.json`.
Hiện gate WhaleFlow false; cần kiểm định cohort sau lọc. T14 CEX NetFlow, sự kiện
transfer lớn theo phân vị quá khứ và tập trung mạng có thể triển khai độc lập.

Bổ sung protocol `t12_lagged_v1`: cohort top 50 từ 30 ngày [t−30,t), log cả
PageRank; không dùng volume cùng ngày hoặc nhãn thực thể cuối kỳ cho dự báo.
`config/t12_design.yaml` và `t12_protocol_freeze.json` cố định ngưỡng trước T15.
Chạy audit sẽ tạo cả cohort và CEX diagnostics, so hash hai lượt rồi dọn bản tạm.
Không đổi ngưỡng theo p-value/hệ số hồi quy; thay đổi phải version protocol.

T07 lưu `t07_label_review_candidates.parquet` (AI, chưa xác minh) và
`t07_secondary_verified_labels.parquet` (sidecar nguồn bậc hai, ban đầu rỗng).
Thành viên mở nguồn, điền quyết định trong Parquet rồi chạy
`python T07_Secondary_Label_Review.py --decisions <relative-path.parquet>`.
Không coi tên do AI tìm thấy là nhãn đã kiểm chứng; chỉ nhập bản approve có
người, thời điểm, URL, confidence và xác nhận đúng địa chỉ Ethereum.
Sau quyết định phải chạy lại audit/design/manifest; không sửa ngầm complete T07
đã ký hash. T07_Complete_Wallet_Labels.py đọc sidecar khi rebuild; nếu hợp nhất
vào complete, version/rebuild các bước phụ thuộc trước khi tạo release mới.

CEX NetFlow chỉ dùng CEX, loại DEX khỏi tập ví sàn, tách chuyển nội bộ CEX.
`cex_coverage.parquet` đo tỷ trọng volume của ví CEX đã biết, không đo recall
CEX thật vì Unknown có thể còn ví sàn. Nhãn hiện tại dùng mô tả hồi cứu;
forecast RQ3 cần nhãn PIT. Xem T12_lagged_cohort_and_CEX_report.md.

## T14: scoped release và input theo revision

Chuẩn bị manifest bằng `python scripts/prepare_t14_release.py --input-revision <revision-input>`
sau khi commit source/config đã nghiệm thu. Script xác minh gate t14_inputs_v1, tất cả artifact và
bytes của source/config trong commit, rồi ghi `data/hf_t14_release_manifest.json`. Không tự upload.

Root manifest ghi `code_git_commit` và `remote_dependencies`, mỗi dependency có thể có revision riêng.
Khi tải để tái lập, lấy source theo code_git_commit; output/config theo revision receipt phát hành;
input theo revision của từng remote_dependency, ghi vào đúng path và kiểm tra SHA-256.
Không mặc định input luôn là bản latest: output đã kiểm định có thể dùng snapshot nguồn bất biến trước đó.
Bản T14 này ghim nguồn ở de42b5dc4e5c3d63161b38ad4f528d97c47f5068; đặc biệt market daily
đã được kiểm định có hash 540b408c..., khác cách lưu/rounding của bản latest 1682966f....
Không ghi đè nguồn chung để buộc các release khác cùng hash.

Sau khi tải, chạy `python scripts/validate_t14_release.py`. Publisher hỗ trợ dependency revision và
chỉ thay artifact trong upload_files; receipt sau upload là bằng chứng revision thực tế. Các cờ input-ready
không chứng nhận danh tính cá nhân hoặc RQ3 đã được trả lời.