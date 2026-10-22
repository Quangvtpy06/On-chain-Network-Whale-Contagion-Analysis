# Xử lý review nguồn và 79 địa chỉ overlap hạ tầng

**Cập nhật:** nhóm đã yêu cầu ban hành [protocol v2](T12_protocol_v2.md). Bản v2 triển khai
hiện tại chỉ đổi scope/điều kiện nghiệm thu và thêm sensitivity hồi cứu; vẫn dùng chính sách
nhãn research-available của v1. Đề xuất public-history registry ở phần A dưới đây chưa được
triển khai và không được dùng để tự backdate nhãn. Xem [kết quả v2](T12_v2_completion_report.md).

Ngày chuẩn bị: 22/10/2026. Tài liệu này là đề xuất xử lý có thể review; không thay protocol v1, không tạo nhãn human_verified và không mở gate.

## Bằng chứng đã chuẩn bị

- [Bảng nguồn 40 địa chỉ](T12_source_review_packet.md): mỗi hàng có toàn bộ địa chỉ, URL, vị trí đọc, kết quả/giới hạn.
- `data/processed/t12/t12_source_review_draft.parquet`: cùng bằng chứng dạng bảng, mọi cờ human/PIT vẫn false.
- `data/processed/t12/t12_infrastructure_history_review.parquet`: đủ 79 địa chỉ, số ngày trong cohort, nhãn T07 hiện tại và đầu mối lịch sử. Những địa chỉ chưa tra cứu riêng được ghi rõ, không giả định đã review hết 79.
- 10/79 có đầu mối từ trang công bố của chủ thể có ngày trước mẫu nghiên cứu, tương ứng 4.118/10.948 lượt thành viên. Đây là ứng viên bằng chứng lịch sử, chưa phải 10 nhãn PIT đã nghiệm thu.
- Trong 40 hàng, 7 có công bố trực tiếp của chủ thể, 2 có tài liệu gốc khác và 2 có attribution trong nghiên cứu gốc. Các hàng còn lại gồm explorer hiện tại, thông tin chỉ xác nhận hoạt động hoặc lookup chưa kết luận. Không biến những hàng Unknown thành ví cá nhân.

Nguồn nổi bật:

1. [Binance — Our Commitment To Transparency](https://www.binance.com/en/blog/community/2895840147147652626): có các địa chỉ Ethereum cụ thể; trang ghi công bố năm 2022 và cập nhật năm 2023. Đối chiếu từng hàng, không suy rộng sang tất cả ví Binance.
2. [Crypto.com — Transparency First](https://crypto.com/us/company-news/transparency-first): danh sách Ethereum/ERC20 chứa `0xcffad3200574698b78f32232aa9d63eabd290703`; không chứa `0x46340b20830761efd32832a74d7169b29feb9758`. Không dùng cùng tài liệu để chứng thực cả hai ví.
3. [Bybit — Ownership Explained](https://www.bybit.com/en/help-center/article/Bybit-Wallet-Addresses-Ownership-Explained): hàng Ethereum có `0xf89d7b9c864f589bbf53a82105107622b35eaa40`; trang có mốc cập nhật trước năm 2025.
4. [Bybit audit report](https://www.bybit.com/common-static/cht-static/por/Bybit_PoR_Audit_2025_Jun_19.pdf#page=14): `0x18e296053cbdf986196903e889b7dca7a73882f6` ở trang PDF 14/in số 13. Ngày audit 19/06/2025 khác ngày report 27/06/2025; chưa được dùng nhãn từ đầu mẫu hoặc mặc định từ ngày audit.
5. [IMF WP/25/141](https://www.imf.org/-/media/files/publications/wp/2025/english/wpiea2025141-source-pdf.pdf): Appendix E/Table 13 gán Cumberland và Jump Trading cho hai địa chỉ trong queue. Đây là attribution nghiên cứu, không phải xác nhận chủ sở hữu cá nhân; tháng tài liệu chưa thay được thời điểm công khai chính xác.
6. [Tài liệu gốc tòa liên bang, 29/10/2024](https://ecf.flmd.uscourts.gov/cgi-bin/show_public_doc?2024-00809-56-6-cv=): đọc danh sách cuối đã sửa attribution của `0xa29e963992597b21bcdcaa969d571984869c4ff5` từ Coinhako sang B2C2. Không lấy đoạn đầu đã bị đính chính, không suy ra danh tính tài khoản hoặc hành vi phạm pháp từ địa chỉ.

## Thành viên nhóm review như thế nào?

1. Mở bảng Markdown 40 hàng, bấm nguồn rồi Ctrl+F **toàn bộ địa chỉ**. Kiểm tra chain Ethereum và xem nhãn có thực sự mô tả địa chỉ đó hay chỉ là đối tác giao dịch. Trang Base/XDC hoặc giao dịch từ Binance không tự chứng minh chủ ví trên Ethereum.
2. Đọc đúng ngữ cảnh: disclosure chủ ví, nhãn explorer, tài liệu nghiên cứu hay claim chưa xác minh. Không tìm thấy danh tính thì chọn reviewed_unknown. Kết quả này không chứng minh đó là ví cá nhân.
3. Ghi nhận bằng lệnh bên dưới sau khi thực sự mở nguồn. Tên và thời điểm của người review phải là thật; trợ lý không chạy lệnh này thay người.
4. Nếu xác nhận được nhãn danh tính, đưa vào workflow T07 như nguồn bậc hai có source_url/confidence. T07 hiện đang có nhãn được ký hash; sửa nhãn cũ cần phiên bản/correction rõ ràng và kiểm định các phụ thuộc.

Ví dụ ghi nhận cho địa chỉ Binance, chỉ chạy sau khi thành viên đã mở nguồn và xác nhận:

```powershell
python scripts/review_t12_source.py --address 0x21a31ee1afc51d94c2efccaa2092ad1028285549 --reviewer "Ten thanh vien" --decision infrastructure --source-url "https://www.binance.com/en/blog/community/2895840147147652626" --note "Da doi chieu dung dia chi trong hang Ethereum; chua xac nhan archive timestamp." --source-opened-by-human
```

Lệnh lưu vào `data/processed/t12/t12_cohort_human_review.parquet`, không xuất CSV, không tự sửa T07/gate. `infrastructure` là kết quả review construct; muốn loại ví trong lịch sử vẫn cần availability/hiệu lực nhãn hợp lệ. Nếu nguồn bị chặn/chưa đủ, để pending, không tích xác nhận. Nếu đã mở và chưa xác định được owner, có thể ghi reviewed_unknown kèm giới hạn cụ thể.

## 79 địa chỉ có nghĩa gì?

Overlap theo nhãn hồi cứu là chẩn đoán cohort còn hạ tầng; **không tự chứng minh scoring đã nhìn trước**. V1 chỉ dùng cửa sổ quá khứ và nhãn có sẵn trước cutoff, nên một CEX chưa được biết lúc đó có thể được chọn như địa chỉ chưa định danh. Điểm yếu là construct/độ phủ nhãn, không nhất thiết là leakage trong công thức.

Do đó không nên chỉ chọn một trong hai cực: gán ngược tất cả nhãn hiện tại, hoặc tuyên bố cohort sai PIT vì sau này biết có CEX. Phải định nghĩa rõ cohort là địa chỉ hoạt động lớn theo thông tin lịch sử hay nhà đầu tư cá nhân đã xác minh. Dữ liệu hiện tại chỉ hỗ trợ cách diễn giải thứ nhất.

Gate v1 đang chặn mọi overlap hạ tầng như một **điều kiện nghiệm thu bảo thủ**. Muốn cho phép cohort hoạt động lớn có contamination chưa nhận biết trong quá khứ thì cần đổi scope/điều kiện gate công khai ở phiên bản mới, không xóa blocking_reasons trong JSON. Không được giữ tên cờ rộng khiến người dùng hiểu đã chứng minh danh tính hoặc đủ mọi điều kiện PIT của T14.

## Phương án chính đề nghị: cohort as-of và độ nhạy hồi cứu

### A. Nhánh chính dùng thông tin công khai trong lịch sử

Tạo protocol v2 riêng, giữ nguyên cấu hình/đầu ra v1 và ngưỡng hành vi đã đóng băng. Chỉ đổi mô hình thời gian nhãn sau khi chốt trước T15.

Registry nhãn cần ít nhất:

| Trường | Ý nghĩa |
|---|---|
| source_publication_at | Mốc công khai chứng minh được của nguồn chứa đúng địa chỉ/chain |
| public_available_at | Mốc khả dụng dùng cho as-of, có thể bảo thủ hơn ngày trên tài liệu |
| effective_from / effective_to | Khoảng hiệu lực attribution, không suy ngược trước bằng chứng |
| verified_at / verified_by | Người kiểm tra và thời điểm thực tế hiện tại, không backdate |
| historical_evidence_url | URL bản tài liệu/commit/archive có thể kiểm chứng |
| historical_evidence_sha256 | Hash bản đã đối chiếu, tránh nguồn mutable đổi nội dung |
| historical_review_status | pending / approved / insufficient |

Chỉ dùng hàng approved khi `public_available_at < D` và attribution có hiệu lực tại cutoff D−1. Timestamp trên giao dịch không phải ngày nhãn được công khai. Ngày cover PDF hoặc ngày audit không tự chứng minh ngày publication. Explorer tag hiện tại không có lịch sử thì chưa đủ.

V1 đang quy định label_available_at không trước verified_at, nghĩa là thời điểm nhóm thực sự xác minh. V2 public-history là **định nghĩa thông tin khác**, dựa vào nguồn đã công khai; không sửa lùi verified_at để lách validator v1.

Thiếu lịch sử thì giữ address unknown tại ngày đó, kèm cờ/coverage thể hiện giới hạn. Cờ nhãn hồi cứu chỉ dùng để audit sau này, không vào predictor/bộ lọc chính của ngày D. Khi đó kết quả chỉ là cohort địa chỉ hoạt động lớn chưa định danh theo thông tin as-of, không phải cohort đã lọc sạch mọi CEX hoặc cá voi cá nhân.

Sau khi đổi registry/policy: dựng lại dân số, loại nhãn khả dụng trước khi chuẩn hóa/rank, bổ sung lại top50 nếu còn đủ ứng viên; kiểm định cutoff và review top sau lọc. Không chỉ xóa 79 địa chỉ khỏi bảng top50 đã chọn.

Nhánh CEX endpoint của T14 cũng phải chọn CEX theo cùng nguyên tắc as-of nếu muốn dự báo PIT. Mở gate xây cohort T12 không tự chứng nhận CEX NetFlow/WhaleFlow endpoint T14.

### B. Nhánh độ nhạy dùng nhãn hiện tại

Tạo kết quả riêng loại hạ tầng bằng T07 hiện tại, đặt tên retrospective/backfilled-label sensitivity. Công bố chênh lệch thành viên, volume, stability và WhaleFlow với nhánh A. Không trộn nhánh này vào dự báo lịch sử mà không ghi look-ahead từ nhãn.

### C. Nếu chưa thu thập được đủ lịch sử

Vẫn làm được phần hồi cứu và các biến thị trường/large-edge không phụ thuộc nhãn. Không cần dừng toàn bộ T14. Phân tích dự báo có thể giới hạn vào tập CEX có bằng chứng lịch sử, báo độ phủ theo USDT và các giới hạn; không coi Unknown là đã xác minh non-CEX.

## Lỗi phân loại cần xử lý riêng

`0x5754284f345afc66a98fbb0a0afe71e0f007b949` mang tên Tether Treasury nhưng type CEX trong T07. [Explorer Ethereum](https://usdt.tokenview.io/en/address/0x5754284f345afc66a98fbb0a0afe71e0f007b949) hiển thị treasury; [nghiên cứu gốc về stablecoin](https://www.nber.org/system/files/working_papers/w27136/w27136.pdf) là đầu mối thêm về luồng issuance/redemption. Đề xuất Other với subtype issuer_treasury, chờ review; không suy ra Tether là CEX.

Hệ quả cần kiểm tra lại khi correction được duyệt: tập CEX, coverage và NetFlow T12/T14. Tài liệu review không tự sửa bảng T07 hoặc output downstream hiện có.
