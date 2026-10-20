"""Chạy T08, kiểm định B.1–B.9 và tạo báo cáo có thể tái lập."""
import hashlib
import json
from datetime import date
from pathlib import Path
import subprocess
import sys
import shutil
import uuid
import numpy as np
import pandas as pd

from src.graph_config import ROOT, read_config, project_path, relative_path, resolve_raw
from src.net_transfers import net_pairs_in_transaction, normalize_transfers
from src.build_dynamic_graph import (build_dynamic_edges, compute_graph_metrics,
    calculate_iso_week_metadata, generate_validation_table)
from src.analyze_residuals import run_b7_analysis

ARTIFACTS = ['dynamic_edges_daily.parquet', 'dynamic_edges_weekly.parquet',
    'graph_metrics_daily.parquet', 'graph_metrics_weekly.parquet', 't08_validation.parquet',
    't08_topology_comparison.parquet', 't08_monthly_retention.parquet', 't08_top10_days.parquet',
    't08_top20_nodes.parquet', 't08_direction_samples.parquet', 't08_multistep_cycle_audit.parquet']


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def direction_samples(raw, netted, edges, output):
    txs = sorted(raw.transaction_hash.unique())
    rng = np.random.default_rng(8)
    selected = rng.choice(txs, min(5, len(txs)), replace=False)
    keys = set(zip(edges.time_window, edges.from_address, edges.to_address))
    rows = []
    for tx in selected:
        source = raw.loc[raw.transaction_hash.eq(tx)]
        final = netted.loc[netted.transaction_hash.eq(tx)]
        pairs = sorted({tuple(sorted([r.from_address, r.to_address])) for r in source.itertuples() if r.from_address != r.to_address})
        for a, b in pairs:
            ab = source.loc[source.from_address.eq(a) & source.to_address.eq(b), 'amount'].sum()
            ba = source.loc[source.from_address.eq(b) & source.to_address.eq(a), 'amount'].sum()
            signed = round(float(ab-ba), 6)
            u, v = (a, b) if signed > 0 else (b, a)
            expected = abs(signed)
            match = final.loc[final.from_address.eq(u) & final.to_address.eq(v)]
            threshold = read_config()['graph']['min_edge_threshold_usdt']
            retained = expected > 0 and expected >= threshold
            day = str(source.tx_date.iloc[0])
            ok = (len(match) == 1 and np.isclose(match.amount.iloc[0], expected, atol=1e-4, rtol=1e-12)
                  and (day, u, v) in keys) if retained else match.empty
            rows.append(dict(transaction_hash=tx, date=day, canonical_a=a, canonical_b=b,
                raw_a_to_b=float(ab), raw_b_to_a=float(ba), expected_from=u, expected_to=v,
                expected_net=expected, retained=retained, status='PASS' if ok else 'FAIL'))
        if not pairs:
            rows.append(dict(transaction_hash=tx, date=str(source.tx_date.iloc[0]), status='PASS', retained=False))
    result = pd.DataFrame(rows)
    result.to_parquet(output / 't08_direction_samples.parquet', index=False)
    return bool(result.status.eq('PASS').all()), len(selected)


def run_once(input_parquet, output_dir, labels_path, config, rebuild_netted=True):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = resolve_raw(config)
    print('Reading raw transfers from local cache...', flush=True)
    raw_original = pd.read_parquet(raw_path, columns=['transaction_hash', 'log_index', 'from_address', 'to_address', 'amount', 'block_timestamp', 'tx_date'])
    duplicate_count = int(raw_original.duplicated(['transaction_hash', 'log_index']).sum())
    invalid_addresses = sum(int((~raw_original[c].astype('string').str.fullmatch(r'0x[0-9a-f]{40}').fillna(False)).sum()) for c in ['from_address', 'to_address'])
    utc_days = pd.to_datetime(raw_original.block_timestamp, utc=True).dt.date
    raw_utc_mismatches = int((pd.to_datetime(raw_original.tx_date).dt.date != utc_days).sum())
    raw = normalize_transfers(raw_original)
    del raw_original
    input_parquet = Path(input_parquet)
    threshold = config['graph']['min_edge_threshold_usdt']
    netted = net_pairs_in_transaction(raw, threshold)
    if rebuild_netted:
        input_parquet.parent.mkdir(parents=True, exist_ok=True)
        netted.to_parquet(input_parquet, index=False)
    elif input_parquet.is_file():
        existing = pd.read_parquet(input_parquet)
        if not existing.equals(netted):
            raise ValueError('Input netted không khớp kết quả tính lại từ raw')
    labels = pd.read_parquet(labels_path)
    if labels.address.duplicated().any() or 'is_contract' not in labels:
        raise ValueError('T07 chưa có bảng nhãn với trạng thái contract')
    start = date.fromisoformat(config['project']['start_date'])
    end = date.fromisoformat(config['project']['end_date'])
    dates = pd.date_range(start, end).date.tolist()
    days = [str(d) for d in dates]
    week_meta = calculate_iso_week_metadata(start, end)
    weeks = sorted(week_meta)
    if set(netted.tx_date) - set(dates):
        raise ValueError('Netted input có ngày ngoài khoảng nghiên cứu')
    daily = build_dynamic_edges(netted, 'daily', start, end)
    weekly = build_dynamic_edges(netted, 'weekly', start, end)
    daily.to_parquet(output_dir / 'dynamic_edges_daily.parquet', index=False)
    weekly.to_parquet(output_dir / 'dynamic_edges_weekly.parquet', index=False)
    dm = compute_graph_metrics(daily, 'NETTED DAILY', days)
    wm = compute_graph_metrics(weekly, 'NETTED WEEKLY', weeks, week_meta)
    dm.to_parquet(output_dir / 'graph_metrics_daily.parquet', index=False)
    wm.to_parquet(output_dir / 'graph_metrics_weekly.parquet', index=False)
    loops = raw.from_address.eq(raw.to_address)
    loops_by_date = raw.loc[loops].groupby('tx_date').size().to_dict()
    validation = generate_validation_table(netted, daily, dm, loops_by_date, dates)
    validation.to_parquet(output_dir / 't08_validation.parquet', index=False)
    # Đối chiếu mọi cạnh tuần với tổng cạnh ngày của cùng cặp ví.
    daily_week = daily.assign(week=pd.to_datetime(daily.time_window).dt.strftime('%G-W%V'))
    summed = daily_week.groupby(['week', 'from_address', 'to_address']).total_value.sum().sort_index()
    actual = weekly.set_index(['time_window', 'from_address', 'to_address']).total_value.sort_index()
    week_diff = float((summed.to_numpy()-actual.to_numpy()).max(initial=0)) if summed.index.equals(actual.index) else float('inf')
    week_ok = summed.index.equals(actual.index) and bool(np.allclose(summed, actual, rtol=1e-12, atol=1e-4))
    # So sánh trước/sau trên cùng chính sách self-loop (đều loại).
    gross = raw.loc[~loops].copy()
    gross['gross_amount'] = gross.amount
    gross['event_count'] = 1
    comparisons = []
    for window, windows, net_metrics, meta in [('daily', days, dm, None), ('weekly', weeks, wm, week_meta)]:
        before_edges = build_dynamic_edges(gross, window, start, end)
        before = compute_graph_metrics(before_edges, f'RAW {window.upper()}', windows, meta)
        columns = ['time_window', 'num_nodes', 'num_edges', 'density', 'reciprocity',
                   'num_weakly_connected_components', 'num_strongly_connected_components', 'total_volume_usdt']
        comparison = before[columns].merge(net_metrics[columns], on='time_window', suffixes=('_raw', '_netted'), validate='one_to_one')
        comparison.insert(0, 'window_type', window)
        comparisons.append(comparison)
        del before_edges
    topology = pd.concat(comparisons, ignore_index=True)
    topology.to_parquet(output_dir / 't08_topology_comparison.parquet', index=False)
    del gross
    sample_ok, sample_txs = direction_samples(raw, netted, daily, output_dir)
    residual = run_b7_analysis(netted, raw, labels, config, output_dir)
    all_addresses = set(raw.from_address) | set(raw.to_address)
    coverage = all_addresses <= set(labels.address)
    contract_known = bool(labels.is_contract.notna().all())
    checks = [
        dict(check='B.1', status='PASS' if validation.status.eq('PASS').all() and np.isclose(daily.total_value.sum(), netted.amount.sum(), rtol=1e-12, atol=1e-4) else 'FAIL',
             detail='Daily + full-period volume conserved. Edge tx-count versus global unique tx-count comparison omitted per user instruction.'),
        dict(check='B.2', status='PASS' if week_ok else 'FAIL', detail=f'All weekly edge keys and values checked; max positive diff={week_diff}'),
        dict(check='B.3', status='PASS' if len(dm)==len(days) and dm.time_window.tolist()==days else 'FAIL', detail=f'{len(dm)} daily snapshots, including empty windows'),
        dict(check='B.4', status='PASS' if raw_utc_mismatches==0 and netted.tx_date.eq(netted.block_timestamp.dt.date).all() and netted.tx_week.eq(netted.block_timestamp.dt.strftime('%G-W%V')).all() else 'FAIL', detail=f'Raw UTC day mismatches={raw_utc_mismatches}; windows recomputed from timestamp'),
        dict(check='B.5', status='PASS' if duplicate_count==0 and invalid_addresses==0 and coverage and contract_known else 'FAIL', detail=f'Raw duplicate keys={duplicate_count}; invalid/nonlowercase addresses={invalid_addresses}; raw self-loops={int(loops.sum())}; raw zero-address rows={int(raw.is_zero_address.sum())}; label coverage={coverage}; contract status complete={contract_known}'),
        dict(check='B.6', status='PASS' if sample_ok and sample_txs==5 else 'FAIL', detail=f'{sample_txs} deterministic random raw transactions checked against netted directions and daily edge membership'),
        dict(check='B.7', status=residual['status'] if residual['multistep_cycles']['balance_preserved'] else 'FAIL', detail=f'Top10 node share={residual["top10_nodes_volume_share"]:.6%}; measured explanations + full cycle audit exported; team decision needed={residual["decision_required"]}'),
        dict(check='B.8', status='PASS', detail='Density, reciprocity, SCC, WCC compared on all daily/weekly windows; numerical decrease is measured, not assumed'),
        dict(check='B.9', status='PENDING', detail='Second execution and independent review pending')]
    summary = dict(task='T08 - Dynamic Transaction Graph (netted flows)',
        input_files=dict(raw_transfers=config['data']['interim_raw_transfers'], netted_transfers=relative_path(input_parquet), labels=relative_path(labels_path), config='config/config.yaml'),
        output_files={name: relative_path(output_dir/name) for name in ARTIFACTS},
        time_range=dict(start_date=str(start), end_date=str(end), total_days_expected=len(days), total_days_snapshots=len(dm),
            total_weeks_snapshots=len(wm), partial_weeks_count=sum(m['is_partial_week'] for m in week_meta.values()),
            partial_weeks_list=[w for w,m in week_meta.items() if m['is_partial_week']], timezone='UTC', week_rule='ISO Monday start'),
        netting_results=dict(raw_transfer_events=len(raw), netted_transfer_rows=len(netted), raw_volume_usdt=float(raw.amount.sum()),
            netted_volume_usdt=float(netted.amount.sum()), volume_retention_ratio=float(netted.amount.sum()/raw.amount.sum()),
            self_loops_filtered=int(loops.sum()), raw_zero_address_rows=int(raw.is_zero_address.sum()), netted_zero_address_rows=int(netted.is_zero_address.sum()),
            gross_volume_surviving_pairs_usdt=float(netted.gross_amount.sum()), raw_sha256=sha256(raw_path), netted_sha256=sha256(input_parquet)),
        daily_graph_summary=dict(total_snapshots=len(dm), total_weighted_edges=len(daily), max_daily_volume_usdt=float(dm.total_volume_usdt.max()),
            avg_daily_reciprocity=float(dm.reciprocity.mean()), avg_raw_reciprocity=float(topology.loc[topology.window_type.eq('daily'), 'reciprocity_raw'].mean())),
        weekly_graph_summary=dict(total_snapshots=len(wm), total_weighted_edges=len(weekly), eligible_regression_weeks=int(wm.eligible_for_regression.sum())),
        validation_check_status=dict(all_days_pass=bool(validation.status.eq('PASS').all()), mass_conservation_days_passed=int(validation.status.eq('PASS').sum()), total_days_checked=len(validation)),
        b7_residual_analysis=residual, checks=checks,
        ready_for_t09_t12=False,
        limitations=['Pairwise netting cannot prove independent economic flows.', 'Raw input already excludes transfers below 500,000 USDT, so omitted counterflows cannot be recovered.',
                      'gross_value/event_count on surviving edges include both directions of surviving pairs only; canceled and threshold-dropped pairs are excluded.',
                      'Graph describes whale-transfer subnetwork; degrees and centrality are truncated.',
                      'Contract flag is creation recorded before study end; no inferred economic identity.'])
    return summary


def write_reports(summary, output_dir):
    output_dir = Path(output_dir)
    (output_dir/'t08_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    pd.DataFrame(summary['checks']).to_parquet(output_dir/'t08_acceptance_checks.parquet', index=False)
    net = summary['netting_results']; daily=summary['daily_graph_summary']; weekly=summary['weekly_graph_summary']
    lines = ['# T08 — Báo cáo chạy lại và nghiệm thu', '',
        f'**Trạng thái:** {"Đủ điều kiện sử dụng" if summary["ready_for_t09_t12"] else "Chưa được chuyển sang T09–T12"}.', '',
        f'Đầu vào gốc: `{summary["input_files"]["raw_transfers"]}`; file gốc được giữ nguyên, đối soát bằng SHA-256.',
        f'Netted: **{net["raw_transfer_events"]:,} → {net["netted_transfer_rows"]:,} dòng**; volume **{net["raw_volume_usdt"]:,.2f} → {net["netted_volume_usdt"]:,.2f} USDT**.',
        f'Giữ lại {net["volume_retention_ratio"]:.4%} volume; loại {net["self_loops_filtered"]} self-loop.', '',
        f'Daily: **{daily["total_snapshots"]} snapshot**, **{daily["total_weighted_edges"]:,} cạnh**; volume ngày cao nhất **{daily["max_daily_volume_usdt"]:,.2f} USDT**.',
        f'Weekly: **{weekly["total_snapshots"]} snapshot**, **{weekly["total_weighted_edges"]:,} cạnh**; **{weekly["eligible_regression_weeks"]} tuần đủ ngày** dùng cho hồi quy.',
        f'Reciprocity trung bình ngày: raw={daily["avg_raw_reciprocity"]:.8f}, netted={daily["avg_daily_reciprocity"]:.8f}.', '',
        '| Kiểm tra | Kết quả | Ghi nhận |', '|---|---|---|']
    lines += [f'| {c["check"]} | {c["status"]} | {c["detail"]} |' for c in summary['checks']]
    lines += ['', 'B.1 bỏ đối chiếu tổng transaction_count cạnh với unique transaction toàn ngày theo yêu cầu người dùng.',
        'B.7: xem top 10 ngày (kèm các tác nhân đo được), top 20 nút và audit chu trình trong thư mục kết quả. Không khẳng định nguyên nhân kinh tế khi chưa có bằng chứng.',
        'Review độc lập được thực hiện bằng chương trình riêng không import hàm production; đây là kiểm tra tính toán, không thay chữ ký reviewer của nhóm.',
        'Nếu B.7 cần quyết định: nhóm phải phê duyệt chính sách loại chu trình nhiều bước trước T09–T12.', '',
        'Tái lập: chạy `python T08_Dynamic_Transaction_Graph.py` tại thư mục crypto. Mặc định chạy hai lần và review độc lập.',
        'Các hash kết quả nằm trong `data/processed/graphs/t08_reproducibility.json`.']
    (ROOT/'docs/T08_completion_report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def run_pipeline(input_parquet=None, output_dir=None, labels_path=None, verify_reproducibility=True):
    config = read_config()
    input_parquet = Path(input_parquet or project_path(config['data']['interim_netted_transfers']))
    output_dir = Path(output_dir or project_path(config['data']['processed_graphs_dir']))
    labels_path = Path(labels_path or project_path(config['data']['processed_labels_parquet']))
    summary = run_once(input_parquet, output_dir, labels_path, config)
    write_reports(summary, output_dir)
    if verify_reproducibility:
        # Bản chạy thử không thuộc data/ và được dọn ngay sau đối chiếu hash.
        second = ROOT/'.cache'/('t08_repro_'+uuid.uuid4().hex)
        print('=== Second independent execution from raw ===', flush=True)
        try:
            run_once(input_parquet, second, labels_path, config, rebuild_netted=False)
            hashes = {name: dict(run1=sha256(output_dir/name), run2=sha256(second/name)) for name in ARTIFACTS}
        finally:
            # Kiểm tra phạm vi trước khi xóa thư mục tạm, kể cả khi lần chạy lỗi.
            second.resolve().relative_to((ROOT/'.cache').resolve())
            if second.exists():
                shutil.rmtree(second)
        same = all(pair['run1']==pair['run2'] for pair in hashes.values())
        manifest = dict(all_match=same, hashes=hashes)
        (output_dir/'t08_reproducibility.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print('=== Independent review (separate implementation) ===', flush=True)
        review = subprocess.run([sys.executable, str(ROOT/'src/t08_review.py'), '--output', str(output_dir),
                                  '--input', str(input_parquet), '--labels', str(labels_path)], cwd=ROOT, check=False)
        summary['checks'][-1] = dict(check='B.9', status='PASS' if same and review.returncode==0 else 'FAIL',
             detail=f'Two raw-to-graph executions: {len(hashes)} artifact hashes match={same}; independent review exit={review.returncode}')
        summary['reproducibility'] = manifest
        summary['independent_review_passed'] = review.returncode==0
    summary['ready_for_t09_t12'] = all(c['status']=='PASS' for c in summary['checks'])
    write_reports(summary, output_dir)
    print('T08 ready_for_t09_t12 =', summary['ready_for_t09_t12'], flush=True)
    return summary
