# T14 — completion report: t14_inputs_v1

Ngày hoàn tất: 24/10/2026. Bản đóng gói **chỉ tại máy**, chưa upload HF, chưa push source lên GitHub. Source base commit 1774a71; thay đổi working tree được ghim bằng SHA-256 trong gate/manifest.

## Kết quả

Đã thay phụ thuộc cờ RQ3 upstream bằng hợp đồng nghiệm thu input downstream theo phạm vi. Gate T07/T12 không bị sửa và byte hash vẫn khớp trước/sau kiểm tra.

| Trường | Trạng thái |
| --- | --- |
| readiness_contract_version | t14_inputs_v1 |
| computation_validated | true |
| retrospective_analysis_ready | true |
| forecast_inputs_ready_cex | true |
| forecast_inputs_ready_activity_cohort | true |
| ready_for_individual_investor_inference | false |
| rq3_answered | false |
| upload_performed | false |

CEX inputs chỉ mô tả tập ví CEX approved quan sát được, không phải toàn bộ ví sàn. Activity-cohort inputs dùng cohort hoạt động lớn T12 v2 với chính sách research-knowledge, giữ membership/rank và biên W\C_D; không chứng nhận danh tính cá nhân hoặc đổi cohort thành public-information PIT thuần túy. T15/T16 trực tiếp trả lời RQ3 và T18 phối hợp split/evaluation trước mô hình.

## Thay đổi đã triển khai

- `src/t14_readiness.py`: các điều kiện bắt buộc, kiểm tra độc lập lịch/RV 1m/5m/HAR/target, metadata cohort lag/rank/membership, warm-up; tính readiness riêng từng nhánh và fail closed khi thiếu bằng chứng.
- `T14_Flow_Volatility.py`: xác thực manifest phút; snapshot/recheck input/source/config/upstream gates; xuất gate và manifest sau kiểm định. Các cờ RQ3 upstream chỉ còn metadata tham khảo.
- `scripts/validate_t14_release.py`: kiểm tra version/provenance/hash, tái lập và tính lại predicate readiness trước downstream use. Không upload hoặc sửa gate.
- Config đóng băng scope/policy rõ ràng; đặc tả, README và handoff cập nhật. Bộ chuẩn bị manifest chung nhận dạng đầy đủ output và validator mới, không còn yêu cầu T12 v1 hoặc chỉ một hash tái lập.
- `/market/` được loại khỏi Git để dataset tiếp tục lưu trên HF theo quy ước.

## Kiểm định cuối

- CLI chạy đủ trên dữ liệu thật, exit code 0; 655 ngày UTC, đủ 943.200 nến phút.
- **81/81** dòng validation PASS, bao gồm 17 kiểm tra dữ liệu/metadata bổ sung cho hợp đồng mới.
- **5/5** bảng được tính hai lần có SHA-256 khớp. Các file gate/summary/manifest là metadata đóng gói và được kiểm tra binding/hash riêng, không tuyên bố chúng là kết quả hash hai lần.
- **15/15** ca readiness đạt: endpoint/cohort gate đóng, scope chưa chọn, version/policy sai, suy luận cá nhân sai scope, thiếu bằng chứng, cutoff/future-label/cohort lag sai, tái lập thiếu hoặc mismatch đều không được mở nhánh. Đóng cohort không tự đóng CEX khi các điều kiện CEX vẫn đạt.
- **5/5** ca sửa artifact bị validator từ chối: output Parquet, config, cờ gate kể cả cập nhật hash tương ứng, provenance rỗng, input market. Mọi byte dùng để thử sửa đã được khôi phục; validator kiểm tra gói cuối lại thành công.
- Validator xác minh 9 artifact được manifest liệt kê; cả hai nhánh input readiness mở, các cờ ownership/RQ3 vẫn false. T07/T12 gate byte hashes không đổi.

Bằng chứng các ca bổ sung: [T14_readiness_validation_evidence.json](T14_readiness_validation_evidence.json). Source kiểm định thật được giữ để tái lập; không tạo/giữ script test giả. Cache lượt tính thứ hai được pipeline tự dọn.

## Gói output tại máy

Thư mục `data/processed/t14/`: **6 Parquet + 4 JSON**:

- `t14_features_daily.parquet`
- `t14_cex_coverage_daily.parquet`
- `t14_cex_coverage_monthly.parquet`
- `t14_cohort_cex_overlap_daily.parquet`
- `t14_sample_eligibility_daily.parquet`
- `t14_validation.parquet`
- `t14_summary.json`
- `t14_reproducibility.json`
- `t14_downstream_gate.json`
- `t14_release_manifest.json`

Manifest liệt kê chính xác 9 file còn lại, source/config/input hashes, remote dependencies và phạm vi nghiệm thu. Không tự chứa hash của chính nó. Publisher chỉ được gọi khi có chỉ thị upload mới; lần này không gọi publisher.

Lệnh kiểm tra trước khi bàn giao T15/T16:

```powershell
python scripts/validate_t14_release.py
```

Sau khi validator đạt, chọn đúng nhánh readiness, rồi mới dùng eligibility theo horizon và predictor_sets. Không lấy target/metadata/readiness làm predictor; không dùng nhánh hồi cứu thay PIT.
## Cập nhật phát hành 24/10/2026

Sau khi được người dùng cho phép, gói đã lên GitHub/HF và tải lại xác minh 12/12 file khớp local. Các mô tả chỉ ở máy/chưa upload phía trên ghi trạng thái lúc kiểm định ban đầu. Xem [receipt phát hành và revision cần tải](T14_release_receipt.md).
