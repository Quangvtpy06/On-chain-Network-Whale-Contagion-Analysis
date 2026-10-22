# T14 — công việc cần sửa sau bàn giao T07/T12

Ngày 22/10/2026. Ghi cho người phụ trách T14; không sửa code hoặc output T14 trong lần bàn giao này. Đã đối chiếu main `c5ed6cd` và nhánh `t14-flow-volatility` ở `9cfe8e9` trước khi phát hành.

## Đầu vào đã có

- T07: `data/processed/t07/cex_history/t07_cex_label_history.parquet`, 306 địa chỉ Ethereum/14 CEX, được ghi nhận Quang đã kiểm tra và chấp nhận. `t07_cex_history_gate.json` mở endpoint lookup cho tập này; public_available_at dùng cận merge `2024-12-31T12:14:13Z`, verified_at là thời điểm review thật 22/10/2026, không backdate. Coverage endpoint 21,2014% của đồ thị USDT netted >=500.000, không phải recall CEX.
- T12: `data/processed/t12/v2/t12_downstream_gate.json`; cohort chính do trường cohort_path chỉ định, hiện là `data/processed/t12/v2/primary/cohort_members_daily.parquet`. Protocol `t12_unidentified_activity_v2`, cửa sổ `[D−30,D)`, top50 sau 30 ngày warm-up. Nhánh retrospective giữ riêng.
- Code, cấu hình và tài liệu lấy đúng commit GitHub ghi trong `data/hf_t07_t12_release_manifest.json`; dữ liệu lấy tại revision HF ghi trong receipt phát hành. Không trộn snapshot cũ với gate mới.

T07 endpoint lookup và T12 activity-cohort gate đã mở trong phạm vi của chúng. Đây chưa phải nghiệm thu toàn bộ T14 hoặc dự báo RQ3.

## 1. Đổi config và loader nhãn

Sửa `config/t14.yaml`, `load_inputs` trong `T14_Flow_Volatility.py`, và `cex_asof`/`pit_cex_netflow` trong `src/flow_volatility.py`:

- Bổ sung đường dẫn history/gate T07 mới; thay đường dẫn cohort/gate v1 bằng v2. Kiểm tra protocol_id, cohort_sha256, input/output hashes; không chỉ đọc một boolean từ JSON.
- Dùng `src.cex_label_history.load_cex_for_cutoff` hoặc adapter tương đương có kiểm định. Schema mới là `review_status=approved`, `human_verified`, `public_available_at`, `effective_from`, `effective_to`; không đưa vào schema secondary cũ bằng cách backdate verified_at hay sửa loader v1.
- Với cutoff D, availability/effective_from phải <D; effective_to >D hoặc null. Phân biệt public-information PIT với research-knowledge policy của T12 v2. Mốc download, commit author date hay ngày giao dịch không thay được thời điểm nhãn công khai.
- Không overlay toàn bộ T07 hiện tại vào tập PIT. Các bảng CEX hồi cứu vẫn có thể giữ dưới tên retrospective riêng. Không bật pit_cex_labels.enabled rồi coi toàn bộ 465 nhãn T07 hiện tại là hợp lệ.

Ví dụ:

```python
labels = load_cex_for_cutoff(pd.Timestamp(day, tz='UTC'))
cex_D = set(labels.address)
```

Nếu không có nhãn khả dụng, flow là unavailable/NaN; nếu có nhãn và không có transfer thì mới là 0. Không đánh đồng hai ca.

## 2. Tính NetFlow CEX theo tập as-of

Từng ngày dùng C_D, không dùng một tập CEX cuối kỳ cho cả kỳ:

- Inflow: from ngoài C_D, to trong C_D.
- Outflow: from trong C_D, to ngoài C_D.
- NetFlow = Inflow − Outflow; CEX→CEX ghi riêng, không đưa vào external NetFlow của toàn sector. Nếu phân tích từng sàn phải định nghĩa thêm giao dịch giữa hai sàn.
- Chỉ CEX: không tự gộp DEX/router, bridge, market maker hoặc issuer treasury. Tether Treasury trong bảng hồi cứu còn cần correction riêng; nó không nằm trong registry approved này.
- Báo số endpoint khả dụng/hoạt động và coverage USDT theo ngày/tháng/toàn kỳ. Coverage 21,2% là tỷ trọng của tập quan sát, không chứng minh đã nhận diện đủ ví sàn.
- Cả raw và scaled/z-score của nhánh PIT phải dùng chính flow PIT. Không tính một cột pit_cex_netflow nhưng vẫn dùng cex_netflow hồi cứu làm predictor mặc định. Normalization dùng quá khứ `[D−L,D)`.

## 3. Chốt chính sách WhaleFlow trước T15

**Không giữ nguyên cách loại CEX bằng danh sách hồi cứu trong `whale_flow(..., exclude_cex=True)` rồi gọi kết quả là cohort v2 PIT.**

V2 là cohort hoạt động lớn theo research-knowledge; public-history registry vừa duyệt theo mô hình thông tin khác. Có 26 địa chỉ/6.289 member-days của v2 trùng registry CEX lịch sử. Phải công bố overlap và chốt một trong các phạm vi sau trước khi chạy T15:

1. Giữ nguyên cohort v2 để phân tích hoạt động lớn: giữ membership/rank, định nghĩa dòng tiền biên rõ ràng và báo intersection với CEX. Không diễn giải là dòng tiền nhà đầu tư cá nhân, không ngầm dùng W\C như một cohort top50 mới.
2. Nếu nghiên cứu yêu cầu cohort đã loại CEX theo public-history: cần phối hợp người làm T12 ban hành phiên bản tiếp theo, lọc nhãn approved as-of **trước** quantile/z/rank và tính lại top50/kiểm định. Không chỉ xóa 26 ví khỏi bảng top50 tại T14.

Bản loại hạ tầng bằng nhãn cuối kỳ tiếp tục là sensitivity hồi cứu riêng, không đổi tên thành PIT. Không lựa chọn phương án theo dấu hệ số hoặc p-value.

Sau khi scope được chốt, dùng W_D và C_D để tính chiều cohort→CEX trừ CEX→cohort theo quy tắc biên đã ghi. Ghi rõ cách xử lý W_D∩C_D và cạnh nội bộ; báo số node bị tác động, không giấu bằng bộ lọc mặc định.

## 4. Market data, target và cutoff

- Dữ liệu minute căn UTC; thống nhất datetime unit trước khi so sánh, không làm tròn sai timestamp để che lỗi microsecond/nanosecond.
- Đủ 1.440 mốc phút mỗi ngày nếu đầu vào T06 theo lịch đó; kiểm tra duplicate/missing minute, close>0 và first-return boundary. Công bố quy tắc return qua ranh giới ngày và số return hợp lệ; không mặc định mọi ngày đều có đủ return khi thiếu close ngày trước mẫu.
- Chốt RV là sum(r²) hay sqrt(sum(r²)), đơn vị, log/RV=0; giữ sensitivity 1m/5m. Các ngày thiếu dữ liệu không tự điền volatility=0.
- Predictor tổng hợp từ ngày D chỉ khả dụng sau khi D kết thúc. Nếu cutoff là D+1 00:00 UTC, target phải bắt đầu sau cutoff; không lấy volatility đã dùng trong predictor làm future target.
- HAR/control dùng đúng thông tin tại cutoff; normalization/percentile chỉ dùng quá khứ. Forward targets tách khỏi feature_columns và không đưa metadata/readiness flags vào hồi quy.
- Chốt nghĩa horizon h: một ngày D+h hay tổng các ngày D+1…D+h; h=1/3/7 phải đúng đặc tả và không chồng lấn predictor. Không trộn hai định nghĩa.

## 5. Kiểm định và sản phẩm phải bàn giao

- Đủ 655 dòng lịch; phân biệt warm-up/missing/không có flow thật. Không dùng 30 ngày chưa có cohort làm quan sát WhaleFlow=0.
- Kiểm tra direction, CEX internal/external, conservation và ví dụ tính tay; đối chiếu subset as-of độc lập. Không buộc flow PIT phải bằng bảng T12 CEX hồi cứu cũ.
- Truncation/mutation ở nhiều cutoff phải sửa cả dữ liệu tương lai và các nhãn chỉ khả dụng tương lai; feature quá khứ không đổi. Kiểm tra public_available_at/effective_to ngay sát cutoff.
- Chạy hai lần, so SHA-256; thay một input/gate/output phải bị từ chối hoặc đóng readiness. Nhận diện rõ computation_validated, retrospective_analysis và pit_forecast theo từng nhánh.
- Phối hợp T18 chốt split train/test theo thời gian trước mô hình T15; không điều chỉnh ngưỡng bằng kết quả test. Target nhiều horizon chồng lấn cần xử lý khi đánh giá ngoài mẫu/HAC, không suy nhân quả từ liên hệ dự báo.
- Output bảng chỉ Parquet: features, validation, coverage, cohort/CEX overlap và sample-eligibility theo ngày; JSON summary/repro/provenance, cập nhật MD/config. Giữ các đoạn validator thật cần tái lập, dọn run/cache/test giả sau khi đạt.
- Gate RQ3 chỉ mở ở T14 sau khi các điều kiện nhánh tương ứng đạt; không sửa tay cờ T07/T12 để thay nghiệm thu T14.

## Cách lấy đúng bản phát hành

Lấy code GitHub trước, dataset HF sau, tại các revision trong manifest/receipt; giữ cấu trúc thư mục gốc. Đọc `data/hf_t07_t12_release_manifest.json`, kiểm tra hash input liên quan. Không dùng GitHub raw của file Parquet hay tải một Git LFS pointer thay cho bytes thật; dùng huggingface_hub snapshot_download/hf download.

Lệnh kiểm tra sẵn có từ gốc dự án:

```powershell
python scripts/validate_t07_cex_history.py
python scripts/validate_t12_v2.py
```

Các lệnh trên kiểm tra T07/T12 và gate trong scope của chúng, không tự chạy/sửa T14.
