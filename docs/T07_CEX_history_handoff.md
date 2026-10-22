# T07 — lịch sử nhãn CEX và bàn giao cho T14

Registry `t07_cex_public_history_v1` bổ sung bằng chứng lịch sử riêng, không ghi đè T07 hồi cứu hoặc nhãn secondary theo research-knowledge. T12 v2 giữ nguyên. Không biến lookup AI thành phê duyệt của thành viên.

## Đã thu thập gì?

Snapshot DefiLlama-Adapters `97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e`, gắn với [PR 12915](https://github.com/DefiLlama/DefiLlama-Adapters/pull/12915), có metadata merge `2024-12-31T12:14:13Z`. Dùng mốc merge làm **cận khả dụng công khai bảo thủ**, không gọi là ngày nhãn xuất hiện đầu tiên. Ngày commit đơn lẻ không đủ: trong khảo sát có commit mang ngày 31/12/2024 nhưng PR đến 02/01/2025 mới merge, nên không dùng nó làm snapshot main trước kỳ mẫu.

Nguồn thứ cấp: bảng `ethereum.owners` của từng adapter, riêng Binance lấy các hàng có network `ETH` trong assetList. Không quét mọi địa chỉ `0x` trong file, không lấy token contract hoặc địa chỉ BSC/Base làm ví Ethereum, không chạy mã JavaScript tải về. Nhãn CEX phản ánh attribution của nguồn, không chứng minh chủ sở hữu tài khoản cá nhân hoặc quyền kiểm soát khóa liên tục.

Ví Crypto.com `0x46340b20830761efd32832a74d7169b29feb9758` có trong [owners Ethereum ở snapshot này](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/crypto-com/index.js#L14). Đây là bằng chứng lịch sử thứ cấp mới; không nói ví đó nằm trong bài công bố Crypto.com năm 2022 vốn không chứa nó.

**306 địa chỉ ứng viên**, từ 14 project có owners literal trong 24 project đã khảo sát. Tập ứng viên chạm khoảng **21,2014% endpoint volume** của transfer đã netting trong kỳ nghiên cứu. Đây chưa phải coverage nhãn approved và không phải recall của toàn bộ CEX.

**Cập nhật review:** theo xác nhận của người dùng, Quang đã mở, kiểm tra và chấp nhận toàn bộ **306/306 địa chỉ trong bộ lịch sử này; 0 pending**. Quyết định đầu tiên cho Binance `0x28c6c06298d514db089934071355e5743bf21d60` được giữ nguyên lúc `2026-10-22T15:24:53.782549Z`; 305 quyết định còn lại được ghi lúc `2026-10-22T15:28:37.410995Z`. Các thời điểm review tách biệt mốc lịch sử `2024-12-31T12:14:13Z`. Coverage endpoint của tập approved khoảng **21,2014%**. Gate endpoint lookup mở cho tập 306 địa chỉ này; không chứng nhận toàn bộ nhãn CEX có thể tồn tại hoặc toàn bộ RQ3. Quyết định không mở rộng ra các ví ngoài tập 306.

Không có file tại đường dẫn khảo sát chỉ có nghĩa là không tìm thấy **tại đường dẫn/snapshot đó**, không chứng minh sàn không có ví hoặc không có nguồn lịch sử khác. Tập CEX hiện tại của T07 có 465 địa chỉ, chỉ 61 trùng với snapshot này. Backlog ghi rõ các khoảng trống; Tether Treasury cần correction phân loại riêng, không tự đưa vào CEX history.

## Cần thành viên làm gì để duyệt?

Mở [bảng review](T07_CEX_history_review_packet.md), ưu tiên 20 địa chỉ có endpoint volume lớn nhất. Với mỗi địa chỉ hoặc một project:

1. Mở URL blob **đã ghim commit**, tìm đầy đủ địa chỉ và xác nhận nó ở owners Ethereum hoặc hàng `ETH` của Binance, không ở phần token hay chain khác.
2. Mở PR 12915, kiểm tra merge đúng commit và thời gian công khai trước mẫu. API response nguyên bản được lưu trong source_payloads để đối chiếu. Cận merge là bằng chứng public-history, không phải ngày nhóm biết nhãn.
3. Xem lại attribution CEX và chấp nhận/không chấp nhận giả định giữ nhãn từ thời điểm quan sát cho đến khi có bằng chứng thay thế. Đây là giả định, không phải chứng cứ ví không bao giờ đổi chủ. Khi có thời điểm ngừng hiệu lực cần correction/version rõ ràng và dùng `effective_to`.
4. Ghi quyết định bằng lệnh dưới đây **sau khi đã thực sự mở và kiểm tra nguồn**. Không dùng tên trợ lý hoặc giả ngày review. `verified_at` do công cụ ghi thời gian hiện tại; `public_available_at` giữ mốc bằng chứng lịch sử, không backdate verified_at.

Ví dụ cho một địa chỉ; thay tên và note bằng thông tin review thật:

```powershell
python scripts/review_t07_cex_history.py --address 0x46340b20830761efd32832a74d7169b29feb9758 --reviewer "Ten thanh vien" --decision approve --note "Da doi chieu owners Ethereum va PR merge; chap nhan public-history bound va gia dinh persistence." --source-opened-by-human --ethereum-addresses-confirmed --historical-bound-confirmed
python scripts/build_t07_cex_history.py
```

Để duyệt cả project, thay `--address ...` bằng `--project crypto-com`, nhưng phải kiểm tra **tất cả địa chỉ trong project** được duyệt. Có thể chỉ duyệt một tập con đủ bằng chứng, không cần chờ toàn bộ 306 hay mọi Unknown. Quyết định đã lưu không bị ghi đè; sửa sai phải có correction phiên bản rõ ràng. Không rõ thì để pending hoặc reject có lý do, không đoán.

## Schema và quy tắc as-of

`t07_cex_label_history.parquet` chỉ chứa hàng approved; `t07_cex_history_candidates.parquet` giữ mọi ứng viên/pending/rejected để audit.

| Trường | Ý nghĩa |
|---|---|
| address / chain / entity_name / entity_type | Địa chỉ lowercase, Ethereum, attribution CEX cụ thể |
| source_url / historical_evidence_url / source_locator | Bản raw và blob ghim commit, dòng chứa bằng chứng |
| snapshot_commit / source_sha256 / public_merge_url | Khóa phiên bản và hash byte nguồn đã lưu |
| public_available_at | Cận công khai bảo thủ từ merge, không phải ngày biết sớm nhất |
| effective_from / effective_to | Khoảng hiệu lực theo mô hình attribution; chưa biết ngừng hiệu lực để null và công bố giả định persistence |
| verified_at / reviewed_by | Thời điểm và người review thật hiện tại, không backdate |
| review_status / human_verified | Không approved thì không được loader chọn |
| source_tier / confidence | Nguồn thứ cấp; đề xuất confidence medium, không biến thành xác nhận của chính sàn |

Với cutoff D lúc 00:00 UTC, chỉ chọn nhãn approved có `public_available_at < D`, `effective_from < D`, `effective_to > D` hoặc null. Thời điểm public-history và thời điểm nhóm review khác nhau theo thiết kế; không sửa điều kiện v1/v2 vốn đo research-knowledge.

## Người làm T14 tích hợp thế nào?

```python
import pandas as pd
from src.cex_label_history import load_cex_for_cutoff

labels = load_cex_for_cutoff(pd.Timestamp('2025-01-02', tz='UTC'))
cex_addresses = set(labels.address)
# Nếu labels rỗng tại cutoff: đánh dấu không có endpoint labels khả dụng.
# Không đổi thiếu nhãn thành một ngày NetFlow = 0 hợp lệ.
```

Loader kiểm tra gate, hash input/output và chỉ lấy approved. Khi chưa có người duyệt nó từ chối dùng registry; không lặng lẽ dùng candidates. Đổi quyết định hoặc sửa dữ liệu sẽ đóng gate/tạo lỗi provenance cho tới khi build/validate lại.

T14 đọc:

- `data/processed/t07/cex_history/t07_cex_label_history.parquet` và `t07_cex_history_gate.json`.
- `data/processed/t12/v2/t12_downstream_gate.json` và đúng cohort_path v2 trong gate.
- Coverage ngày gồm nhánh `approved_asof` và nhánh `candidate_only_not_approved`; tuyệt đối không trộn hai nhánh.

NetFlow CEX: outside→CEX trừ CEX→outside; CEX→CEX phải báo riêng theo định nghĩa sector/entity đã chọn. DEX, bridge và issuer treasury không tự coi là CEX. T14 vẫn phải kiểm tra chiều, UTC, thời điểm giá/volatility/X_t, train/test T18 và các horizon; gate T07 không chứng nhận toàn bộ RQ3.

**T12 v2 không tự đổi sau khi bổ sung nguồn này.** Nó dùng policy nhãn theo research-knowledge, còn registry này theo public-information. Nếu muốn loại CEX đã biết công khai khỏi cohort trước tính z/rank, phải ban hành phiên bản cohort tiếp theo, nhập các nhãn đã duyệt và chạy lại đầy đủ. Không tự loại 26 địa chỉ trùng ứng viên khỏi cohort v2 ở T14 rồi vẫn gọi là cùng cohort. Có 26 địa chỉ/6.289 member-days trùng ứng viên lịch sử hiện tại; đây là chẩn đoán cần nêu khi thiết kế WhaleFlow, chưa phải nhãn approved mới.

Người làm T14 có thể chuẩn bị loader song song. Để chốt biến PIT phải nhận tập nhãn approved có coverage và lựa chọn protocol cohort rõ ràng. T12 v2 hiện đã sẵn sàng ở scope hoạt động lớn; không yêu cầu xác minh nhà đầu tư cá nhân để làm NetFlow CEX.

## Tái lập và các file

Lần đầu: `python scripts/build_t07_cex_history.py --fetch`. Nếu proxy môi trường bị lỗi có thể dùng `--direct` cho nguồn công khai. Khi payload đã có, chỉ chạy offline `python scripts/build_t07_cex_history.py`; không tự tải đè bằng chứng ghim.

Chạy độc lập: `python scripts/validate_t07_cex_history.py`. Kiểm tra parser thứ hai, metadata public merge, chain/địa chỉ/hash, quyết định người review, cutoff/expiry, và coverage 655 ngày đối chiếu endpoint group totals. Mọi bảng chỉ Parquet; metadata JSON và hướng dẫn Markdown. Giữ mã validator thật để tái lập, không tạo mã test/dataset giả bàn giao.

Source payload giữ bytes nguồn gốc và HTTP status trong Parquet để nhóm audit/tái lập. Kiểm tra nguồn khi phát hành: root snapshot không có file license, metadata license hiện tại của repository trả null; không tự ghi nguồn là MIT/CC0. Payload được giữ kèm URL, commit và hash, không được mô tả là code do nhóm tự viết. Địa chỉ, URL, hash và kết quả review là các bảng bàn giao tách biệt.
