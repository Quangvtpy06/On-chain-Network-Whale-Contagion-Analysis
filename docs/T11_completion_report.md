# T11 — Community detection và network concentration

**Hoàn tất phần kỹ thuật, kiểm định và tái lập trên T08 hiện tại.**
Kết quả RQ4 là mô tả hồi cứu quanh ngày volume cao, chưa xác nhận stress thị trường hoặc hành vi nhà đầu tư.

## Phạm vi bàn giao

| Cửa sổ | Snapshot | Dòng node | Q trung bình |
|---|---:|---:|---:|
| daily | 655 | 712,519 | 0.715513 |
| weekly | 94 | 388,557 | 0.693665 |

Giữ 655 ngày UTC và 94 tuần ISO; hai tuần thiếu ngày có eligible_for_regression=false.
Louvain có hướng, trọng số USDT, resolution=1. Community ID chỉ có ý nghĩa trong từng snapshot.

## Kiểm định

- Validator độc lập đạt 749/749 cửa sổ từ cạnh T08; không nhập hàm tính chỉ số production.
- 8/8 Parquet khớp SHA-256 giữa hai tiến trình mới, PYTHONHASHSEED=0.
- Kiểm tra calendar, khóa, node/edge, volume/degree, phân hoạch, modularity, mọi chỉ số tập trung, bảng top và thống kê RQ4.
- Chỉ validator đạt mới bật ready_for_downstream; --skip-reproducibility luôn giữ false.
- Tái lập không chứng minh quyền sở hữu, ý nghĩa kinh tế hoặc giả thuyết RQ4.

## Bảng sản phẩm và hash hiện tại

| File | Dòng | SHA-256 |
|---|---:|---|
| community_nodes_daily.parquet | 712,519 | `7bb18cb01b4f8cba675fcbddbeccc6a2196f70fdfee8dea1e55d976a92090eea` |
| community_nodes_weekly.parquet | 388,557 | `950bc0d927ba1205d5f8ba694cfeda4fb1b16b422a385a4012462465eced4f58` |
| snapshot_metrics_daily.parquet | 655 | `0b79d6750588025ed4750347a9915a2bfe1f0fcc7d885e1b666b8302ab613ed4` |
| snapshot_metrics_weekly.parquet | 94 | `acd4230742a022c8b9c2a4f5449f400faeecf0182e64d2a8667357a5bc8137a4` |
| t11_validation.parquet | 749 | `181303bf625e17d6de9dc5151eb3e9247b13e48cf869f55c09dd8cdc71b87e77` |
| top_communities_summary.parquet | 3,745 | `f54b59ddd104466ded81689051115029713e8b89e99e2e92940bb045406be579` |
| rq4_daily_regimes.parquet | 655 | `d8a073d2ee152e22732b670dfff5749579bd8602daf498443a12a301a9cd5d07` |
| rq4_comparison.parquet | 5 | `038728e7da253373fb6f0180307e12d8f33ee61809596e5cd293dbe8694f39dc` |

Bảng top có 3,745 dòng, top 5 theo volume trong mỗi cửa sổ ngày/tuần, được sinh trong cả hai lượt.
Metadata: t11_summary.json, t11_review.json, t11_reproducibility.json.

## RQ4 — đối chiếu mô tả

High-volume là volume T08 >= phân vị 90% toàn kỳ; pre là 1–3 ngày trước high-volume và không phải high-volume.
Số ngày: baseline=490, pre=96, high-volume=66, censored=3.
Ba ngày cuối không đủ quan sát tương lai bị loại khỏi so sánh; không mặc định chúng là baseline.

| Chỉ số | Baseline | Pre | High-volume | Thay đổi Pre/Base | p Welch | p Holm (5 chỉ số) |
|---|---:|---:|---:|---:|---:|---:|
| gini_volume | 0.816855 | 0.831010 | 0.869759 | +1.73% | 5.73022e-05 | 0.000286511 |
| hhi_community_volume | 0.132915 | 0.137495 | 0.136254 | +3.45% | 0.321764 | 0.643527 |
| community_concentration_index | 0.094865 | 0.096605 | 0.092972 | +1.83% | 0.501503 | 0.643527 |
| modularity | 0.720254 | 0.710143 | 0.686800 | -1.40% | 0.026792 | 0.080376 |
| cr_top5pct_volume | 0.651065 | 0.670432 | 0.743913 | +2.97% | 0.00291157 | 0.0116463 |

Các p-value là thăm dò: Welch giả định quan sát độc lập, Holm chỉ điều chỉnh kiểm định nhiều chỉ số, không xử lý phụ thuộc thời gian/cụm sự kiện.
Không thể suy từ Gini node sang tập trung cộng đồng, danh tính cá nhân, tái cơ cấu danh mục, dòng vào sàn hoặc khủng hoảng thanh khoản.
HHI cộng đồng và CCI không cung cấp bằng chứng đủ để xác nhận giả thuyết tăng tập trung trước stress thị trường.
Cần sự kiện stress độc lập và thiết kế thống kê phù hợp trước khi đưa ra kết luận thị trường/nhân quả hoặc dự báo.

## Biểu đồ và giới hạn

Bốn PNG được tạo ở data/figures/t11/: modularity_timeseries, concentration_timeseries, rq4_stress_comparison và community_map_2026-10-17 (tiền tố t11_).
Các box dùng thứ tự baseline/pre/high-volume, N động và cùng bảng rq4_comparison; đây là biểu đồ Matplotlib tĩnh.
Mạng chỉ chứa transfer sau netting >=500.000 USDT; concentration mô tả mạng con đang hoạt động, không phải toàn mạng hoặc tài sản cá nhân.
Volume node là vào + ra, tổng bằng hai lần volume cạnh; community_volume lặp trên node, không cộng lại cột này qua các node.
CCI=max(Q,0)×HHI community volume là chỉ số tổng hợp của dự án, không tự xác nhận rủi ro hệ thống.

## Chạy lại

```powershell
python T11_Community_Concentration.py
python scripts/validate_t11_current.py
python -m src.visualize_t11
```

Không lưu mã/bản test giả sau khi kiểm tra; giữ validator dữ liệu thật và bằng chứng Parquet/JSON.
Xem [đặc tả](T11_community_concentration_specification.md) và [kết quả xử lý review](T11_review_report.md).

## Bổ sung kiểm tra RQ4 với stress thị trường (26/10/2026)

T11 ban đầu chỉ đối chiếu trước ngày volume giao dịch lớn. Phân tích RQ4 riêng nay dùng
nhãn stress RV P90 của T13 và HHI/CCI từ T11 ở 1–3 ngày trước onset stress. Có 23
đợt stress và 434 mốc đối chứng yên bình. HHI/CCI trước stress cao hơn trung bình,
nhưng p Holm kiểm định tăng của cả hai chỉ số bằng 0,2603; chưa có bằng chứng
đủ ở mức 5%. Độ nhạy ghép đối chứng cùng thứ trong tuần cho p Holm 0,0580,
cũng chưa đạt 5%. T11 output và hash ở trên không thay đổi. Xem
[đặc tả mới](RQ4_stress_lead_specification.md) và
[báo cáo kết quả](RQ4_stress_lead_completion_report.md).
