"""Public-source desk review, 2026-10-21. Observed labels are not ownership proof.

Unresolved means the lookup did not establish an Ethereum entity. It never means
individual. Search-index observations are identified separately from direct pages.
No historical point-in-time attribution is asserted by current explorer labels.
"""
REVIEW_DATE='2026-10-21'
# address, observed label, category, evidence URL, retrieval mode, note
ROWS=[
('0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4','Binance deposit','exchange_tag','https://etherscan.io/address/0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4?age=24H','search_index','Explorer page title attributes a Binance deposit; direct page returned 403.'),
('0x18e296053cbdf986196903e889b7dca7a73882f6','Bybit','exchange_primary_document','https://www.bybit.com/common-static/cht-static/por/Bybit_PoR_Audit_2025_Jun_19.pdf#page=14','primary_pdf','Address listed among Ethereum reserves on printed page 13; audit 2025-06-19, report 2025-06-27.'),
('0xaa8ba7d4611437141192e7ceced531bc0a133efb','Kraken 5','exchange_tag','https://ethereum.routescan.io/address/0xaA8ba7D4611437141192e7ceCed531Bc0A133efb/nft-transfers','search_index','Explorer explicitly labels Kraken 5 / hot wallet.'),
('0x14681e4e26f1b5b5774ae3b7f694ff08bbbeb65c','','unresolved','https://usdt.tokenview.io/en/address/0x14681e4e26f1b5b5774ae3b7f694ff08bbbeb65c','search_index','Address/transfer records found; no defensible economic identity established.'),
('0xed0c6079229e2d407672a117c22b62064f4a4312','','unresolved','https://etherscan.io/address/0xEd0C6079229E2d407672a117c22b62064f4a4312','search_index','DeFi token/debt positions are visible, but holdings do not identify a person or institution.'),
('0x549d835356d92983abb76e4cae639f7857963425','','unresolved','https://etherscan.io/address/0x549d835356d92983abb76e4cae639f7857963425','search_index','Many token transfers/counterparties; no identity inferred from exchange interactions.'),
('0xc333e80ef2dec2805f239e3f1e810612d294f771','','unresolved','https://www.blockchain.com/eth/address/0xc333e80ef2dec2805f239e3f1e810612d294f771','search_index','Ethereum address record found; Etherscan direct lookup blocked; no identity conclusion.'),
('0xb99a2c4c1c4f1fc27150681b740396f6ce1cbcf5','Abraxas Capital Management / Heka Funds','fund_tag','https://blockscan.com/Address/0xb99a2c4c1c4f1fc27150681b740396f6ce1cbcf5','direct_page','Blockscan entity label links to the asset manager; this is institutional labeling, not an individual.'),
('0x6aea888bcf4fd52213e9d03e7c69a45d98b35065','','unresolved','https://etherscan.io/address/0x6aea888bcf4fd52213e9d03e7c69a45d98b35065','search_index','Exchange transfers alone do not establish ownership or intermediary status.'),
('0xef686ec84eea2eae6f59cbc704d05b939f8fb385','HTX-associated explorer icon','exchange_hint','https://etherscan.io/address/0xef686ec84eea2eae6f59cbc704d05b939f8fb385','search_index','HTX icon on address in transaction rows; weaker hint than an explicit reserve record.'),
('0xf8191d98ae98d2f7abdfb63a9b0b812b93c873aa','','unresolved','https://eth.tokenview.io/cn/address/0xf8191d98ae98d2f7abdfb63a9b0b812b93c873aa','search_index','Active address found; no defensible Ethereum economic identity established.'),
('0x0b2fdf416cf2951499de9a1adac65c8e9907c8c2','Binance deposit','exchange_tag','https://etherscan.io/address/0x0b2fdf416cf2951499de9a1adac65c8e9907c8c2?age=30D','search_index','Explorer explicitly identifies Binance deposit address.'),
('0x17dc4d78e8abca9408c43541beb3c8215655403a','','unresolved','https://etherscan.io/address/0x17dc4d78e8abca9408c43541beb3c8215655403a','search_index','Address page found without defensible entity label in retrieved content.'),
('0xad6eaa735d9df3d7696fd03984379dae02ed8862','Cumberland','fund_tag','https://blockscan.com/Address/0xad6eaa735d9df3d7696fd03984379dae02ed8862','search_index','Blockscan labels Cumberland / Fund; Etherscan COMP holder page corroborates same label.'),
('0x05d9617595e69ff577076355abc5e7c51ed0bdf3','OKX 191','exchange_tag','https://etherscan.io/address/0x05d9617595e69ff577076355abc5e7c51ed0bdf3','search_index','Explorer page title labels OKX 191.'),
('0xa3c9204c856ba6c5c56e32bfc44b4c8203fea930','','unresolved','https://blockscan.com/Address/0xa3c9204c856ba6c5c56e32bfc44b4c8203fea930','lookup_inconclusive','Exact-address search did not establish identity; direct explorer lookup inaccessible.'),
('0xa29e963992597b21bcdcaa969d571984869c4ff5','B2C2 (document attribution)','institution_document_hint','https://ecf.flmd.uscourts.gov/cgi-bin/show_public_doc?2024-00809-56-6-cv=','search_index','Public court exhibit groups address under B2C2; not an adjudication of ownership or wrongdoing.'),
('0x11dbf181dd5c075c2abd92cb9579c4809406b5be','','unresolved','https://etherscan.io/address/0x11dbf181dd5c075c2abd92cb9579c4809406b5be','search_index','Transfers and fee-recipient record do not by themselves establish economic owner or bot status.'),
('0x8f0ee0393eae7fc1638bd7860a3fec6a663786ae','','unresolved','https://blockscan.com/Address/0x8f0ee0393eae7fc1638bd7860a3fec6a663786ae','lookup_inconclusive','No defensible attribution from exact-address lookup; direct lookup inaccessible.'),
('0x3a3c006053a9b40286b9951a11be4c5808c11dc8','Ceffu custody hot wallet 1','custody_tag','https://routescan.io/address/0x3a3C006053a9B40286B9951A11bE4C5808c11dc8/multichain-portfolio','search_index','Explorer explicitly labels Ceffu custody hot wallet.'),
('0xcd531ae9efcce479654c4926dec5f6209531ca7b','Coinbase Prime 1 (Monad only)','cross_chain_hint','https://monadscan.com/address/0xcd531ae9efcce479654c4926dec5f6209531ca7b','search_index','Label observed on Monad; do not automatically transfer that attribution to Ethereum.'),
('0x65c340eb0688d8f8b64e9c6d580f312a97b615d8','','unresolved','https://blockscan.com/Address/0x65c340eb0688d8f8b64e9c6d580f312a97b615d8','lookup_inconclusive','No defensible attribution from exact-address lookup; direct lookup inaccessible.'),
]
