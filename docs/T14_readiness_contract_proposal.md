# Đề xuất hợp đồng readiness đầu vào T14

Phạm vi: hướng sửa cho người phụ trách T14 sau review 1774a71. Đây là đề xuất thay đổi code/đặc tả T14, không phải sửa cờ gate hoặc xác nhận RQ3 đã có kết quả.

## Vì sao đang bị chặn

`T14_Flow_Volatility.py` hiện yêu cầu `ready_for_rq3_pit_forecast` trong gate T07 cho nhánh CEX và trong cả T07/T12 cho nhánh WhaleFlow. Những gate đó chứng nhận nhãn/cohort trong scope upstream và đang giữ cờ RQ3 false. Chờ các cờ đó trước khi T14 được nghiệm thu downstream tạo ra phụ thuộc không đúng vai trò.

T07 chịu trách nhiệm tập nhãn CEX và lịch khả dụng. T12 chịu trách nhiệm cohort và thời điểm chọn. T14 chịu trách nhiệm xây biến, target, cutoff và tính PIT của việc sử dụng các tập đó. T15/T16 trực tiếp phân tích/trả lời RQ3 theo Blueprint08; T18 phối hợp thiết kế đánh giá ngoài mẫu.

## Logic đề xuất

Không thay `false` thành `true` trong JSON T07/T12. Thay việc sử dụng cờ RQ3 upstream làm prerequisite bằng chứng nhận downstream tại T14 với tên/phạm vi rõ ràng:

```python
forecast_inputs_ready_cex = (
    computation_validated
    and t07_endpoint_contract_verified
    and cex_asof_usage_validated
    and market_targets_and_cutoffs_validated
    and predictor_target_separation_validated
    and observed_subset_scope_frozen
)

forecast_inputs_ready_activity_cohort = (
    forecast_inputs_ready_cex
    and t12_activity_cohort_contract_verified
    and cohort_lag_and_hashes_validated
    and whaleflow_scope == 'v2_activity_cohort'
    and overlap_boundary_validated
    and activity_cohort_information_policy_disclosed
)
```

Các tên phụ trong ví dụ phải được triển khai bằng kiểm tra thật và ghi kết quả; không tạo hằng `True` để mở readiness. Giữ các cờ suy luận nhà đầu tư cá nhân đóng; T14 không ghi `rq3_answered=true`.

## Điều kiện nghiệm thu theo nhánh

### CEX

- Gate T07 đúng protocol/history_path; endpoint lookup đã mở; các input/output hash và schema approved/human_verified khớp.
- Nhãn chọn bằng public_available_at/effective_from < D, effective_to > D hoặc null; adapter và ranh giới cutoff đã kiểm thử.
- PIT raw/scaled/z-score đều từ cùng flow PIT; tách CEX internal/external, không trộn DEX/router/bridge/treasury.
- RV 1m, sensitivity 5m, dữ liệu UTC, ngày thiếu, first-return boundary, HAR và target h1/h3/h7 khớp đặc tả; toàn bộ RV/target thiếu phải bị từ chối.
- Truncation/mutation, target/predictor separation, kiểm tra tính tay/độc lập và hash hai lần đều đạt. Metadata/readiness không được đưa vào predictor.
- Coverage báo theo ngày/tháng/toàn kỳ. Phạm vi là **tập endpoint CEX approved quan sát được**, không phải toàn bộ CEX và không coi coverage 21,2% là recall. Không tự đặt ngưỡng coverage mới sau khi xem kết quả mô hình.

### Cohort hoạt động lớn

- Gate T12 v2 ready_for_cohort_whaleflow mở; đúng protocol_id/cohort_path/hash và inputs/outputs; không lấy cờ suy luận cá nhân/RQ3 upstream làm thay nghiệm thu downstream.
- Cohort D chỉ dùng [D−30,D), sau warm-up; giữ membership/rank của v2. Scope v2_activity_cohort được ghi rõ trước T15.
- W∩C_D được báo, giữ nguyên thành viên trong cohort; phía biên flow dùng W\C_D và không gọi đó là cohort top50 mới. Overlap 26 địa chỉ/6.289 member-days được kiểm tra theo snapshot.
- Warm-up no_cohort/insufficient_flow_history, zero_variance và missing_input được phân biệt; complete-case eligibility không đồng nghĩa readiness đã được duyệt.
- Công bố T12 v2 dùng chính sách research-knowledge; CEX endpoints dùng public-history. Chứng nhận input sẵn sàng cho nghiên cứu theo chính sách này không được đổi tên thành cohort đã xác minh nhà đầu tư cá nhân hoặc public-information PIT thuần túy. Nếu RQ3 đòi phạm vi mạnh hơn, cần cohort T12 phiên bản mới trước mô hình.

## Cách phát hành thay đổi

1. Cập nhật T14 code/config/spec và đặt phiên bản hợp đồng readiness mới, chẳng hạn `readiness_contract_version: t14_inputs_v1`; giữ artifact hash để phân biệt output cũ/mới.
2. Xuất `t14_downstream_gate.json` kèm source/config/input/output hashes, scope và policy, kết quả từng điều kiện, blocking reasons theo nhánh. Không chỉ có một boolean.
3. T15/T16 xác thực hợp đồng này và dùng predictor_sets/eligibility đúng nhánh. Retrospective giữ riêng; target không đi vào feature.
4. Test: đóng endpoint/cohort gate, sai hash, đổi cutoff, mutate dữ liệu/nhãn tương lai, RV/target thiếu, scope sai phải bị từ chối/đóng nhánh. Nhánh đạt kỹ thuật và scope approved mới được mở input readiness, không cần T15/T16 đã trả lời RQ3.
5. Đóng băng scope/rules và phối hợp T18 split train/test trước mô hình; không sửa theo hệ số/p-value ngoài mẫu.

Có thể nghiệm thu CEX inputs độc lập với activity-cohort inputs. Nếu nhóm chưa chốt chính sách thông tin của cohort thì chỉ đóng nhánh activity cohort; không buộc các biến thị trường hoặc nhánh CEX hợp lệ phải dừng theo.
## Cập nhật hợp đồng T14 ngày 24/10/2026

Đã triển khai `t14_inputs_v1` theo đề xuất trong `src/t14_readiness.py`, tích hợp tại T14 và validator
`scripts/validate_t14_release.py`. Endpoint/cohort gate T07/T12 được giữ nguyên; các cờ RQ3 upstream
chỉ là metadata tham khảo. Thay cho việc chờ các cờ đó, T14 xuất `t14_downstream_gate.json` với
`forecast_inputs_ready_cex` và `forecast_inputs_ready_activity_cohort` theo điều kiện kỹ thuật/scope.
Hai cờ này chứng nhận input theo phạm vi, không chứng nhận nhà đầu tư cá nhân hoặc RQ3 đã có kết quả.
Consumer mới phải kiểm tra version/hash/gate rồi mới dùng eligibility. Xem đặc tả T14 cho schema mới.
Bản đóng gói hiện tại chỉ ở máy; chưa upload HF.
## Cập nhật phát hành 24/10/2026

Sau khi được người dùng cho phép, gói đã lên GitHub/HF và tải lại xác minh 12/12 file khớp local. Các mô tả chỉ ở máy/chưa upload phía trên ghi trạng thái lúc kiểm định ban đầu. Xem [receipt phát hành và revision cần tải](T14_release_receipt.md).
