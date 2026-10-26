# Kiểm tra output T19 đã phát hành — 25/10/2026

**Kết luận: PASS cho sản phẩm ma trận feature và split phục vụ phân loại hồi cứu CEX/DEX ở T20.** Không chứng nhận dự báo nhãn point-in-time, danh tính nhà đầu tư cá nhân hay khả năng khái quát sang ví mới.

## Phiên bản đã kiểm tra

- GitHub main hiện tại: `b98af34`; code tính toán T19 và config không đổi so với commit được ghi trong manifest: `b59985d305c9492f2d00cf5bf70c2f1f7de2a864`.
- GitHub lưu code; output nằm ở [Hugging Face, revision 25becf91d38a38ef7998d26b3b148e4109ef1f05](https://huggingface.co/datasets/team-crypto/Market-data-crypto-project/tree/25becf91d38a38ef7998d26b3b148e4109ef1f05/data/processed/t19).
- Đã tải và kiểm tra đủ **11/11 file trong manifest**: 10 output và config. Tổng 193.462.093 byte, mọi SHA-256/kích thước khớp. Parquet mở được bằng PyArrow/pandas; không phải con trỏ Git LFS.
- File manifest đã tải: `data/hf_t19_release_manifest.json`. Trường `upload_performed=false` là trạng thái lúc chuẩn bị manifest; việc tải thành công và đối chiếu byte từ revision cụ thể xác nhận các file thực sự đã có trên HF.

## Kết quả trên bảng thật

| Sản phẩm | Weekly | Daily |
|---|---:|---:|
| Cửa sổ | 94 | 655 |
| Dòng node-window | 388.557 | 712.519 |
| Predictor trong feature dictionary | 41 | 41 |
| Lớp đủ điều kiện | CEX, DEX | CEX, DEX |
| Gap giữa các tập | 1 tuần | 7 ngày |

- Bảng validation công bố có **70 PASS**, không FAIL/WARN.
- Tính lại độc lập trong phiên review từ input local đúng hash T07/T09/T10/T11. Cả **6/6 bảng chính** (feature, split, label summary × hai loại cửa sổ) khớp dữ liệu, dtype và content hash trong cùng môi trường đọc.
- Chạy lại các invariant của validator trên output đã tải: khóa, số học degree/volume, PageRank, giới hạn metric, calendar, split theo thời gian, loại tuần lẻ, nhãn và độ phủ lớp đều đạt. Lượt này không chạy lại các phép mutation/truncation tại mọi cutoff; bằng chứng 70 PASS của lượt phát hành và review code trước đó được giữ riêng, không coi là vừa thực thi lại toàn bộ các ca đó.
- Kiểm tra bổ sung bằng lookup riêng: lag degree/volume của 200 dòng ngẫu nhiên mỗi loại đều đúng cửa sổ lịch trước; tổng endpoint volume bằng hai lần edge volume ở mọi cửa sổ. Không có khóa trùng hoặc nhãn/id/split trong danh sách 41 predictor.
- Hai tuần lẻ không vào train/validation/test. Cả hai readiness `computation_validated` và `node_classification_ready` đúng trong phạm vi đã nêu; `pit_label_forecast=false` phù hợp chính sách nhãn.

## Giải thích khác biệt hash giữa môi trường

Parquet được ghi bằng pandas **3.0.6**, máy review dùng **2.2.3**. Hàm `frame_hash` đưa tên dtype vào SHA-256: chuỗi được ghi là `str` ở writer nhưng đọc thành `object` ở reader. Vì vậy so trực tiếp với `t19_repro.json` ban đầu báo khác cả sáu hash, dù bảng tải về và bảng tính mới khớp chính xác trong môi trường đọc.

Đã dùng metadata dtype writer có sẵn trong footer Parquet để dựng lại đúng header hash, giữ nguyên hash của giá trị từng hàng. **6/6 hash khớp hoàn toàn với `t19_repro.json`**. Đây là khác biệt cách biểu diễn dtype, không phải thay đổi dữ liệu. Hash byte của mọi artifact cũng đã khớp manifest độc lập.

Nên ghi phiên bản Python/pandas/NumPy/PyArrow trong summary và dùng schema hash chuẩn hóa hoặc khóa môi trường cho các lượt sau. Đây là cải thiện tái lập giữa môi trường, không cần chạy lại output hiện tại chỉ vì khác dtype chuỗi.

## Điều kiện sử dụng ở T20

1. Chỉ lấy predictor từ `t19_feature_dictionary.parquet`; không đưa address, `label_*`, split hoặc metadata vào X. Chỉ huấn luyện dòng nhãn hợp lệ trong split train; fit encoder/scaler/imputer trên train.
2. Giữ split đã phát hành, không kéo gap/tuần lẻ vào mẫu đánh giá. Weekly là bảng chính, daily là phụ; không chọn lại theo kết quả test.
3. Báo riêng đánh giá cho địa chỉ chưa xuất hiện trong train. Ở test mới: weekly có CEX 51 địa chỉ/253 dòng và DEX **6 địa chỉ/6 dòng**; daily có CEX 49 địa chỉ/752 dòng và DEX **6 địa chỉ/7 dòng**. Mẫu DEX ví mới quá ít để kết luận mạnh về khái quát hóa.
4. Nhãn T07 là hồi cứu; đây là phân loại CEX/DEX trên feature cùng cửa sổ, không phải phân loại cá voi cá nhân hoặc dự báo danh tính lịch sử. Unknown/Contract/Other không phải lớp âm.

Bằng chứng số liệu và hash: [T19_published_output_review_evidence.json](T19_published_output_review_evidence.json). Không sửa code/output T19, không upload hoặc thay gate trong review. Bản tải và script kiểm tra tạm được xóa sau khi hoàn tất; các thay đổi T15/T16 đang chờ của người dùng được giữ nguyên.
