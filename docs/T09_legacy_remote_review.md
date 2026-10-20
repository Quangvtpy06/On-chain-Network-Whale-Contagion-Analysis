# T09 — Review đầu ra Hugging Face và code

Revision nguồn: `3ddac08eef81e611c54e035369d5da355829e723`. Các file tải về được giữ nguyên, đối chiếu SHA-256 theo metadata Hugging Face.
**Kết luận:** Chưa đạt để dùng cùng T08 netted hiện tại.

| Tham chiếu | Cửa sổ | PASS | FAIL |
|---|---|---:|---:|
| current_netted_t08 | daily | 0 | 655 |
| current_netted_t08 | weekly | 0 | 94 |
| legacy_raw_event_graph | daily | 655 | 0 |
| legacy_raw_event_graph | weekly | 94 | 0 |

Kiểm định độc lập: dựng degree/strength bằng pandas; PageRank kiểm tra phương trình chuyển trạng thái có dangling và alpha=0.85 bằng SciPy. Code được probe thêm bằng nghiệm hệ tuyến tính trên đồ thị giả có nút dangling.

## Phát hiện

- Remote summary refers to snapshot_metrics_daily/weekly.csv, but neither file exists in the remote folder.
- Remote summary contains absolute paths and has no input graph hash / revision.
- Weekly outputs omit partial-week / regression eligibility metadata.
- Code enumerates only windows found in edges, dropping empty snapshots; empty calculate_snapshot returns incomplete stats.
- PageRank retry relaxes tolerance from 1e-8 to 1e-6, making accuracy inconsistent between snapshots.
- Code silently sums duplicate edges; this can double-count transaction_count instead of rejecting an invalid T08 input.
- Remote weighted_degree_tx must be interpreted according to the reference that matches: raw event counts are not distinct transaction counts.

## Yêu cầu trước khi bàn giao bản mới

- Chạy T09 trên T08 netted đã nghiệm thu, ghi hash đầu vào và đường dẫn tương đối từ config.
- Bàn giao node_metrics_daily/weekly.parquet và snapshot_metrics_daily/weekly.parquet; giữ đủ lịch 655 ngày, 94 tuần.
- Mang metadata tuần thiếu ngày vào cả bảng node/cửa sổ; loại 2 tuần này khi hồi quy.
- Xác minh degree, weighted_degree và PageRank trên mọi node/cửa sổ; weighted_degree_tx là số lượt transaction qua cạnh, không phải số unique tx của cả ví.
- Chỉ đưa bản đã được nghiệm thu vào release manifest. Không tự upload bản T09 cũ chưa khớp T08 mới.

## Chuẩn hóa nơi lưu test và bàn giao đã thực hiện

- T09 chạy thử `--max-windows` mặc định xuất vào `.cache/t09_preview`, không ghi đè bảng chính.
- Đã chạy thử 1 ngày trên T08 netted, đối chiếu độc lập PASS và dọn output thử sau khi kiểm tra.
- Đầu ra mới của code dùng đường dẫn tương đối và thư mục T09 đọc từ config; bộ dữ liệu remote được giữ nguyên để review.
- Đã dọn 4 thư mục test cũ và bản T08 chạy lặp sau khi kiểm đủ 11 hash; tổng khoảng 144 MB.
- T08 tự dọn lần chạy thứ hai trong `.cache/`; pytest đặt dữ liệu thử dưới `.cache/`.
- `data/hf_release_manifest.json` chỉ ra file được push và file bị chặn. T09 remote hiện bị chặn, cần chạy lại toàn kỳ và nghiệm thu trước khi dùng cùng T08 mới.
