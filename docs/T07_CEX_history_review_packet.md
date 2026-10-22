# T07 CEX — bảng review lịch sử

Trạng thái registry: 306 approved / 0 pending / 0 rejected. Quyết định của thành viên được lưu riêng, không suy từ extraction status.
Nguồn thứ cấp DefiLlama, snapshot cố định và merge công khai trước mẫu. Chưa có phê duyệt của thành viên thì không được dùng như nhãn PIT đã nghiệm thu.
Mở URL blob và PR merge; đối chiếu đúng owners Ethereum và các địa chỉ. Ngày commit không thay được ngày public merge. verified_at là thời điểm review thật hôm nay.
Review theo project bằng scripts/review_t07_cex_history.py; không cần sửa Parquet trực tiếp. Xem docs/T07_CEX_history_handoff.md.

| Project | Chủ thể | Số địa chỉ | Approved / Pending / Rejected | Nguồn cố định | Trạng thái trích xuất |
|---|---|---:|---|---|---|
| binance | Binance | 15 | 15 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/binance/config.js) | literal_ethereum_addresses_extracted |
| crypto-com | Crypto.com | 6 | 6 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/crypto-com/index.js) | literal_ethereum_addresses_extracted |
| bybit | Bybit | 9 | 9 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bybit/index.js) | literal_ethereum_addresses_extracted |
| okex | OKX | 107 | 107 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/okex/index.js) | literal_ethereum_addresses_extracted |
| kucoin | KuCoin | 27 | 27 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/kucoin/index.js) | literal_ethereum_addresses_extracted |
| gateio | Gate.io | 0 | 0 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/gateio/index.js) | not_found_in_snapshot |
| huobi | HTX | 36 | 36 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/huobi/index.js) | literal_ethereum_addresses_extracted |
| bitget | Bitget | 55 | 55 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bitget/index.js) | literal_ethereum_addresses_extracted |
| mexc | MEXC | 0 | 0 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/mexc/index.js) | not_found_in_snapshot |
| deribit | Deribit | 16 | 16 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/deribit/index.js) | literal_ethereum_addresses_extracted |
| bitfinex | Bitfinex | 4 | 4 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bitfinex/index.js) | literal_ethereum_addresses_extracted |
| bitstamp | Bitstamp | 0 | 0 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bitstamp/index.js) | no_literal_ethereum_owners |
| kraken | Kraken | 15 | 15 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/kraken/index.js) | literal_ethereum_addresses_extracted |
| coinbase | Coinbase | 0 | 0 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/coinbase/index.js) | not_found_in_snapshot |
| phemex | Phemex | 2 | 2 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/phemex/index.js) | literal_ethereum_addresses_extracted |
| bitmart | BitMart | 0 | 0 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bitmart/index.js) | not_found_in_snapshot |
| bitkub | Bitkub | 0 | 0 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bitkub/index.js) | not_found_in_snapshot |
| coinex | CoinEx | 9 | 9 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/coinex/index.js) | literal_ethereum_addresses_extracted |
| bingx | BingX | 0 | 0 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bingx/index.js) | not_found_in_snapshot |
| whitebit | WhiteBIT | 0 | 0 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/whitebit/index.js) | not_found_in_snapshot |
| poloniex | Poloniex | 0 | 0 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/poloniex/index.js) | not_found_in_snapshot |
| bitmex | BitMEX | 2 | 2 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bitmex/index.js) | literal_ethereum_addresses_extracted |
| hashkey-exchange | HashKey Exchange | 3 | 3 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/hashkey-exchange/index.js) | literal_ethereum_addresses_extracted |
| osl | OSL | 0 | 0 / 0 / 0 | [Mở nguồn](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/osl/index.js) | not_found_in_snapshot |

## Ưu tiên 20 địa chỉ có volume đầu mút netted cao nhất

Bảng xếp theo volume để đối chiếu. Trạng thái review được ghi riêng. Mẫu số volume là tổng hai đầu mút của node; cùng một transfer có thể nằm ở hai node.
| Địa chỉ | Chủ thể được nguồn gán | USDT đầu mút | Review | Vị trí nguồn lịch sử |
|---|---|---:|---|---|
| `0x28c6c06298d514db089934071355e5743bf21d60` | Binance | 857,739,843,810.76 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/binance/config.js#L11-L11) |
| `0x77134cbc06cb00b66f4c7e623d5fdbf6777635ec` | Bitfinex | 206,694,481,822.44 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bitfinex/index.js#L10-L10) |
| `0x56eddb7aa87536c09ccc2793473599fd21a8b17f` | Binance | 157,563,424,175.53 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/binance/config.js#L237-L237) |
| `0x18709e89bd403f470088abdacebe86cc60dda12e` | HTX | 156,738,477,249.05 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/huobi/index.js#L15-L15) |
| `0x21a31ee1afc51d94c2efccaa2092ad1028285549` | Binance | 150,026,569,815.96 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/binance/config.js#L10-L10) |
| `0xdfd5293d8e347dfe59e90efd55b2956a1343963d` | Binance | 144,486,878,819.15 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/binance/config.js#L13-L13) |
| `0x9696f59e4d72e237be84ffd425dcad154bf96976` | Binance | 142,046,407,474.46 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/binance/config.js#L131-L131) |
| `0xa03400e098f4421b34a3a44a1b4e571419517687` | HTX | 106,503,104,169.23 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/huobi/index.js#L44-L44) |
| `0xf977814e90da44bfa03b6295a0616a897441acec` | Binance | 84,333,668,781.77 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/binance/config.js#L14-L14) |
| `0x89e51fa8ca5d66cd220baed62ed01e8951aa7c40` | Kraken | 77,400,584,864.24 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/kraken/index.js#L18-L18) |
| `0x5a52e96bacdabb82fd05763e25335261b270efcb` | Binance | 65,466,727,610.44 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/binance/config.js#L143-L143) |
| `0xf89d7b9c864f589bbf53a82105107622b35eaa40` | Bybit | 54,670,088,084.79 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bybit/index.js#L11-L11) |
| `0xffe15ff598e719d29dfe5e1d60be1a5521a779ae` | HashKey Exchange | 36,259,495,215.07 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/hashkey-exchange/index.js#L17-L17) |
| `0x1ab4973a48dc892cd9971ece8e01dcc7688f8f23` | Bitget | 34,492,999,688.32 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/bitget/index.js#L52-L52) |
| `0x5041ed759dd4afc3a72b8192c143f72f4724081a` | OKX | 27,363,610,849.32 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/okex/index.js#L10-L10) |
| `0xcffad3200574698b78f32232aa9d63eabd290703` | Crypto.com | 27,071,607,768.75 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/crypto-com/index.js#L12-L12) |
| `0x46340b20830761efd32832a74d7169b29feb9758` | Crypto.com | 21,623,048,443.74 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/crypto-com/index.js#L14-L14) |
| `0x83c41363cbee0081dab75cb841fa24f3db46627e` | KuCoin | 21,584,682,447.48 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/kucoin/index.js#L18-L18) |
| `0xd3a22590f8243f8e83ac230d1842c9af0404c4a1` | Binance | 18,693,180,706.40 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/binance/config.js#L154-L154) |
| `0x835678a611b28684005a5e2233695fb6cbbb0007` | Binance | 17,313,278,715.88 | approved | [Mở đúng dòng](https://github.com/DefiLlama/DefiLlama-Adapters/blob/97218fb144afd6bdd65e1b58a2c5c14b1a8f7a8e/projects/binance/config.js#L270-L270) |
