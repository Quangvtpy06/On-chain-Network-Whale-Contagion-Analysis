# T12 protocol v2 — cohort địa chỉ hoạt động lớn chưa được định danh

Ban hành ngày 22/10/2026 theo yêu cầu của nhóm, trước khi chạy T15 trong workspace này. Protocol ID: `t12_unidentified_activity_v2`. Không đọc kết quả hồi quy để chọn quy tắc. Không có output T15 cục bộ khi đóng băng; điều này không xác nhận lịch sử truy cập kết quả ở các máy khác.

## Phạm vi và thay đổi so với v1

V2 cho phép danh tính chưa xác minh như một giới hạn được công bố. Không yêu cầu mọi địa chỉ phải được định danh hoặc mọi overlap hạ tầng hồi cứu phải bằng 0 để nghiệm thu **cohort hoạt động lớn**. Đây không phải nghiệm thu cohort nhà đầu tư cá nhân. Tra cứu AI không biến thành xác nhận của thành viên và không sửa T07. `reviewed_unknown` chỉ dùng khi một người thực sự ghi nhận review; hàng AI chưa review vẫn pending.

Giữ nguyên toàn bộ config/ngưỡng v1: 30 ngày lịch `[D−30,D)`, warm-up 30 ngày, top 50, `z(log1p(Value)) + z(log1p(WeightedDegree)) + z(log(PageRank))`, độ lệch chuẩn tổng thể ddof=0, thành phần std=0 đóng góp 0; đồng hạng sắp địa chỉ tăng dần. Value là USDT vào + ra; WeightedDegree là tổng tần suất giao dịch lớn trên các cạnh T09; PageRank là trung bình 30 ngày lịch. Đây không phải số giao dịch duy nhất trên toàn node. Giữ screen chuyển tiếp net/gross ≤0,05, tần suất ≥max(20, phân vị 0,95), giữ cả chín tổ hợp độ nhạy đã định trước. Không chọn lại sau khi xem T15.

Nhánh chính chỉ dùng contract có thời điểm tạo on-chain trước D, zero address và nhãn secondary human-verified đã khả dụng/hiệu lực trước D. Không đưa bảng T07 hiện tại hoặc tra cứu năm 2026 vào bộ lọc lịch sử. Chưa có bằng chứng lịch sử được duyệt thì vẫn unknown tại cutoff. V2 này **không** tự chuyển sang public-history registry hay backdate verified_at; việc đó là thay đổi riêng cần version mới. Khi chứng cứ nhãn bổ sung được duyệt phải tái lập cohort và hash, không vá bảng thành viên.

V1 giữ nguyên ở `data/processed/t12/`; v2 ở `data/processed/t12/v2/`. Gate v1 giữ nguyên. Gate v2 chỉ có hiệu lực với protocol ID và đường dẫn cohort được ghi trong chính gate đó.

## Bản độ nhạy hồi cứu bắt buộc

Nhánh `retrospective` loại địa chỉ T07 hiện tại thuộc CEX, DEX, Bridge, Contract, Other, DeFi hoặc is_contract. Lọc toàn bộ dân số **trước** tính ngưỡng tần suất, chuẩn hóa z và chọn top 50; do đó có thành viên thay thế. Không chỉ xóa 79 địa chỉ khỏi bảng top 50 cũ. Đây là sensitivity dùng nhãn cuối kỳ, không phải cohort PIT.

Xuất so sánh từng ngày: số thành viên chung/bị loại/thay thế, Jaccard, độ ổn định cửa sổ liền kề, tỷ trọng USDT gắn nhãn/hạ tầng và dòng tiền. Tỷ trọng trailing dùng tổng node endpoint volume trong các cửa sổ 30 ngày chồng lấn, không phải volume USDT duy nhất; bảng ngày có thêm tỷ trọng theo volume ngày hiện tại. Chỉ số coverage này là tỷ trọng nhãn quan sát được, không phải recall danh tính thật.

Dòng tiền cohort được tính trên cạnh ngày: inflow từ ngoài cohort, outflow ra ngoài cohort, internal riêng; không đếm hai lần cạnh nội bộ. Chênh lệch inflow−outflow đối chiếu với tổng in_strength−out_strength của node T09. Biến `net_to_current_cex_usdt` = cohort→CEX − CEX→cohort, chỉ tính biên ngoài cohort. CEX lấy nhãn T07 hiện tại, loại nhãn conflict; các dòng này **chỉ dùng mô tả/độ nhạy hồi cứu**, không đưa vào dự báo RQ3 như biến PIT.

Không có ngưỡng Jaccard hoặc tương quan dòng tiền được tối ưu để mở gate: phải báo toàn bộ kết quả kể cả khi khác biệt lớn. Khác biệt lớn làm yếu diễn giải về danh tính/hạ tầng, không được chọn nhánh theo dấu hoặc p-value hồi quy.

## Điều kiện nghiệm thu

1. Config v1 và v2 khớp bản freeze; không dùng kết quả T15 để chọn cấu hình.
2. Hai lần tính độc lập khớp hash của toàn bộ 12 Parquet sản phẩm.
3. Đủ 655 ngày mỗi nhánh; 30 ngày warm-up không có thành viên; tham chiếu độc lập kiểm tra `[D−30,D)`, score/rank/top 50 ở cả hai nhánh, không trùng date/address.
4. Nhánh chính giữ nguyên membership và score v1; nhánh hồi cứu không còn overlap hạ tầng theo định nghĩa đã đóng băng, được tính lại trước chuẩn hóa.
5. Có diagnostics nhãn/USDT, overlap hạ tầng, stability, thay thế và dòng tiền cho mọi ngày; flow bảo toàn với node net T09.
6. Có bằng chứng lookup và trạng thái cho 40 địa chỉ ưu tiên. Không giả làm human review; chưa định danh là giới hạn không chặn scope hoạt động lớn. Danh tính đã xác minh vẫn cần workflow T07 riêng.
7. Ca kiểm soát rỗng, một node/std=0, đồng hạng, ví dụ giải tích ddof=0 đạt; sửa dữ liệu D hoặc tương lai không đổi cohort tại D; tham chiếu phải phát hiện score thật bị sửa.
8. Bất kỳ lỗi provenance/hash/kiểm định đều đóng gate trước khi chạy và không để gate mở từ lần trước. Validator lưu hash code/config/input/output để người khác chạy lại.

Gate đạt chỉ mở `ready_for_cohort_whaleflow` cho cohort hoạt động lớn v2. `ready_for_t14_t15`, `ready_for_individual_investor_inference`, `ready_for_rq3_pit_forecast` vẫn false vì không đại diện nghiệm thu toàn bộ T14/T15, danh tính hay endpoint CEX PIT. Hệ thống downstream phải chọn đúng protocol/path và kiểm tra provenance. Không sửa tay cờ gate.

## Chạy và bàn giao T14

Từ gốc dự án, dùng interpreter PyCharm:

```powershell
python scripts/run_t12_v2.py
python scripts/validate_t12_v2.py
```

T14 đọc gate `data/processed/t12/v2/t12_downstream_gate.json` và cohort do trường `cohort_path` chỉ định. Không tự mở các gate khác hoặc trỏ về cohort v1. NetFlow/WhaleFlow tới CEX cần nghiệm thu riêng lịch sử nhãn endpoint, UTC, độ phủ USDT và timing trước khi coi là dự báo PIT. Nhãn Unknown không phải non-CEX đã xác minh; centrality cao không chứng minh nhà đầu tư cá nhân. Đồ thị chỉ có transfer từ 500.000 USDT, nên tần suất/centrality mô tả mạng con giao dịch lớn.

Giữ code chạy/validator thật và bằng chứng Parquet/JSON; các thư mục chạy lại/control tạm được tự xóa. Không tạo CSV. Kết quả thực tế được ghi trong `T12_v2_completion_report.md` sau nghiệm thu; không đưa số liệu mong muốn vào điều kiện gate.
