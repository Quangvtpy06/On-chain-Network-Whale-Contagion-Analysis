# T07 CEX public-history — kết quả bổ sung

Ngày 22/10/2026. Phạm vi: chuẩn bị registry lịch sử nhãn CEX cho người làm T14; không thay T07 hồi cứu, config chung đã được ký hash hoặc T12 v2.

## Kết quả

- Khảo sát 24 đường dẫn adapter ở snapshot public merge trước năm 2025, lấy được owners Ethereum literal từ 14 project.
- 306 claim/306 địa chỉ: theo xác nhận của người dùng, Quang đã kiểm tra và chấp nhận **306/306**, còn **0 pending**. Chỉ áp dụng tập 306 đã xác nhận, không mở rộng sang địa chỉ ngoài registry.
- Bằng chứng gồm URL ghim commit, dòng chứa địa chỉ, hash bytes và metadata PR merge. Không thực thi JavaScript nguồn; không suy ví Ethereum từ địa chỉ ở chain khác.
- Snapshot `97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e`, public merge bound `2024-12-31T12:14:13Z`. Đây là cận bảo thủ, không phải ngày xuất hiện đầu tiên.
- 306 ứng viên chạm **21,2014489%** endpoint volume toàn kỳ của transfer đã netting. Mẫu số là `2 × sum(total_value)`; coverage không phải recall CEX và không đại diện toàn bộ giao dịch Ethereum/USDT dưới ngưỡng 500.000.
- 61/465 địa chỉ mang type CEX hiện tại trong T07 trùng tập ứng viên; các ví lớn chưa có bằng chứng trong snapshot được đưa vào backlog, không gán ngược nhãn hiện tại.
- 26 địa chỉ/6.289 member-days của cohort T12 v2 trùng các ứng viên lịch sử. Không tự xóa chúng ở T14; nếu dùng public-history để thay bộ lọc cohort cần phiên bản T12 tiếp theo và tái lập sau phê duyệt.
- Có nguồn lịch sử thứ cấp cho Crypto.com `0x46340b20830761efd32832a74d7169b29feb9758`, tại owners Ethereum của snapshot. Không nhầm với bài công bố chính thức năm 2022 vốn không liệt kê địa chỉ đó.

## Kiểm định

- Hai lần build offline từ cùng bytes nguồn: **8/8 Parquet khớp SHA-256**, lưu trong `t07_cex_history_reproducibility.json`.
- Validator độc lập dùng parser hẹp khác production tokenizer, kiểm tra địa chỉ, Ethereum owners, public merge metadata, freeze và hash.
- Coverage đối chiếu endpoint group totals cho **655 ngày × 2 scope**: candidate chưa approved và approved as-of. Scope approved hiện không có nhãn; số 0 coverage không có nghĩa thị trường không có CEX.
- Controls ranh giới public_available_at, effective_to và loại hàng chưa human_verified đều đạt.
- Kiểm tra adapter phê duyệt trong bộ nhớ: giữ verified_at thực tế sau public_available_at, từ chối thiếu từng xác nhận nguồn/chain/lịch sử. Không lưu hồ sơ review giả, không xuất fixture hay code test tạm.
- Loader `load_cex_for_cutoff` từ chối registry khi chưa có nhãn approved, kiểm tra provenance trước khi sử dụng sau phê duyệt. Sau xác nhận đầy đủ của Quang, đã chạy lại hai lần, 8/8 Parquet khớp hash; loader trả đúng 306 địa chỉ tại cutoff 01/01/2025 và không trả nhãn tại đúng mốc availability. Không tự chuyển missing labels thành NetFlow=0.

## Trạng thái bàn giao

Gate kỹ thuật đạt; sau xác nhận Quang đã mở và kiểm tra toàn bộ nguồn của 305 địa chỉ còn lại, `ready_for_t14_endpoint_lookup=true` **cho đủ 306 địa chỉ trong bộ lịch sử này**. Quyết định Binance đầu tiên giữ verified_at=`2026-10-22T15:24:53.782549Z`; 305 quyết định bổ sung ghi verified_at=`2026-10-22T15:28:37.410995Z`. public_available_at giữ `2024-12-31T12:14:13Z`, không backdate ngày review. Coverage endpoint approved **21,2014489%** trên đồ thị netted; pending=0. `ready_for_rq3_pit_forecast=false` vì đây không phải nghiệm thu toàn bộ tính biến và timing của T14. Giữ nguyên yêu cầu của nhóm: “Một thành viên cần mở từng nguồn và xác nhận”; quyết định được ghi dựa trên xác nhận của người dùng và không mở rộng ra ngoài registry.

Người làm T14 có thể bắt đầu tích hợp loader ngay; để chốt biến PIT cần ít nhất một tập con nhãn approved và coverage tương ứng. Không cần chờ định danh mọi ví Unknown. Các nhánh volatility/large-transfer độc lập không bị chặn.

[Bảng nguồn và top 20 ưu tiên review](T07_CEX_history_review_packet.md) có URL mở đúng dòng. [Hướng dẫn phê duyệt, schema và hợp đồng T14](T07_CEX_history_handoff.md) có lệnh CLI. Tất cả bảng ở `data/processed/t07/cex_history/`, chỉ dùng Parquet; metadata JSON. Đã push GitHub/HF; xem [revision phát hành và bàn giao T14](T07_T12_release_2026-10-22.md).
