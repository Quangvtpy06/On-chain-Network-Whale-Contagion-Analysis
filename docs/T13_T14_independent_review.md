# Review độc lập T13–T14 — 22/10/2026

## Kết luận

- **T13:** 20 bảng Parquet có số liệu đúng theo phương pháp đã mô tả. Có thể dùng làm bằng chứng mô tả RQ1/RQ2 trong mạng con chuyển USDT lớn. Code nguyên bản chưa chạy hết trong môi trường PyCharm hiện tại vì phép so sánh timestamp microsecond/nanosecond; bàn giao còn sai quy ước CSV và thiếu khả năng tái tạo đúng bộ hình đã công bố.
- **T14:** bảng 655 ngày tái tạo đúng giá trị, NetFlow/RV/chuẩn hóa quá khứ đúng trên dữ liệu hiện có. **Chưa đạt yêu cầu tất cả point-in-time cho dự báo** vì nhãn CEX hồi cứu; cờ readiness hiện tại gây hiểu nhầm, WhaleFlow chưa có cohort bị điền 0 và kiểm định chưa bắt được các lỗi ngữ nghĩa quan trọng.
- Không cần T14 để trả lời hai RQ đầu ở mức mô tả/association. T14 chủ yếu chuẩn bị biến cho RQ3/T15, không tự chứng minh quan hệ dự báo hoặc nhân quả.

## Phạm vi và phiên bản

- GitHub: [82a6b3b8c705d82b7d0e018c5c069c9643aec4ec](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/tree/82a6b3b8c705d82b7d0e018c5c069c9643aec4ec).
- HF: [026e2dfa93a72f0c77f9a029d70df92501108301](https://huggingface.co/datasets/team-crypto/Market-data-crypto-project/tree/026e2dfa93a72f0c77f9a029d70df92501108301).
- Kiểm tra code T13, reader, T14, module flow, config, tài liệu; đọc 20 Parquet + 4 PNG T13 và 2 Parquet + 2 JSON T14. Tại phiên bản này **không có biểu đồ trong data/processed/t14**; code T14 cũng không có bước vẽ hình.
- Dữ liệu thị trường: 943.200 phút, 15.720 giờ, 655 ngày. T08/T09 dùng các bản local đã có và đối chiếu provenance của T14 với HF. Đủ 9/9 input SHA, 2/2 code SHA và SHA config T14 khớp.
- Môi trường PyCharm: Python 3.12.5, pandas 2.2.3, PyArrow 25.0.1. Cài statsmodels 0.15.0 do môi trường thiếu gói đã khai báo trong requirements.
- Không sửa code production, không ghi đè output chuẩn, không push trong lượt review. Bản sao code/dữ liệu và script kiểm tra nằm tạm trong cache, được xóa sau review; chỉ giữ báo cáo và bằng chứng JSON tại data/processed/reviews/t13_t14_review.json.

## Phát hiện cần xử lý, theo mức ưu tiên

### 1. T14: readiness tính toán không đồng nghĩa readiness dự báo PIT

[T14_Flow_Volatility.py:57,124–126](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/82a6b3b8c705d82b7d0e018c5c069c9643aec4ec/T14_Flow_Volatility.py#L124)

Output ghi cex_labels_pit=false nhưng ready_for_t15_cex_netflow=true. Bộ nhãn CEX dùng danh tính đã biết hiện tại cho cả quá khứ, không có lịch sử available_from cho từng nhãn. Bốn kiểm tra truncation giữ nguyên tập CEX nên không kiểm tra được leakage từ nhãn. Việc công thức NetFlow chỉ dùng giao dịch ngày D không giải quyết được vấn đề này.

Cần tách cờ technical_validation_passed, retrospective_analysis_ready và predictive_pit_ready. Với dữ liệu hiện tại, cờ dự báo CEX phải false; chỉ cho phép phân tích hồi cứu hoặc thu thập lịch sử khả dụng nhãn và as-of join. Nhánh large_transfer_count/volume không dùng nhãn vẫn có thể phát triển độc lập; các cột large_*_cex vẫn chịu giới hạn nhãn CEX. Gate cohort WhaleFlow hiện false là đúng, không tự mở vì review này.

### 2. T13: nguyên bản không chạy hết trên dữ liệu HF hiện tại trong môi trường này

[T13_Network_Statistics.py:291](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/82a6b3b8c705d82b7d0e018c5c069c9643aec4ec/T13_Network_Statistics.py#L291)

timestamps.equals(expected) trả false vì dữ liệu minute có datetime64[us, UTC], expected là datetime64[ns, UTC]. Ngày 01/01/2025 có đủ 1.440 timestamp, không trùng, tất cả giá trị thời gian bằng expected. Nguyên bản dừng với Invalid 1-minute timestamps.

Chuẩn hóa timestamps.as_unit('ns') trước khi so sánh, hoặc so giá trị thời gian sau khi kiểm tra chiều dài, thứ tự, uniqueness. Review chỉ sửa một dòng này trong bản sao tạm; sau đó toàn pipeline chạy hết. Không được diễn giải kết quả này thành nguyên bản chạy thành công không cần sửa.

### 3. T14: 30 ngày không có cohort bị mã hóa thành zero flow

[src/flow_volatility.py:60–85,228](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/82a6b3b8c705d82b7d0e018c5c069c9643aec4ec/src/flow_volatility.py#L60)

30 ngày đầu has_cohort=false nhưng whale_to_cex_usdt, cex_to_whale_usdt, whaleflow_usdt được khởi tạo bằng 0. Chỉ bản wf dùng cho scaled/z bị mask NaN. Điều này trái đặc tả và khiến người dùng cột thô hiểu thiếu cohort là đã quan sát được không có flow.

Cần mask NaN cho ba cột WhaleFlow thô khi chưa có cohort hợp lệ, giữ 0 cho trường hợp có cohort hợp lệ và thực sự không có giao dịch. Nên công bố thêm số thành viên sau khi loại CEX. Cohort thực tế hiện tại có information_cutoff < date trên mọi dòng; tuy nhiên loader T14 chỉ giữ date/address, nên không kiểm tra được điều này ở các lần chạy sau.

### 4. T14: validation PASS chưa đảm bảo đúng ngữ nghĩa kiểm tra

[src/flow_volatility.py:286–315](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/82a6b3b8c705d82b7d0e018c5c069c9643aec4ec/src/flow_volatility.py#L286)

- available_after_day_end thực chất chỉ kiểm tra available_at > đầu ngày. Negative control trên dữ liệu thật: đổi available_at thành D 01:00 UTC, cờ này vẫn PASS dù chưa quan sát đủ D. Bảng đã công bố có available_at đúng D+1 00:00; lỗi nằm ở độ chặt của validator.
- cohort_excludes_cex chỉ kiểm tra số địa chỉ bị loại >=0; không chứng minh tập cohort sử dụng không chứa CEX.
- pit_check cắt hàng tương lai nhưng giữ nguyên nhãn và không tái dựng cohort từ nguồn lịch sử. PASS chỉ chứng minh tính bất biến của feature với những input được cắt, không chứng minh toàn bộ nguồn thông tin point-in-time.
- feature_columns trả mọi cột không có tiền tố target_, gồm metadata, gate và WhaleFlow bị chặn. Trước T15 cần whitelist predictor theo từng nhánh, kiểm tra gate rõ ràng, không dùng cả danh sách này như tập biến hồi quy.

### 5. T13: output và hình chưa tái tạo đúng chuẩn bàn giao

[T13_Network_Statistics.py:176–195,1894–1940,2160–2180](https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis/blob/82a6b3b8c705d82b7d0e018c5c069c9643aec4ec/T13_Network_Statistics.py#L176)

- write_csv vẫn ghi 20 CSV rồi ghi thêm Parquet. Cần bỏ CSV theo quy ước nhóm.
- Default output là data/processed/t13_recomputed và outputs/figures/t13_recomputed; không phải data/processed/t13 và thư mục figures của nó. Nên có chế độ xuất chuẩn có kiểm soát, mode review riêng rõ ràng.
- Pipeline tạo network_dynamics.png, centrality_distribution.png, flow_concentration.png, normal_vs_stress.png. HF công bố bốn tên t13_*.png; hai hình activity/PageRank là thiết kế khác hình do code tạo. Giá trị hình đã công bố phù hợp các bảng nhưng chưa có bước code tái tạo đúng thiết kế/tên/path đó.
- docs/T13_completion_report.md còn bốn link assets/t13/... trong khi commit cuối đã xóa docs/assets/t13. Cần trỏ tới hình HF ở revision phù hợp hoặc vị trí tồn tại.
- T13 chưa có manifest input/code/output hash và validation machine-readable như các task trước. Nên bổ sung để biết bảng dùng chính xác input nào; cố định revision khi đọc HF.

### 6. Hai định nghĩa volatility khác nhau cần công bố thống nhất

T13 rv = sqrt(sum squared minute returns), tức realized volatility theo phút. T14 rv = sum squared hourly returns, tức realized variance theo giờ; T14 realized_vol mới là sqrt(rv). Không có lỗi toán học trong hai định nghĩa riêng này, nhưng không được merge hoặc so sánh hai cột rv như cùng đơn vị/estimator. Cần tên/metadata rõ variance vs volatility, tần suất lấy mẫu, ngày đầu thiếu close quá khứ; chọn một estimator chính và báo độ nhạy nếu dùng estimator còn lại.

T14 large_transfer_* hiện đo cạnh theo cặp địa chỉ trong ngày có total_value vượt ngưỡng, không đếm từng transfer/transaction. Công thức khớp config/đặc tả hiện tại; nên đặt tên large_edge_* hoặc chuyển nguồn sang transfer netted nếu muốn biến sự kiện giao dịch lớn của RQ3.

## Kiểm định đã thực hiện và giới hạn

| Kiểm tra | Kết quả |
|---|---|
| Chạy T13 nguyên bản | FAIL tại kiểm tra dtype timestamp; statsmodels ban đầu thiếu đã cài |
| Chạy T13 sau một sửa tương thích trong bản sao tạm | PASS toàn pipeline; đủ 655 ngày, 92 tuần đầy đủ |
| So 20 bảng T13 tái tính với HF | 20/20 khớp trong tolerance 1e-8, không thay nội dung phương pháp |
| RV T13 từ 943.200 giá phút, tính riêng bằng log tỷ số giá | Khớp; sai số tuyệt đối tối đa 2,22e-15; toàn bộ nhãn stress khớp |
| Top-K tính độc lập bằng sort Python + math.fsum | 5.895/5.895 nhóm khớp; max share diff 5,55e-16 |
| HAC độc lập bằng OLS NumPy + sandwich Bartlett 7 lag | 11 RQ1 + 9 RQ2 khớp beta, SE, p-value |
| BH-FDR tính riêng bằng thứ tự p-value | Khớp 20 kiểm định trong hai family riêng 11/9 |
| T14 input/code/config provenance | 9/9 input, 2/2 code và config khớp ghi nhận; inputs khớp HF pinned revision |
| Tái tính toàn bộ core feature T14 | Khớp bảng 655 ngày; numeric values và dtype không khác |
| NetFlow tính độc lập từ tổng nhận trừ tổng gửi của tập CEX | 655/655 ngày; max diff 8,34e-7 USDT do thứ tự cộng số thực; 465 CEX |
| RV T14 tính riêng bằng timestamp join close giờ trước | 654 ngày hợp lệ; max diff 1,73e-18; ngày đầu NaN |
| Z-score past-only tính bằng slice quá khứ từng ngày | 655 ngày × 2 series CEX/WhaleFlow khớp |
| Quantile cạnh từ slice quá khứ riêng | 625 ngày đủ lịch sử; threshold diff 0; count mismatch 0 |
| Cutoff cohort và availability hiện có | Tất cả cutoff < date; available_at đúng D+1 00:00 |
| T14 pit truncation | 4/4 mốc PASS; không kiểm tra được PIT của nhãn |
| T14 validator negative control | Phát hiện kiểm tra availability quá yếu như mục 4 |
| T14 artifact reproducibility | SHA published khớp JSON run1/run2; hai lần serialize ở môi trường review khớp nhau nhưng khác byte published, dù numeric/dtype khớp; không coi đây là tái lập byte độc lập published |

T14 review chạy full core feature và kiểm tra độc lập các công thức chính; không gọi main CLI ghi vào output chuẩn. Hai lần serialize trong review không phải hai phép tính độc lập. Không thay thế hạn chế này bằng tuyên bố independent full-run hash match.

## RQ1: có thể trả lời gì từ T13?

RQ1 trong blueprint: cấu trúc transaction network thay đổi thế nào giữa normal và stress?

T13 dùng stress = RV ETH/USDT phút > P90 của cả mẫu 655 ngày. P90 = 4,869485%; có 589 ngày normal, 66 ngày stress. Đây là phân loại hồi cứu theo volatility thị trường, hợp lý cho so sánh mô tả RQ1; không phải nhãn stress đã biết trước ngày giao dịch hoặc bằng chứng dự báo. CMSI/sensitivity đều dùng toàn mẫu nên cũng chỉ dùng hồi cứu.

| Chỉ số | Mean stress so với normal | BH p-value, sau kiểm soát trend trong HAC |
|---|---:|---:|
| Nodes | +21,90% | 0,0000213 |
| Edges | +28,75% | 0,0000213 |
| Volume USDT | +33,98% | 0,003997 |
| Transactions | +32,28% | 0,0000744 |
| Density | -17,79% | 0,0000286 |
| Reciprocity | -4,48% | 0,1423 |
| Top-10 volume share | -4,33% | 0,1038 |
| Gini volume | +1,32% | 0,1423 |
| HHI volume | -8,87% | 0,1346 |

Thay đổi phần trăm ở bảng là chênh lệch mean thô; p-value kiểm định beta stress có trend, không phải test đúng cùng một estimand mean ratio. Kết luận được hỗ trợ: stress volatility cao đi kèm mạng lớn/hoạt động mạnh hơn nhưng density thấp hơn. Không có bằng chứng đủ để nói mọi chỉ số tập trung đều tăng. So sánh tuần loại hai tuần thiếu ngày, còn 92 tuần (82 normal/10 stress).

T04–T12 là đầu vào và metrics; chỉ tới T13 có market regimes + so sánh + suy luận mới hình thành câu trả lời RQ1. T14 không phải điều kiện bắt buộc cho câu trả lời này. Giới hạn: USDT đã netting, threshold >=500.000 USDT, không phải toàn Ethereum hay toàn bộ token transfer; bậc và centrality bị cắt xén.

## RQ2: có thể trả lời gì từ T13?

RQ2: các ví trung tâm có vai trò disproportionate trong flows không?

Top 1% địa chỉ theo PageRank chiếm trung bình 30,5631% incident flow trong normal và 35,6130% trong stress. Chênh mean +5,0499 điểm phần trăm; beta stress có trend +3,9640 điểm phần trăm, BH p=0,000978. Tỷ trọng hơn nhiều node share là bằng chứng mô tả về sự tập trung dòng tiền ở nhóm địa chỉ trung tâm; không phải kiểm định nhân quả hay vai trò độc lập trong dự báo.

Incident flow share = tổng in+out-strength của nhóm / tổng in+out-strength mọi node; mẫu số bằng hai lần volume cạnh. Không diễn giải thành tỷ lệ transfer duy nhất đã đi qua nhóm. Top-K chọn lại trong mỗi cửa sổ từ cùng ngày; dùng được cho RQ2 mô tả, không dùng để khẳng định nhóm được biết trước cho WhaleFlow dự báo.

Xếp theo weighted degree rồi đo share weighted degree có tính cơ học; ưu tiên bằng chứng degree/PageRank và nêu tính đồng thời. PageRank cũng xuất phát từ cùng đồ thị có trọng số, không phải thước đo ngoại sinh. Không gọi các địa chỉ đó là nhà đầu tư cá nhân hay tổ chức đã xác minh. Nhãn T07 thấp không ngăn trả lời RQ2 ở mức address-network, nhưng ngăn kết luận danh tính/chủ thể kinh tế.

Phân phối daily đang pool node-day, weekly đang lấy thống kê từng tuần rồi trung bình tuần; cần ghi rõ hai cách cân trọng số này. Biểu đồ histogram log(1+degree) hiển thị đúng nhưng không tự so sánh hai regime.

## Điều kiện nghiệm thu đề nghị

1. T13 sửa timestamp, chỉ xuất Parquet, thống nhất canonical paths và code sinh bốn hình/link báo cáo; bổ sung provenance/validation.
2. T14 sửa missing-cohort semantics và kiểm định cutoff/availability/membership; tách cờ readiness kỹ thuật khỏi predictive PIT và whitelist predictor theo gate.
3. Với nhãn CEX hiện tại, chỉ nghiệm thu NetFlow hồi cứu; giữ chặn khẳng định dự báo PIT CEX/WhaleFlow. Không cần chặn nhánh biến thị trường hoặc large-edge không phụ thuộc nhãn.
4. Thống nhất tên variance/volatility và sampling; ghi rõ h=3/7 hiện là volatility của riêng ngày D+h, không phải volatility cộng dồn 3/7 ngày.
5. Không cần đợi T14 để viết phần kết quả RQ1/RQ2 như phạm vi ở trên; sửa các lỗi kỹ thuật/bàn giao trước khi tuyên bố task hoàn tất.
