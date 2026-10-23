# T14 — so sánh output local với HF

Ngày 24/10/2026. HF dataset `team-crypto/Market-data-crypto-project`, snapshot được ghim: `8163ab9056da671992da2bf90b188cca2e2db79c`. Chỉ đọc HF, không upload hoặc sửa bất kỳ output nào. Local release tiếp tục qua validator t14_inputs_v1.

**Kết luận:** hai gói không giống nhau. Các bảng flow/coverage/overlap/eligibility khớp, nhưng 10 cột RV/HAR/target trên HF khác dữ liệu thật. **Bản local đúng hơn theo đặc tả tính RV từ nến 1 phút T06**, đồng thời đầy đủ hợp đồng readiness và manifest hơn.

## Đối chiếu từng sản phẩm

| Sản phẩm | Kết quả |
| --- | --- |
| t14_cex_coverage_daily.parquet | Cùng 655 dòng, schema và mọi giá trị khớp chính xác |
| t14_cex_coverage_monthly.parquet | Cùng 23 dòng, mọi giá trị khớp chính xác |
| t14_cohort_cex_overlap_daily.parquet | Cùng 655 dòng, mọi giá trị khớp chính xác |
| t14_sample_eligibility_daily.parquet | Cùng 655 dòng, mọi giá trị khớp chính xác, gồm warm-up |
| t14_features_daily.parquet | Cùng 655 dòng/70 cột; flow và phần lớn controls khớp, 10 cột volatility/HAR/target khác đáng kể |
| t14_validation.parquet | Local 81 dòng PASS; HF 64 dòng PASS; 64 dòng chung khớp; local thêm 17 kiểm tra contract |
| t14_reproducibility.json | Cả hai tự khớp hash hai lần chạy của gói mình; hash giữa hai gói khác |
| t14_summary.json | Khác hash minute input, daily market, source/config và hợp đồng readiness |
| t14_downstream_gate.json | Chỉ có local |
| t14_release_manifest.json | Chỉ có local |

Các file Parquet đều khác hash byte. Riêng 4 bảng cùng giá trị, có khác phiên bản ghi metadata: local PyArrow 25.0.1/Pandas 2.2.3; HF PyArrow 26.0.0/Pandas 3.0.6. Hash khác ở các bảng này không phải bằng chứng dữ liệu số sai.

## Những cột số khác thực sự

`rv`, `log_rv`, `realized_vol`, `rv_5m`, `realized_vol_5m`, `log_rv_week`, `log_rv_month`, `target_log_rv_h1`, `target_log_rv_h3`, `target_log_rv_h7`.

- RV/log RV/realized vol và RV 5m/realized vol 5m khác ở cả 654 ngày có giá trị.
- HAR tuần khác 648 dòng, HAR tháng khác 625 dòng.
- Target h1/h3/h7 khác lần lượt 654/652/648 dòng.
- `log_volume_usdt` khác 10 ô ở tối đa 3,55e-15; `taker_imbalance` khác 417 ô ở tối đa 2,29e-16. Đây là sai số máy, không phải khác biệt kinh tế đáng kể.

Ví dụ ngày **02/01/2025**:

| Chỉ số | Local | HF |
| --- | --- | --- |
| RV 1 phút, sum(r²) | 0,0006503000899874552 | 0,000008277118240035295 |
| RV 5 phút, sum(r²) | 0,0006148427672870045 | 0,000041788395689993534 |
| Realized volatility sqrt(RV) | 2,550098% | 0,287700% |

Cùng file `src/flow_volatility.py` có SHA-256 giống nhau trong summary hai bản. Chênh lệch RV không do đổi định nghĩa/công thức của file này, mà do chuỗi giá đầu vào khác.

## Truy nguồn và kiểm tra độc lập

1. Đã kiểm tra hash **655/655 file ngày T06 ở snapshot HF hiện tại**: tất cả giữ nguyên so với nguồn tạo file gộp local.
2. Hash file phút local và file phút gộp hiện có trên HF cùng là:
   `46816308ad14b7491255150bd1bc484c6f54f2d4dca7a25a065f3767dabbb524`.
3. Summary output HF lại khai báo minute input có hash:
   `ff01b316cc80a56e99b8d40cef131e246d3d73ec6f4b4f6a90f7185a9eb85fd9`.
   Vì vậy output HF không được tính từ file phút gộp hiện đang phát hành tại đường dẫn config.
4. Tải nến phút gốc ngày 01–02/01 trực tiếp từ HF rồi tính diff(log(close)): RV 02/01 = **0,0006503000899875011**, khớp local trong sai số số thực; không khớp output HF.
5. Tái dựng giá phút bằng cách reindex **giá close 1 giờ** đang có trên HF sang lưới 1 phút và nội suy tuyến tính theo thời gian. Sau đó tính RV 1m và RV 5m theo cùng định nghĩa. Kết quả **khớp output HF trên toàn kỳ**: sai số RV tối đa 4,78e-18, RV 5m tối đa 1,78e-17.

Bước 5 là bằng chứng rất mạnh rằng chuỗi tạo output HF tương đương giá phút nội suy từ hourly. Chưa có bytes của file input hash ff01... để xác nhận chính đoạn script chuẩn bị file đó; kết luận chắc chắn là RV HF tái dựng được từ hourly interpolation và không khớp giá phút T06 thật. Nội suy không khôi phục dao động nội giờ nên không đáp ứng sản phẩm RV phút theo đặc tả T14.

Cả hai gói đều có thể tự tái lập đúng hash hai lần. Điều đó chứng minh tính nhất quán của lần chạy, không chứng minh đầu vào là dữ liệu phút thật. Kiểm tra provenance và đối chiếu nguồn gốc mới phân biệt được trường hợp này.

## Readiness và hướng sử dụng

Local có hợp đồng `t14_inputs_v1`, hai cờ input-ready theo scope, 17 kiểm tra bổ sung và manifest. HF còn các cờ `pit_forecast_ready_cex/whaleflow` cũ và không có gate/manifest mới. Local chỉ chứng nhận tập CEX approved và activity cohort research-knowledge; không chứng nhận cá nhân/RQ3 đã được trả lời.

- Với flow, coverage, overlap và eligibility: hai gói tương đương về giá trị.
- Với volatility, HAR và target để phân tích/dự báo: dùng **bản local đã kiểm tra với dữ liệu phút gốc**.
- File phút gộp đang trên HF đã đúng; không cần thay 655 file nguồn hoặc tạo lại giá phút bằng nội suy. Cần phát hành lại một gói output T14 nhất quán, gồm features/validation/summary/repro/gate/manifest, khi có chỉ thị upload.
- Nếu T15/T16 đã dùng target của snapshot HF này, cần tính/chạy lại phần phụ thuộc sau khi thay gói đầu vào.

Chưa upload theo yêu cầu giữ output local. Đối chiếu thực hiện trong bộ nhớ, không giữ bản data tải xuống hoặc script test tạm. Bằng chứng máy đọc được: [T14_local_vs_HF_comparison.json](T14_local_vs_HF_comparison.json).