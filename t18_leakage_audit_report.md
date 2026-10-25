# T18 Look-ahead Bias Audit & Train/Test Split Report

**Task:** Audit T15 and T16 for look-ahead bias; propose time-based train/test split;
evaluate out-of-sample (OOS) performance.

> **Scope:** Covers T15 (`T15_Volatility_Regression.py`) and T16 (`T16_Event_Study.py`) only.
> T14 (`T14_Flow_Volatility.py`, `src/flow_volatility.py`) is read solely to understand
> inputs — full T14 audit is out of scope for T18.

---

## Bước 1 — Look-ahead Bias Audit

### Q1 — T14: Cột `*_pit_z` có thực sự PIT không?

**KẾT LUẬN: CÓ — các cột PIT chỉ dùng dữ liệu đến thời điểm t.**

Trích dẫn từ `src/flow_volatility.py`:

```python
# L6: is computable at `available_at` = D+1 00:00 UTC; nothing later is read.
# L12: pit: CEX set C_D = approved public-history registry, public_available_at < D.
# L65: """C_D for every day: approved public-history labels with public_available_at < D 00:00 UTC."""
# L252-L257: rolling mean/std use series.shift(1).rolling(...) — không bao gồm ngày D.
```

`whaleflow_pit_z` và `pit_cex_netflow_z` đều dùng `C_D` (CEX set known BEFORE day D),
và z-score được tính qua rolling window với `.shift(1)` — tức là không nhìn tương lai.

---

### Q2 — T15: Target `Vol_{t+h}` có bị trộn với `X_t` không?

**KẾT LUẬN: KHÔNG — target và predictors không trộn nhau.**

Trích dẫn từ `T15_Volatility_Regression.py`:

```python
# L212: target_col = f"target_log_rv_h{h}"   ← cột này được tính bởi T14: shift(-h)
# L217: y = df[target_col]                   ← chỉ lấy target
# L128: data = pd.concat([y, X], axis=1).dropna()  ← y và X concat, không overlap
```

`target_log_rv_h{h}` là cột được T14 tạo sẵn bằng `log_rv.shift(-h)` —
tức là giá trị của ngày D+h. Predictors `X_t` là giá trị của ngày D.
Việc `concat + dropna` tại L128 chỉ loại bỏ hàng NaN, không làm lệch thời điểm.

**Q2b — Chọn HORIZONS=[1,3,7] và maxlags có dùng toàn mẫu không?**

**KẾT LUẬN: CÓ VẤN ĐỀ TIỀM NĂNG (mức độ nhẹ).**

```python
# L67: HORIZONS = [1, 3, 7]   ← hardcoded constant, không fit từ data
# L121-123: maxlags = max(h, int(np.ceil(4.0*(n/100)**(2/9))))
#           — n ở đây là số hàng SAU dropna của toàn bộ mẫu, không chỉ train
```

Giá trị `HORIZONS` và công thức maxlags là **lý thuyết/cố định** (không được chọn
bằng cách xem kết quả test), nên không gây data leakage thực sự.
Tuy nhiên, khi chạy OOS đúng chuẩn, `maxlags` nên tính từ `n_train`, không `n_total`.

---

### Q3 — T16: Ngưỡng percentile tính bằng ROLLING hay TĨNH? ← CÂU HỎI QUAN TRỌNG NHẤT

**KẾT LUẬN: ROLLING (point-in-time) — KHÔNG có look-ahead bias.**

Trích dẫn từ `T16_Event_Study.py`:

```python
# L139-146: hàm _rolling_pit_percentile
def _rolling_pit_percentile(series: pd.Series, window: int, q: float) -> pd.Series:
    """
    At each time t, threshold = quantile(series[t-window : t-1], q).
    """
    # shift(1) ensures we never include the current observation in the threshold
    return series.shift(1).rolling(window=window, min_periods=max(30, window // 3)).quantile(q)

# L160: threshold = _rolling_pit_percentile(df[col], LARGE_TRANSFER_LOOKBACK, LARGE_TRANSFER_PERCENTILE)
# L161: events = (df[col] > threshold) & df[col].notna() & threshold.notna()

# L190: threshold = _rolling_pit_percentile(df[col], CONCENTRATION_LOOKBACK, CONCENTRATION_PERCENTILE)
# L191: events = (df[col] > threshold) & df[col].notna() & threshold.notna()
```

`.shift(1)` trước `.rolling()` đảm bảo tại ngày t, ngưỡng chỉ tính từ dữ liệu
`[t-window, t-1]` — không bao giờ nhìn ngày t hoặc tương lai.

`whale_inflow` dùng ngưỡng cố định (+2.0 std) trên cột đã được standardise PIT —
không cần rolling, không có leakage.

---

### Q4 — Có `bfill`, `ffill` lấy giá trị tương lai lấp quá khứ không?

**KẾT LUẬN: KHÔNG — không tìm thấy bất kỳ bfill/ffill/fillna nào trong T15 và T16.**

Kết quả grep cụ thể:

- `T15_Volatility_Regression.py`: không có `bfill`, `ffill`, `fillna`
- `T16_Event_Study.py`: không có `bfill`, `ffill`, `fillna`

Chỗ duy nhất xử lý missing là `dropna()` tại L128 của T15 — hành vi an toàn (loại bỏ
hàng NaN, không lấp giá trị).

---

### Tổng kết Bước 1

| Mục | Câu hỏi                                         | Kết quả | Ghi chú                                                                  |
| --- | ----------------------------------------------- | ------- | ------------------------------------------------------------------------ |
| Q1  | Cột `*_pit_z` chỉ dùng dữ liệu đến t?           | ✅ CÓ   | `.shift(1).rolling()` trong T14; `public_available_at < D`               |
| Q2a | Target `Vol_{t+h}` không trộn với `X_t`?        | ✅ CÓ   | T14 tạo sẵn `target_log_rv_h{h}` = shift(-h); concat an toàn             |
| Q2b | HORIZONS, maxlags không fit từ test data?       | ⚠️ NHẸ  | Hardcoded lý thuyết — không leak, nhưng maxlags nên dùng n_train khi OOS |
| Q3  | T16 ngưỡng percentile dùng ROLLING không?       | ✅ CÓ   | `series.shift(1).rolling(...).quantile(q)` — không nhìn tương lai        |
| Q4  | Không có `bfill`/`ffill` lấy giá trị tương lai? | ✅ CÓ   | Không tìm thấy trong T15 hoặc T16                                        |

> **Không phát hiện lỗi look-ahead bias thực sự trong T15 hoặc T16.**
> Vấn đề duy nhất (Q2b) là nhẹ và mang tính kỹ thuật, không ảnh hưởng đến tính hợp lệ
> của kết quả T15 đã công bố.

---

## Bước 2 — Đề xuất Train/Test Split

> **[ĐỀ XUẤT CỦA T18 — chưa chốt với nhóm]**

**Dữ liệu:** `t14_features_daily.parquet` — 655 ngày: 2025-01-01 → 2026-10-17

**Phương pháp:** Chia theo thời gian (chronological), **không random split**,
vì đây là time-series có cấu trúc autoregressive (HAR).

**Tỷ lệ đề xuất: 80% train / 20% test**

|           | Ngày bắt đầu | Ngày kết thúc | Số ngày |
| --------- | ------------ | ------------- | ------- |
| **Train** | 2025-01-01   | 2026-06-08    | 524     |
| **Test**  | 2026-06-09   | 2026-10-17    | 131     |

**Cutoff:** `2026-06-08`

**Lý do chọn 80/20:**

- 524 ngày train đủ để ước lượng ổn định (T15 cần ~594 rows sau dropna — xem Q2b)
- 131 ngày test (~4.3 tháng) đủ để kiểm tra OOS một cách có ý nghĩa
- Không dùng cross-validation vì leakage giữa các fold trên time-series

Xem `config/t18_train_test_split.yaml` để biết đầy đủ quy tắc.

---

## Bước 3 — T15 Out-of-Sample Evaluation

**Setup:** Train trên 2025-01-01 → 2026-06-08; predict trên 2026-06-09 → 2026-10-17.
Dùng hệ số từ train để dự báo trên test; tính R² OOS theo công thức
`R²_OOS = 1 - SS_res / SS_tot`.

| h   | R² In-sample (full) | n_full | R² OOS (test) | n_test | ΔR²        |
| --- | ------------------- | ------ | ------------- | ------ | ---------- |
| 1   | 0.4493              | 594    | **0.2525**    | 130    | **−0.197** |
| 3   | 0.2341              | 592    | **−0.065**    | 128    | **−0.299** |
| 7   | 0.2933              | 588    | **0.1557**    | 124    | **−0.138** |

### Nhận xét

- **h=1:** R²_OOS = 0.253 — mô hình vẫn có khả năng dự báo dương trên test, nhưng
  giảm đáng kể so với in-sample (−0.197). Đây là mức drop bình thường cho mô hình
  volatility dự báo 1 bước.

- **h=3:** R²_OOS = **−0.065** — mô hình tệ hơn dự báo bằng mean đơn giản trên tập test.
  Đây là dấu hiệu **overfitting rõ ràng** ở horizon 3 ngày. Hệ số trong mẫu có thể
  phản ánh đặc thù giai đoạn 2025-2026/06 hơn là quan hệ cấu trúc thật sự.

- **h=7:** R²_OOS = 0.156 — mô hình còn dự báo dương nhưng kém hơn in-sample (−0.138).

> [!WARNING]
> **R²_OOS âm tại h=3** là cảnh báo nghiêm trọng: mô hình không có khả năng
> dự báo vượt baseline (mean) trên dữ liệu ngoài mẫu ở horizon 3 ngày.
> Kết quả T15 gốc (in-sample) cần được đọc với cẩn trọng và không nên dùng trực
> tiếp để đưa ra kết luận về khả năng dự báo thực tế.

> [!NOTE]
> Vấn đề kỹ thuật Q2b: n_test chỉ có 130/128/124 rows sau dropna — HAC maxlags
> tính từ n_train sẽ nhỏ hơn khi chạy OOS đúng chuẩn. Kết quả OOS trên đây dùng
> hệ số của mô hình train để predict trực tiếp, không fit lại trên test.

---

## Bước 4 — T16 Out-of-Sample Evaluation

**Phân bố events theo cutoff 2026-06-08:**

| Event type | Tổng | Train (≤ 2026-06-08) | Test (> 2026-06-08) |
|---|---|---|---|
| `large_transfer` | 42 | 33 | **9** |
| `whale_inflow` | 16 | 15 | **1** |
| `concentration` | 74 | 57 | **17** |

### Nhận xét

- **`large_transfer`:** 9 events trong test — đủ để quan sát pattern định tính,
  nhưng quá nhỏ để bootstrap CI có ý nghĩa thống kê. Không nên diễn giải mạnh.

- **`whale_inflow`:** **Chỉ 1 event trong test** — **hoàn toàn không thể đánh giá
  OOS** cho loại event này. Kết quả T16 gốc cho whale_inflow (n=16) đã nhỏ,
  nay phần test chỉ còn 1 ngày → không có giá trị kiểm định.

- **`concentration`:** 17 events trong test — đây là loại có đủ event nhất để
  so sánh OOS. Pattern T16 gốc (vol thấp tại tau=0, rebound tại tau=+1) cần được
  kiểm tra lại trên 17 events này nếu muốn xác nhận tính ổn định.

> [!IMPORTANT]
> **Kết luận Bước 4:** T16 event study không phù hợp với framework train/test split
> thông thường vì số lượng event quá nhỏ sau khi chia. Cách kiểm tra tính bền vững
> phù hợp hơn cho T16 là: (a) thay đổi ngưỡng threshold (T17 robustness), và
> (b) kiểm tra liệu các events trong test có pattern nhất quán với train hay không
> — điều này cần ít nhất 10+ events mỗi loại, chỉ đáp ứng với `concentration`.

---

## Bước 5 — Phát hiện tiềm năng liên quan T14 (KHÔNG sửa)

Trong quá trình đọc `src/flow_volatility.py` phục vụ Q1, phát hiện 1 điểm cần
người phụ trách T14 xác nhận:

- **L353-354:** `corwin_schultz_spread` dùng `hl.shift(1)` và `high.shift(1)` —
  đây là dữ liệu của ngày D-1 (backward-looking), đúng PIT. Tuy nhiên, cột
  `parkinson_var` tại L374 (`np.log(d.high/d.low)**2 / (4*np.log(2))`) chỉ dùng
  high/low của ngày D — không có issue nhưng nên xác nhận rõ đây là intraday var
  của ngày D chứ không phải D+1.

> **Không tự sửa T14. Liệt kê để người phụ trách T14 xác nhận.**

---

## Tổng kết

| Task | Phát hiện                         | Mức độ               | Hành động đề xuất                                                  |
| ---- | --------------------------------- | -------------------- | ------------------------------------------------------------------ |
| T15  | Không có look-ahead bias          | ✅                   | Không cần sửa                                                      |
| T15  | R²_OOS âm tại h=3                 | ⚠️ Nghiêm trọng      | Ghi caveat rõ trong T15 report; không diễn giải h=3 là dự báo được |
| T15  | maxlags dùng n_total thay n_train | ⚠️ Nhẹ               | Fix khi chạy OOS chính thức ở T17                                  |
| T16  | Ngưỡng rolling PIT — đúng         | ✅                   | Không cần sửa                                                      |
| T16  | whale_inflow: 1 event trong test  | ❌ OOS không khả thi | Ghi caveat; không báo cáo OOS cho whale_inflow                     |
| T14  | `parkinson_var` cần xác nhận      | ℹ️ Tham khảo         | Chuyển sang người phụ trách T14                                    |

---

## Output Files

- `config/t18_train_test_split.yaml` — quy tắc split (cutoff, train/test dates, rules)
- `t18_leakage_audit_report.md` — báo cáo này

_Generated by T18 Leakage Audit. Not uploaded to Hugging Face. No git add/commit/push performed._

