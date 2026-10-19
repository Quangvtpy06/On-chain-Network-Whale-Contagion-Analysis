"""T07: enrich Ethereum address labels with public evidence, no Dune/API key.
Run at root of On-chain-Whale-Git: python -u T07_Public_Label_Enrichment.py
Requires: pandas, pyarrow. Reads existing T07 wallets only; does not re-read interim.
"""
from __future__ import annotations
import io
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / 'data/processed/t07/t07_all_wallet_labels.parquet'
OUT = ROOT / 'data/processed/t07'
URL = 'https://raw.githubusercontent.com/prettydeath/wallet-attribution/main/data/ethereum.csv'
DATASET = 'https://github.com/prettydeath/wallet-attribution'
TYPES = ['CEX', 'DEX', 'DeFi', 'Bridge', 'Custodian', 'Contract', 'Protocol', 'Issuer', 'Other', 'Unknown']
ADDR = re.compile(r'^0x[a-f0-9]{40}$')

def norm(x):
    return str(x).strip().lower()

def classify(row):
    category = norm(row.get('category', ''))
    descriptor = ' '.join([norm(row.get('label', '')), norm(row.get('entity', ''))])
    # Narrow functional categories are only inferred from specific source attributes.
    if category == 'exchange': return 'CEX'
    if category == 'bridge': return 'Bridge'
    if category == 'defi':
        if any(k in descriptor for k in ('uniswap', 'sushiswap', '1inch', 'curve', 'balancer', 'pancakeswap', '0x exchange', 'paraswap', 'cow swap', 'dex router', 'dex aggregator')):
            return 'DEX'
        return 'DeFi'
    if category == 'service':
        if any(k in descriptor for k in ('custody', 'custodian', 'fireblocks', 'bitgo', 'anchorage', 'copper.co')):
            return 'Custodian'
        return 'Other'
    if category in ('sanctioned', 'terrorism', 'ransomware', 'hack', 'scam', 'darknet', 'extremism', 'frozen', 'mixer', 'gambling', 'mining', 'mev'):
        return 'Other'
    # `entity` doesn't prove type; keep Unknown to avoid spurious attribution.
    return 'Unknown'

def main():
    if not INPUT.is_file():
        raise SystemExit(f'Missing input: {INPUT}')
    print('Reading T07 address table (not 2.1m transfer events)...', flush=True)
    df = pd.read_parquet(INPUT)
    if 'address' not in df or 'entity_type' not in df:
        raise SystemExit('Input needs address and entity_type')
    df['address'] = df['address'].astype(str).str.strip().str.lower()
    if df['address'].duplicated().any():
        raise SystemExit('Duplicate address in existing T07 table')
    print('Addresses:', f'{len(df):,}', flush=True)
    print('Fetching Ethereum public labels:', DATASET, flush=True)
    try:
        req = urllib.request.Request(URL, headers={'User-Agent': 'T07-academic-research/1.0'})
        with urllib.request.urlopen(req, timeout=70) as resp:
            content = resp.read(100 * 1024 * 1024 + 1)
        if len(content) > 100 * 1024 * 1024:
            raise ValueError('Dataset exceeds safety limit (100 MiB)')
    except Exception as exc:
        raise SystemExit(f'Public dataset download failed: {exc}\nTry opening {URL} in a browser.') from exc
    labels = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    labels.columns = labels.columns.str.strip().str.lower()
    needed = {'address', 'network', 'entity', 'label', 'category', 'source', 'source_url', 'confidence'}
    if not needed.issubset(labels.columns):
        raise SystemExit(f'Unexpected public CSV schema. Columns: {list(labels.columns)}')
    labels = labels[labels['network'].str.lower().eq('ethereum')].copy()
    labels['address'] = labels['address'].map(norm)
    labels = labels[labels['address'].map(lambda x: bool(ADDR.fullmatch(x)))].copy()
    # Reject duplicate rows with conflicting source categorization.
    labels['mapped_type'] = labels.apply(classify, axis=1)
    conflicts = labels.groupby('address')['mapped_type'].nunique()
    ambiguous = set(conflicts[conflicts > 1].index)
    labels = labels[~labels['address'].isin(ambiguous)].drop_duplicates('address', keep='first')
    print('Public Ethereum addresses:', f'{len(labels):,}', 'conflicting:', len(ambiguous), flush=True)

    use = ['address', 'entity', 'label', 'category', 'source', 'source_url', 'confidence', 'mapped_type']
    new = df.merge(labels[use], on='address', how='left', validate='one_to_one', suffixes=('', '_public'))
    # Avoid silently overriding existing manually contributed labels.
    existing = new['entity_type'].fillna('Unknown').astype(str).str.strip().ne('Unknown')
    recognized = new['mapped_type'].notna() & new['mapped_type'].ne('Unknown')
    fill = ~existing & recognized
    new['entity_type'] = new['entity_type'].fillna('Unknown')
    new.loc[fill, 'entity_type'] = new.loc[fill, 'mapped_type']
    if 'entity_name' not in new:
        new['entity_name'] = 'Unknown'
    new.loc[fill, 'entity_name'] = new.loc[fill, 'label'].where(new.loc[fill, 'label'].ne(''), new.loc[fill, 'entity'])
    for col in ('source', 'source_url', 'confidence', 'evidence', 'date_downloaded', 'class'):
        if col not in new.columns:
            new[col] = ''
        new[col] = new[col].fillna('')
    new.loc[fill, 'source'] = 'wallet-attribution:' + new.loc[fill, 'source_public'].astype(str) if 'source_public' in new else 'wallet-attribution'
    new.loc[fill, 'source_url'] = new.loc[fill, 'source_url_public'].where(new.loc[fill, 'source_url_public'].ne(''), DATASET) if 'source_url_public' in new else DATASET
    new.loc[fill, 'confidence'] = new.loc[fill, 'confidence_public'] if 'confidence_public' in new else 'Unverified'
    new.loc[fill, 'evidence'] = 'Public dataset category=' + new.loc[fill, 'category'].astype(str) + '; label=' + new.loc[fill, 'label'].astype(str)
    new.loc[fill, 'class'] = new.loc[fill, 'category']
    new.loc[fill, 'date_downloaded'] = datetime.now(timezone.utc).date().isoformat()
    # Keep original source detail for ALL matched addresses, including unknown category.
    new['public_entity'] = new['entity'].fillna('')
    new['public_label'] = new['label'].fillna('')
    new['public_category'] = new['category'].fillna('')
    new['public_source'] = new['source_public'].fillna('') if 'source_public' in new else ''
    new['public_source_url'] = new['source_url_public'].fillna('') if 'source_url_public' in new else ''
    new['public_confidence'] = new['confidence_public'].fillna('') if 'confidence_public' in new else ''
    disagreements = existing & recognized & new['mapped_type'].ne(new['entity_type'])
    new['label_conflict_review'] = disagreements
    new = new.drop(columns=[x for x in ('entity', 'label', 'category', 'mapped_type', 'source_public', 'source_url_public', 'confidence_public') if x in new])
    assert len(new) == len(df)
    assert new['address'].is_unique
    assert new['entity_type'].isin(TYPES).all()
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / 't07_public_enriched_wallet_labels.parquet'
    new.to_parquet(output, index=False)
    counts = {category: int(new['entity_type'].eq(category).sum()) for category in TYPES}
    summary = {
        'total_addresses': int(len(df)), 'public_addresses_matched': int(new['public_category'].ne('').sum()),
        'newly_labeled': int(fill.sum()), 'existing_labeled_preserved': int(existing.sum()),
        'conflicts_needing_review': int(disagreements.sum()), 'counts': counts,
        'source_dataset': DATASET, 'retrieved_utc': datetime.now(timezone.utc).isoformat(),
        'note': 'Unknown means no supported classification; classifications reflect upstream public labels and require verification for high-stakes use.'
    }
    (OUT / 't07_public_enrichment_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print('\n===== T07 PUBLIC LABEL RESULTS =====')
    for k in ('total_addresses', 'public_addresses_matched', 'newly_labeled', 'existing_labeled_preserved', 'conflicts_needing_review'):
        print(k + ':', f'{summary[k]:,}')
    for k, v in counts.items():
        print(f'{k}: {v:,}')
    print('Saved:', output)
    print('Summary:', OUT / 't07_public_enrichment_summary.json')

if __name__ == '__main__':
    main()
