# T10 — Betweenness, eigenvector và clustering

Chạy `T10_Heavy_Graph_Metrics.py` từ thư mục gốc `crypto`. Dùng SDK Python của
PyCharm. Đường dẫn/lịch lấy từ `config/config.yaml`, tham số T10 từ
`config/t10.yaml`. Tách cấu hình riêng giúp thêm T10 không thay đổi config đã
được ký hash cho T09. T10 phụ thuộc T08 đã nghiệm thu, không phụ thuộc T09.

## Đồ thị và cửa sổ

Đọc cạnh có hướng đã netting của T08. Kiểm tra ready flag, hash hai lần chạy T08,
địa chỉ, cạnh trùng, cạnh tự trỏ và trọng số trước khi tính. Không cộng ngầm cạnh
trùng. Giữ toàn bộ lịch 655 ngày UTC và 94 tuần ISO bắt đầu thứ Hai; cửa sổ rỗng
có một dòng snapshot, không thêm ví giả vào bảng node. Tuần đầu/cuối thiếu ngày
có `eligible_for_regression=false` trên cả bảng node và bảng cửa sổ.

## Định nghĩa chỉ số

- `betweenness`: có hướng, không tính endpoints, chuẩn hóa theo các cặp có thứ
  tự `(n-1)(n-2)`. Khoảng cách là số cạnh; volume USDT không phải khoảng cách.
  Brandes chính xác khi n ≤ 500. Trên ngưỡng: 128 nguồn lấy mẫu không hoàn lại,
  seed SHA-256 của seed cấu hình, loại cửa sổ và mã cửa sổ; thứ tự node/cạnh cố
  định. NetworkX 3.7 chuẩn hóa lấy mẫu có điều kiện theo việc node có thuộc mẫu
  nguồn hay không. `betweenness_method`, `betweenness_pivots`, `sampling_seed`
  giúp phân biệt số ước lượng và số chính xác.
- `eigenvector`: vector riêng trái không âm của ma trận trọng số USDT,
  `A.T x = lambda x`, chuẩn L2 bằng 1. Dùng dense eig với n ≤ 64, ARPACK cho
  các đồ thị lớn, khởi tạo xác định, kiểm tra phương trình riêng với sai số tương
  đối ≤ 1e-8. Có scale trọng số để tránh vấn đề số học; trị riêng bàn giao đổi
  về đơn vị USDT. Không đổi sang PageRank hoặc đồ thị vô hướng khi không hội tụ.
  Trường hợp không đạt sai số sẽ dừng, không công bố bản hoàn tất.
- Đồ thị rời rạc/không liên thông mạnh có thể có eigenvector không duy nhất hoặc
  bằng 0 trên các thành phần không trội. `eigenvector_may_be_nonunique` là cờ
  cảnh báo bảo thủ. DAG có trị riêng trội bằng 0: dùng vector đều trên các sink,
  gắn `eigenvector_ranking_degenerate=true`; không dùng kết quả đó xếp hạng
  ảnh hưởng. Đây là nghiệm phương trình riêng, không phải centrality duy nhất.
- `clustering`: hệ số tam giác có hướng theo NetworkX/Fagiolo, bằng 0 khi mẫu
  số bằng 0. `clustering_weighted` thêm trung bình hình học của trọng số đã chia
  cho trọng số lớn nhất trong từng cửa sổ. Cả hai được tính chính xác vì đồ thị
  T08 hiện tại đủ thưa; không cần xấp xỉ mọi chỉ số.

## Bàn giao và kiểm định

Trong `data/processed/t10`: hai bảng `node_metrics_daily/weekly.parquet` (khóa
`window_type,time_window,address`); hai bảng `snapshot_metrics_daily/weekly.parquet`
với số node/cạnh, trung bình chỉ số, phương pháp và sai số eigenvector;
`t10_validation.parquet`, `t10_sampling_quality.parquet`, `t10_summary.json`,
`t10_reproducibility.json`, `t10_review.json`. Không xuất CSV.
Bảng node có thể ghép với T09 theo `window_type,time_window,address`; chọn các
cột chỉ số cần dùng để tránh nhân đôi các cột metadata khi ghép.

Mọi node/cửa sổ được kiểm tra bằng công thức tam giác ma trận thưa độc lập và
phương trình eigenvector. Bộ nghiệm thu `scripts/validate_t10_current.py` dùng
API shortest-path subset và tự chuẩn hóa lại để đối chiếu betweenness trên
toàn bộ 749 cửa sổ, đồng thời kiểm tra khóa, metadata, lịch và hash nguồn/đích.

Ở mỗi độ phân giải, chọn 3 cửa sổ theo số node nhỏ nhất, trung vị, lớn nhất để
đối chiếu betweenness chính xác. Bảng sampling_quality công bố MAE, RMSE, sai số
tuyệt đối lớn nhất và độ trùng top 20. Đây là sai số đo trên các cửa sổ được
chọn, không phải khoảng tin cậy hoặc cam kết độ chính xác cho mọi cửa sổ.
Nếu nghiên cứu cần top ví ổn định hơn, tăng số pivot hoặc tính chính xác trên
cửa sổ cần phân tích rồi chạy lại toàn bộ quy trình nghiệm thu.

Chương trình chạy hai lần, so SHA-256 của cả 6 bảng Parquet, xóa bản chạy thứ
hai khỏi `.cache` trong finally. Chỉ bàn giao khi kiểm định và tái lập đều đạt.
Entry point tự khởi động tiến trình Python với `PYTHONHASHSEED=0`: NetworkX
duyệt tập hợp địa chỉ khi cộng trọng số tam giác; cố định seed ngăn chênh vài
bit số thực giữa các tiến trình riêng. Seed hash Python khác với seed lấy mẫu
betweenness và cả hai đều được ghi lại. Cache được thử quyền ghi trước khi tính.
`--skip-reproducibility` chỉ khảo sát và không bật ready flag. Mã test giả được
xóa sau khi đạt; giữ kiểm định dữ liệu thật để lần chạy sau vẫn có nghiệm thu.

Một ERC-20 event không nhất thiết là dòng tiền kinh tế độc lập. Netting T08 chỉ
giảm các vòng trực tiếp; các chỉ số T10 vẫn chịu giới hạn vòng nhiều bước và
ngưỡng 500.000 USDT. Centrality/clustering mô tả mạng con cá voi, không đại diện
toàn bộ Ethereum; không so clustering có trọng số giữa cửa sổ mà bỏ qua việc
trọng số được chuẩn hóa riêng theo từng cửa sổ.

Tham chiếu: [NetworkX betweenness](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.betweenness_centrality.html),
[clustering](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.cluster.clustering.html),
[eigenvector](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.eigenvector_centrality.html),
[SciPy eigs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.eigs.html).
