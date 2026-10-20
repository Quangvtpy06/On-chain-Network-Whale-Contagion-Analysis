# Chiến lược xử lý Big Data từ HuggingFace — Không cần clone toàn bộ

## 🔍 Tình trạng hiện tại

### Dataset trên HuggingFace (26.3 GB tổng)
```
team-crypto/Market-data-crypto-project
├── data/
│   ├── raw/daily/                    ← 104 file parquet (2026-07-06 → 2026-10-17)
│   │                                  (Xet pointers ~130B mỗi file, thực tế mỗi file hàng chục MB)
│   ├── interim/
│   │   └── usdt_whale_transfers_interim.parquet   ← FILE CHÍNH (Xet pointer 134B → thực ~GB)
│   ├── external/
│   │   └── t07_verified_labels.csv                ← 972 bytes (file nhỏ)
│   └── processed/
│       ├── graphs/
│       │   ├── dynamic_edges_daily.parquet         ← Xet pointer → thực ~GB
│       │   ├── dynamic_edges_weekly.parquet        ← Xet pointer → thực ~GB
│       │   ├── graph_metrics_daily.csv             ← 104 KB
│       │   ├── graph_metrics_weekly.csv            ← 15 KB
│       │   └── t08_summary.json                    ← 1.5 KB
│       ├── t07/                                    ← JSON summaries (nhỏ)
│       └── t09/
│           ├── node_metrics_daily.parquet          ← ~47.5 MB
│           ├── node_metrics_weekly.parquet         ← ~27.9 MB
│           └── t09_summary.json                    ← 1.2 KB
└── market/                           ← Binance trade data (phần lớn 26.3 GB)
    ├── klines/
    └── trades/
```

### Scripts đã có trên máy local

| File | Mô tả | Input cần | Trạng thái |
|------|--------|-----------|------------|
| `T07_Full_Wallet_Labeling.py` | Gán nhãn toàn bộ ví | `interim/usdt_whale_transfers_interim.parquet` + `external/t07_verified_labels.csv` | ❌ Thiếu data |
| `T08_Dynamic_Transaction_Graph.py` | Xây dynamic graph | `interim/usdt_whale_transfers_interim.parquet` | ❌ Thiếu data |
| `T09_Network_Centrality.py` | Tính centrality metrics | `processed/graphs/dynamic_edges_*.parquet` | ❌ Thiếu data |

### Vấn đề cốt lõi

`.gitattributes` khai báo `*.parquet filter=lfs diff=lfs merge=lfs -text` → các file `.parquet` lớn là **Git LFS / Xet pointers**, khi clone bình thường chỉ lấy được con trỏ (~130 bytes), **không phải dữ liệu thực**.

---

## 🚀 Giải pháp: Selective Download từ HuggingFace Hub

### Ý tưởng chính

Thay vì clone 26.3 GB về máy, ta dùng **`huggingface_hub`** để **tải chọn lọc** — chỉ tải đúng file cần thiết, có cache tự động.

### Phân loại file theo chiến lược tải

| Nhóm | Files | Kích thước | Chiến lược |
|------|-------|------------|------------|
| **Nhỏ - Tải ngay** | `t07_verified_labels.csv`, JSON, CSV | < 200 KB | `hf_hub_download()` |
| **Trung bình** | `node_metrics_*.parquet` (T09 output) | ~75 MB | `hf_hub_download()` |
| **Lớn** | `usdt_whale_transfers_interim.parquet`, `dynamic_edges_*.parquet` | Hàng GB | `hf_hub_download()` — tải 1 lần, cache |
| **Rất lớn - Skip** | `market/trades/` (Binance tick data) | ~25 GB | ❌ Không cần cho T07-T09 |

---

## 📋 Cách refactor script hiện tại

### Thay đổi cần thiết trong mỗi script

**TRƯỚC** (đọc local — lỗi vì không có file):
```python
INPUT = ROOT / "data/interim/usdt_whale_transfers_interim.parquet"
LABELS = ROOT / "data/external/t07_verified_labels.csv"
```

**SAU** (tải từ HuggingFace, cache tự động):
```python
from huggingface_hub import hf_hub_download

REPO = "team-crypto/Market-data-crypto-project"
INPUT = hf_hub_download(REPO, "data/interim/usdt_whale_transfers_interim.parquet", repo_type="dataset")
LABELS = hf_hub_download(REPO, "data/external/t07_verified_labels.csv", repo_type="dataset")
```

`hf_hub_download()` tự động cache — lần đầu tải, lần sau đọc từ cache (~/.cache/huggingface/).
