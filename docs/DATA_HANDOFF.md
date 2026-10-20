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
cache tải xuống, `__pycache__`, ảnh/HTML xem thử hoặc thư mục test.

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

Theo quy ước thống nhất: mã test với dữ liệu giả và dữ liệu test tạm được xóa sau
khi kiểm tra đạt, áp dụng cả các bước trước. Không giữ bản chạy thứ hai trong data/.
Giữ bộ kiểm định dữ liệu thật đang được pipeline sử dụng (`src/t08_review.py`,
`src/t09_reference.py`, các lệnh nghiệm thu T09 và kiểm định tích hợp T10) để lần
chạy sau vẫn phát hiện sai dữ liệu. Validation Parquet và review JSON được giữ làm
bằng chứng nghiệm thu; đây là sản phẩm bàn giao, không phải dữ liệu test giả.

T10: chạy `T10_Heavy_Graph_Metrics.py` để tính và đối chiếu hai lần; cấu hình riêng
trong `config/t10.yaml` dùng cùng đường dẫn/lịch T08 từ `config/config.yaml`.
Đầu ra tại `data/processed/t10`; bảng sampling_quality công bố sai số xấp xỉ.
`--skip-reproducibility` chỉ dùng khảo sát, không đánh dấu sẵn sàng bàn giao.

Sau khi push một release, các thành viên lấy đúng revision đã công bố rồi kiểm tra
hash theo manifest. Việc upload dữ liệu là một bước riêng, không diễn ra khi test.

Khi được yêu cầu xuất bản: đăng nhập `hf auth login`, chạy
`scripts/prepare_hf_manifest.py` rồi `scripts/publish_hf_release.py`.
Publisher chỉ upload allowlist, kiểm tra hash trên remote và lưu receipt tại
`.release/hf_publish_receipt.json`; không xóa các file remote khác.
GitHub chỉ lưu code/config/tài liệu; dữ liệu và receipt được `.gitignore` loại bỏ.
