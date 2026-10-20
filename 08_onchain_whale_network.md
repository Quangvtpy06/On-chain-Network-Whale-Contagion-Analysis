# RESEARCH BLUEPRINT 08

## On-chain Network & Whale Contagion Analysis

*Phân tích mạng lưới giao dịch blockchain, whale flows và khả năng lan truyền rủi ro bằng Graph Analytics và GNN*

> **Môn học gợi ý:** Công nghệ ứng dụng trong Tài chính / Financial Technology  
> **Định dạng:** Research + Code + Financial Product  
> **Mức độ:** Undergraduate advanced / MSc-entry level  
> **Thời lượng phù hợp:** 8–12 tuần  
> **Ngôn ngữ triển khai:** Python ưu tiên; R có thể dùng cho econometrics  
> **Lưu ý:** Đây là thiết kế học thuật và mô phỏng nghiên cứu, không phải khuyến nghị đầu tư.

---

## 1. Tên chủ đề

**On-chain Network and Whale Contagion Analysis: Graph-Based Evidence from Ethereum/Bitcoin Transaction Networks**

**Hướng nghiên cứu:** Blockchain Analytics, Network Science, Graph Machine Learning, Market Microstructure.

---

## 2. Mục tiêu nghiên cứu, câu hỏi nghiên cứu và mô hình dự kiến

### 2.1. Mục tiêu nghiên cứu

Blockchain cung cấp một network transaction ledger công khai. Dự án chuyển transaction data thành graph để nghiên cứu cấu trúc dòng vốn, các địa chỉ lớn (whales), communities và khả năng các network signals liên hệ với market stress.

Mục tiêu:

1. Xây dynamic transaction graph.
2. Tính centrality/community/flow metrics.
3. Xác định whale activity theo quy tắc minh bạch.
4. Kiểm tra whale/network signals có liên hệ với volatility/liquidity.
5. Xây interactive graph explorer.
6. Nhóm mạnh có thể triển khai GraphSAGE/GAT.

### 2.2. Câu hỏi nghiên cứu

- **RQ1:** Cấu trúc transaction network thay đổi như thế nào giữa normal và stress periods?
- **RQ2:** Central wallets có vai trò disproportionate trong flows hay không?
- **RQ3:** Large transfers/exchange inflows có dự báo volatility ngắn hạn không?
- **RQ4:** Community concentration có tăng trước stress events không?
- **RQ5:** GNN có phân loại address/entity behavior tốt hơn tabular ML không?

### 2.3. Graph representation

\[
G_t=(V_t,E_t)
\]

- node \(v\): address/entity;
- edge \(e_{ij}\): transaction từ \(i\) đến \(j\);
- edge weight: value hoặc number of transfers.

Dynamic graph có thể xây theo daily/weekly windows.

### 2.4. Network metrics

- in-degree/out-degree;
- weighted degree;
- PageRank;
- betweenness;
- eigenvector centrality;
- clustering coefficient;
- community modularity;
- network concentration.

Whale score có thể kết hợp:

\[
WhaleScore_i
=
z(Value_i)
+
z(WeightedDegree_i)
+
z(PageRank_i)
\]

nhưng không nên coi mọi high-centrality address là nhà đầu tư cá nhân; có thể là exchange, bridge hoặc contract.

### 2.5. Whale-flow signals

Ví dụ exchange-labelled wallets:

\[
NetFlow_t=Inflow_t-Outflow_t
\]

Predictive regression:

\[
Vol_{t+h}
=
\alpha+\beta WhaleFlow_t+\gamma'X_t+\varepsilon_{t+h}
\]

hoặc:

\[
r_{t+h}
=
\alpha+\beta WhaleFlow_t+\gamma'X_t+\varepsilon_{t+h}
\]

Ưu tiên volatility/liquidity hơn return prediction để tránh overclaim.

### 2.6. Event study

Events:
- large transfer above percentile;
- whale-to-exchange inflow;
- network concentration spike.

Event-time response:

\[
Y_{t+\tau},\ \tau=-k,\ldots,+k
\]

Y:
- volatility;
- volume;
- spread;
- return.

### 2.7. Graph ML extension

Task 1: address classification.

Inputs:
- node features;
- graph neighborhood.

Models:
- MLP baseline;
- Node2Vec;
- GCN;
- GraphSAGE;
- GAT.

Metrics:
- macro F1;
- class-wise precision/recall.

Task 2 nâng cao: temporal graph anomaly detection.

### 2.8. Causal caution

Large transfers có thể **phản ứng** với price changes thay vì gây price changes.

Vì vậy dùng từ:
- predictive association;
- lead-lag relationship;
- event-linked response.

Không gọi “causal effect” nếu không có identification design.

---

## 3. Data dự kiến

### 3.1. Blockchain

Khuyến nghị Ethereum vì:
- account-based data;
- rich ERC-20/DeFi ecosystem;
- Google Blockchain Analytics/public data thuận lợi.

Bitcoin có thể là alternative nếu nhóm quen UTXO.

### 3.2. Sources

- Google Blockchain Analytics / BigQuery;
- Ethereum public datasets;
- Etherscan labels/public labels nếu điều khoản cho phép;
- protocol-labelled addresses;
- CoinGecko/Binance market data.

### 3.3. Raw variables

```text
block_time
from_address
to_address
value
token_address
transaction_hash
gas
status
```

ERC-20 transfer logs nếu nghiên cứu token flows.

### 3.4. Sampling

Full Ethereum graph rất lớn. Sinh viên nên:

- chọn một token/asset;
- chọn top addresses;
- hoặc ego-network quanh exchanges/whales;
- hoặc daily sampled transfer graph.

### 3.5. Labeling

Nếu làm classification:
- exchange;
- DeFi;
- bridge;
- contract;
- personal/unknown;
- scam/phishing chỉ khi có label source đáng tin.

Không tự suy đoán identity.

---

## 4. Output dự kiến

### 4.1. Academic output

Bảng:

1. network statistics;
2. centrality distributions;
3. whale-flow predictive regressions;
4. event-study results;
5. ML/GNN comparisons.

Hình:

- graph visualization;
- community map;
- top centrality nodes by anonymous labels;
- whale inflow vs volatility;
- event-time plots.

### 4.2. Product output

**Interactive On-chain Network Explorer**

Features:

- date/window selector;
- asset selector;
- network graph;
- top central nodes;
- exchange inflow/outflow;
- whale activity score;
- volatility context.

Có thể dùng:
- NetworkX;
- PyVis/Plotly;
- Streamlit;
- PyTorch Geometric cho GNN.

### 4.3. Privacy/ethics

Không trình bày anonymous address như một cá nhân thật khi không có verified public label.

---

## 5. Tài liệu tham khảo gợi ý

1. Ron, D., & Shamir, A. (2013). Quantitative analysis of the full Bitcoin transaction graph. *Financial Cryptography and Data Security*.
2. Kondor, D., Pósfai, M., Csabai, I., & Vattay, G. (2014). Do the rich get richer? An empirical analysis of the Bitcoin transaction network. *PLoS ONE, 9*(2), e86197.
3. Li, Z., & He, E. (2023). Graph neural network-based Bitcoin transaction tracking model. *IEEE Access, 11*, 62109–62120.
4. Ko, H., Lee, S., & Seo, J. (2024). Ethereum smart contract account classification and transaction prediction using the Graph Attention Network. *Journal of Web Engineering*.
5. Shen, D., & Shi, G. (2025). The role of whale investors in the Bitcoin market. *Research in International Business and Finance*.
6. Kasula, V. K., Yadulla, A. R., Yenugula, M., et al. (2025). Blockchain address classification using graph neural networks for enhanced security and analytics. *Discover Artificial Intelligence, 5*, 285.
7. Li, C., Zhang, Y., Liu, R., et al. (2026). Ethereum phishing fraud detection via dynamic graph neural network with anonymous walks. *Pattern Recognition*.


---

## 6. Checklist bàn giao tối thiểu cho nhóm

- [ ] Research question được phát biểu rõ và nhất quán với model.
- [ ] Data dictionary và source log.
- [ ] Script tải/chuẩn hóa dữ liệu có thể chạy lại.
- [ ] Không có look-ahead bias/data leakage.
- [ ] Có econometric/statistical benchmark.
- [ ] Có ít nhất một model nâng cao.
- [ ] Có untouched out-of-sample test.
- [ ] Có robustness hoặc sensitivity analysis.
- [ ] Có README hướng dẫn chạy code.
- [ ] Có dashboard/app hoặc research visualization có thể demo.
- [ ] Có báo cáo học thuật giải thích economic meaning, không chỉ model metrics.

## 7. Cấu trúc repository đề xuất

```text
project/
├── README.md
├── requirements.txt
├── config/
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── src/
│   ├── data/
│   ├── features/
│   ├── models/
│   ├── evaluation/
│   └── utils/
├── notebooks/
├── dashboard/
├── tests/
├── outputs/
│   ├── tables/
│   └── figures/
└── paper/
```

> **Nguyên tắc chung:** một model đơn giản nhưng point-in-time đúng, có benchmark và kiểm định out-of-sample tốt hơn một model phức tạp nhưng leakage hoặc không thể tái lập.
