# T20–T22 — giao thức bắt buộc Graph ML cho RQ5

Nguồn công việc: hàng T20–T22 của `Phan_cong_Blueprint08.xlsx`; câu hỏi RQ5 trong `08_onchain_whale_network.md`. Giao thức `graph_ml_stage4_v1` và mọi tham số được đóng băng tại `config/graph_ml_stage4.yaml` trước khi xem kết quả test. T23 là phần mở rộng và chỉ được bắt đầu sau khi T20, T21, T22 chạy đạt và được kiểm định độc lập.

## Tập dữ liệu và ý nghĩa nhãn

T19 đã nghiệm thu là đầu vào bắt buộc. **Tuần ISO đầy đủ** là tập chính; lấy đúng 41 predictor trong `t19_feature_dictionary.parquet`, nhãn CEX/DEX hợp lệ và split train/validation/test có gap một tuần. Không huấn luyện trên `Unknown`, `Contract`, `Other`, địa chỉ hay nhãn/metadata. T19 đã loại tuần đầu/cuối không đủ ngày. Dùng graph T08 `dynamic_edges_weekly.parquet`, chỉ cùng cửa sổ với mỗi hàng T19. Chỉ có transfer USDT từ 500.000 trở lên.

Bản T19 trên HF (revision `25becf91d38a38ef7998d26b3b148e4109ef1f05`) và bản chạy lại bằng pandas 2.2.3 có cùng nội dung bảng nhưng khác byte Parquet. Loader kiểm tra SHA byte của từng bảng với summary **của chính bản T19 đang đọc**, rồi dùng hash tên cột + giá trị để ràng buộc T20–T23 giữa hai kiểu ghi Parquet. Môi trường đã chạy được ghi tại `requirements-stage4.txt`; thay phiên bản thư viện cần đối chiếu lại hash nội dung và kết quả mô hình.

Nhãn T07 được xác minh hồi cứu và không có ngày khả dụng lịch sử cho từng địa chỉ. Vì vậy đây là **phân loại CEX/DEX trên graph và feature cùng cửa sổ**, không phải dự báo nhãn tại thời điểm quá khứ, không phải nhận diện nhà đầu tư cá nhân. Tập địa chỉ có nhãn lệch chọn mạnh. Tập test chứa nhiều ví đã có trong train; phải báo riêng hàng của ví chưa thấy trong train và số ví DEX mới.

## T20: tabular MLP và Node2Vec

Fit median imputer và standard scaler chỉ trên toàn bộ node của các tuần train; clip giá trị chuẩn hóa theo config. MLP dùng class-weight để xử lý lệch lớp, chọn epoch tốt nhất bằng macro F1 validation. Node2Vec đi random walk bậc hai trên **hợp graph các tuần train**, không đưa cạnh validation/test vào việc học embedding. Cấu hình mặc định p=q=1 là trường hợp unbiased của Node2Vec. Vector của địa chỉ train được cố định sau fit; địa chỉ mới dùng trung bình vector của hàng xóm thuộc graph train **trong chính tuần cần phân loại**, hoặc zero và cờ unavailable nếu không có. Điều này là tính năng đồng thời của cửa sổ, không được diễn giải là điểm thời gian trước cửa sổ. So MLP 41 feature với MLP 41 feature + 16 chiều Node2Vec + cờ unavailable trên cùng hàng/nhãn.

## T21: GCN và GraphSAGE

Mỗi tuần là một graph riêng, chuyển cạnh có hướng T08 thành cạnh hai chiều để message passing. Không có cạnh nối giữa tuần train và tuần tương lai. GCN và GraphSAGE hai lớp đọc cùng vector chuẩn hóa của T20; hàng không nhãn có thể làm hàng xóm nhưng không đóng góp loss. Fit tham số chỉ từ tuần train, chọn epoch theo macro F1 validation, đánh giá test một lần. Không dùng Node2Vec làm input cho GNN để phép so sánh kiểm tra đóng góp của cấu trúc lân cận.

## T22: GAT và phép so sánh RQ5

GAT hai lớp với cùng split, feature và lịch chọn epoch. Bảng so sánh gồm tabular MLP, MLP+Node2Vec, GCN, GraphSAGE, GAT: macro F1, precision/recall/F1 từng lớp và số hàng/địa chỉ của test toàn bộ và test ví mới. Quy tắc chính: chọn GNN có macro F1 validation cao nhất (đồng hạng theo tên), so macro F1 test của nó với tabular MLP. Khoảng tin cậy 95% chính cho chênh lệch lấy bootstrap **cụm địa chỉ** để các hàng cùng ví không bị coi độc lập. Kiểm tra độ nhạy bổ sung sau review dùng bootstrap khối **3 tuần liên tiếp** để xét cú sốc thị trường chung; nó không thay kiểm định chính. Không chọn lại mô hình, feature, threshold hoặc split theo test. CI chính phải nằm hoàn toàn trên 0 mới gọi là bằng chứng GNN tốt hơn ở mức 5% trong mẫu này; báo số hỗ trợ DEX ví mới và không khái quát khi quá nhỏ.

## Tiêu chí nghiệm thu trước T23

T20/T21/T22 phải chạy thành công trên đúng hash T19/T08; kiểm định khóa, số hàng, sample alignment, provenance, finite probability, macro F1 và confusion matrix tái tính độc lập đạt. Chạy lại hai tiến trình với seed hash khác nhau và đối chiếu nội dung output. Review thủ công giới hạn nhãn hồi cứu, lệch chọn và ví mới. Nếu có FAIL hoặc phát hiện leakage/so sánh khác mẫu, sửa và kiểm định lại trước khi tạo bất kỳ output T23 nào.

Bảng data chỉ Parquet. JSON dùng cho cấu hình nguồn/hash/kết quả review; Markdown và hình chỉ là báo cáo. Các file test/bản chạy tạm được xóa sau nghiệm thu, giữ lại validator dữ liệu thật và bằng chứng review.
