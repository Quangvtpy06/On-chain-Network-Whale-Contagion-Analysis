"""T14: build NetFlow, WhaleFlow, realized volatility and controls X_t (daily, point-in-time).

Run from the project root after T05-T07, T08 and T12 v2 have been accepted:

    python T14_Flow_Volatility.py

Gates are verified structurally (protocol_id, cohort sha256, every input/output hash), not by one
boolean. The tables are computed twice (second run in .cache/), hashes are compared, truncation and
future-label mutation tests run, and readiness is reported per branch:
computation_validated / retrospective_analysis_ready / forecast_inputs_ready_cex /
forecast_inputs_ready_activity_cohort. Certification is scoped to approved endpoints/activity cohorts,
not individual ownership or an answered RQ3. No upload is performed.
`--skip-reproducibility` is for exploration and never marks the output ready. This script only reads the
T07/T12 gates; it never edits their flags.
"""
import argparse
import json
import shutil
import uuid
import subprocess
from pathlib import Path

import pandas as pd

from src import flow_volatility as fv
from src import t14_readiness as readiness
from src.graph_config import ROOT, project_path, read_config, relative_path
from src.node_centrality import sha256, verified_t08_inputs, write_json

SETTINGS = ROOT / 'config/t14.yaml'
FEATURES = 't14_features_daily.parquet'
COVERAGE_DAILY = 't14_cex_coverage_daily.parquet'
COVERAGE_MONTHLY = 't14_cex_coverage_monthly.parquet'
OVERLAP = 't14_cohort_cex_overlap_daily.parquet'
ELIGIBILITY = 't14_sample_eligibility_daily.parquet'
REPRODUCED = [FEATURES, COVERAGE_DAILY, COVERAGE_MONTHLY, OVERLAP, ELIGIBILITY]
PIT_CUTS = [0.25, 0.5, 0.75, 0.95]
SUPPORTED_SCOPES = {'v2_activity_cohort'}


def check_hashes(base, hashes, label):
    """Every listed file must exist and match; all problems are reported together."""
    problems = []
    for rel, digest in hashes.items():
        path = base / rel
        if not path.exists():
            problems.append(f'{rel}: missing')
        elif sha256(path) != digest:
            problems.append(f'{rel}: sha256 mismatch')
    if problems:
        raise ValueError(f'{label} failed verification: ' + '; '.join(problems))


def load_verified_gates(settings):
    """Verify T07 history gate and T12 v2 gate. Returns (t12_gate, t07_gate)."""
    ins = settings['inputs']

    # ---- T07 public-history registry ----
    t07 = json.loads(project_path(ins['t07_history_gate']).read_text(encoding='utf-8'))
    if t07.get('protocol_id') != settings['t07_protocol_id']:
        raise ValueError('T07 gate protocol_id mismatch')
    if not t07.get('technical_validation_passed') or t07.get('blocking_reasons'):
        raise ValueError('T07 history failed technical validation or has blocking reasons')
    if not t07.get('ready_for_t14_endpoint_lookup'):
        raise ValueError('T07 historical CEX subset has not been human-approved; '
                         'do not use candidates as PIT endpoints')
    history = project_path(ins['t07_label_history'])
    if project_path(t07['history_path']) != history:
        raise ValueError('t07_label_history differs from gate history_path')
    check_hashes(ROOT, t07['input_hashes'], 'T07 gate input_hashes')
    check_hashes(history.parent, t07['output_hashes'], 'T07 gate output_hashes')

    # ---- T12 v2 cohort ----
    t12 = json.loads(project_path(ins['t12_gate']).read_text(encoding='utf-8'))
    if t12.get('protocol_id') != settings['t12_protocol_id']:
        raise ValueError(f"T12 gate protocol_id mismatch: got {t12.get('protocol_id')!r}")
    cohort = project_path(ins['cohort_members'])
    if project_path(t12['cohort_path']) != cohort:
        raise ValueError('cohort_members differs from gate cohort_path')
    if t12['cohort_sha256'] != sha256(cohort):
        raise ValueError('T12 cohort sha256 mismatch')
    cohort_key = cohort.relative_to(project_path(t12['cohort_path']).parent.parent).as_posix()
    if t12['output_hashes'].get(cohort_key) != t12['cohort_sha256']:
        raise ValueError('T12 gate output_hashes disagree with cohort_sha256')
    check_hashes(ROOT, t12['input_hashes'], 'T12 gate input_hashes')
    check_hashes(cohort.parent.parent, t12['output_hashes'], 'T12 gate output_hashes')
    return t12, t07


def read_daily(path):
    """Daily OHLCV; the T06 file names its time column `date`, the code expects `datetime_utc`."""
    daily = pd.read_parquet(path)
    if 'datetime_utc' not in daily.columns:
        if 'date' not in daily.columns:
            raise ValueError('Daily market file has neither datetime_utc nor date column')
        daily = daily.rename(columns={'date': 'datetime_utc'})
    return daily


def load_inputs(cfg, settings):
    """Read every input after the gates verified it. Retrospective labels stay in a separate set."""
    load_verified_gates(settings)
    paths = {k: project_path(v) for k, v in settings['inputs'].items()}
    minute_manifest = json.loads(paths['market_1m_manifest'].read_text(encoding='utf-8'))
    if project_path(minute_manifest['output']['path']) != paths['market_1m'] or \
            sha256(paths['market_1m']) != minute_manifest['output']['sha256']:
        raise ValueError('Minute input differs from its published provenance manifest')
    if len(minute_manifest.get('sources', [])) != cfg['project']['total_days']:
        raise ValueError('Minute input provenance does not contain the full daily calendar')
    history = pd.read_parquet(paths['t07_label_history'])

    labels = pd.read_parquet(paths['labels_parquet'])
    secondary = pd.read_parquet(paths['secondary_labels'])
    # RETROSPECTIVE overlay, same as T12 build_cex. Secondary labels can only re-type addresses already
    # present in T07 and never silently resolve a conflict. Not used by the PIT branch.
    labels = labels.copy()
    for row in secondary.itertuples():
        present = labels.address.eq(row.address)
        if present.any() and labels.loc[present, 'is_entity_attributed'].any() \
                and not labels.loc[present, 'entity_type'].eq(row.entity_type).all():
            raise ValueError('Secondary label conflicts with attributed T07')
        for column in ['entity_name', 'entity_type', 'confidence', 'source_url']:
            labels.loc[present, column] = getattr(row, column)

    cohort_metadata = pd.read_parquet(paths['cohort_members'])
    cohort = cohort_metadata[['date', 'address']]
    return dict(
        edges=pd.read_parquet(
            paths['daily_edges_parquet'],
            columns=['time_window', 'from_address', 'to_address', 'total_value']
        ),
        cohort=fv.normalise_cohort(cohort),
        cohort_metadata=cohort_metadata,
        cex=fv.cex_set(labels),
        cex_history=history,
        minute=pd.read_parquet(
            paths['market_1m'],
            columns=['datetime_utc', 'close']
        ),
        daily=read_daily(paths['market_1d']),
        eth_stats=pd.read_csv(paths['eth_stats_csv']),
    ), paths


def compute(folder, cfg, settings, dates, gates):
    inputs, _ = load_inputs(cfg, settings)
    table = fv.build_features(inputs, settings, dates)
    table['whaleflow_gate_open'] = bool(gates['t12']['ready_for_cohort_whaleflow'])
    table['cex_labels_pit'] = bool(gates['t07']['ready_for_t14_endpoint_lookup'])
    table['protocol_id'] = settings['protocol_id']
    cov_daily, cov_monthly = fv.coverage_tables(table, n_retrospective_cex=len(inputs['cex']))
    tables = {FEATURES: table.reset_index(), COVERAGE_DAILY: cov_daily, COVERAGE_MONTHLY: cov_monthly,
              OVERLAP: fv.overlap_table(table), ELIGIBILITY: fv.eligibility_table(table, settings)}
    folder.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_parquet(folder / name, index=False)
    return inputs, table


def adapter_rows(history, cex_by_day, dates):
    """The cached C_D must equal the official entry point load_cex_for_cutoff (which re-verifies gate hashes)."""
    from src.cex_label_history import load_cex_for_cutoff
    rows = []
    for day in [dates[0], dates[len(dates) // 2], dates[-1]]:
        try:
            official = frozenset(load_cex_for_cutoff(pd.Timestamp(day, tz='UTC')).address)
            ok, detail = official == cex_by_day[day], f'n={len(official)}'
        except Exception as error:  # report, never swallow
            ok, detail = False, repr(error)
        rows.append(dict(check='adapter_matches_load_cex_for_cutoff', cut_date=day,
                         status='PASS' if ok else 'FAIL', detail=detail))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-reproducibility', action='store_true')
    args = parser.parse_args()

    cfg = read_config()
    settings = read_config(SETTINGS)
    if settings.get('readiness_contract_version') != readiness.VERSION:
        raise ValueError('Unsupported T14 readiness contract version')
    folder = project_path(settings['output_dir'])
    provenance = verified_t08_inputs(cfg)
    dates = list(fv.day_index(cfg['project']['start_date'], cfg['project']['end_date']))
    if len(dates) != cfg['project']['total_days']:
        raise ValueError('Calendar length does not match config')

    t12_gate, t07_gate = load_verified_gates(settings)
    input_hashes = {relative_path(project_path(v)): sha256(project_path(v))
                    for v in settings['inputs'].values()}
    source_hashes = {relative_path(p): sha256(p) for p in [ROOT / 'src/flow_volatility.py',
        ROOT / 'T14_Flow_Volatility.py', ROOT / 'src/cex_label_history.py',
        ROOT / 'src/t14_readiness.py', ROOT / 'scripts/validate_t14_release.py']}
    settings_hash = sha256(SETTINGS)
    gates = dict(t12=t12_gate, t07=t07_gate)
    scope = settings.get('whaleflow_scope')
    if scope is not None and scope not in SUPPORTED_SCOPES:
        raise ValueError(f'whaleflow_scope {scope!r} is not supported by this code; '
                         f'supported: {sorted(SUPPORTED_SCOPES)} (next_cohort_version needs a new T12 release)')
    scope_ok = scope in SUPPORTED_SCOPES

    inputs, table = compute(folder, cfg, settings, dates, gates)
    hashes = {name: dict(run1=sha256(folder / name)) for name in REPRODUCED}

    history = inputs['cex_history']
    cex_by_day = fv.asof_cex_sets(history, dates)
    cuts = [dates[int(len(dates) * q)] for q in PIT_CUTS]
    rows = [fv.validate(table, settings, dates, expected_days=cfg['project']['total_days'])]
    reference = settings.get('retrospective_reference', {}).get('t12_cex_netflow')
    if reference and project_path(reference).exists():
        t12_cex = pd.read_parquet(project_path(reference))
        rows.append(fv.validate(table, settings, dates, t12_cex)
                    .query("check == 'retrospective_matches_t12_cex_netflow'"))
    ok_sets, n_bad = fv.independent_asof_check(history, cex_by_day, dates)
    extra = [dict(check='independent_asof_subset', cut_date='', status='PASS' if ok_sets else 'FAIL',
                  detail=f'mismatching_days={n_bad}'),
             dict(check='history_addresses_lowercase', cut_date='',
                  status='PASS' if history.address.eq(history.address.str.lower()).all() else 'FAIL', detail='')]
    for name, ok, detail in fv.label_boundary_checks(history) + fv.known_example_checks():
        extra.append(dict(check=name, cut_date='', status='PASS' if ok else 'FAIL', detail=detail))
    unique_overlap, overlap_member_days = fv.overlap_addresses(inputs['cohort'], cex_by_day)
    ref = settings.get('reference_overlap')
    if ref:
        extra.append(dict(check='overlap_matches_handoff_reference', cut_date='',
                          status='PASS' if (len(unique_overlap) == ref['unique_addresses']
                                            and overlap_member_days == ref['member_days']) else 'FAIL',
                          detail=f'got {len(unique_overlap)} addresses/{overlap_member_days} member-days; '
                                 f"expected {ref['unique_addresses']}/{ref['member_days']}"))
    rows += [pd.DataFrame(extra), pd.DataFrame(adapter_rows(history, cex_by_day, dates)),
             fv.pit_check(inputs, settings, dates, cuts),
             readiness.contract_data_checks(inputs, table, settings, dates)]
    validation = pd.concat(rows, ignore_index=True)
    validation.to_parquet(folder / 't14_validation.parquet', index=False)

    same = None
    if not args.skip_reproducibility:
        cache = ROOT / '.cache'
        cache.mkdir(exist_ok=True)
        temporary = cache / f't14_{uuid.uuid4().hex}'
        try:
            compute(temporary, cfg, settings, dates, gates)
            for name in REPRODUCED:
                hashes[name]['run2'] = sha256(temporary / name)
        finally:
            if temporary.exists():
                if not temporary.resolve().is_relative_to(cache.resolve()):
                    raise ValueError('Unsafe cleanup')
                shutil.rmtree(temporary)
        same = all(h['run1'] == h['run2'] for h in hashes.values())
    if verified_t08_inputs(cfg) != provenance:
        raise ValueError('T08 inputs changed during T14')
    readiness.verify_hash_map(ROOT, input_hashes, 'T14 inputs during computation')
    readiness.verify_hash_map(ROOT, source_hashes, 'T14 sources during computation')
    if sha256(SETTINGS) != settings_hash:
        raise ValueError('T14 settings changed during computation')
    final_t12, final_t07 = load_verified_gates(settings)
    if final_t12 != t12_gate or final_t07 != t07_gate:
        raise ValueError('Upstream gates changed during T14')

    passed = bool(validation.status.eq('PASS').all())
    validated = bool(passed and same)
    t07_open = bool(t07_gate['ready_for_t14_endpoint_lookup'])
    t12_open = bool(t12_gate['ready_for_cohort_whaleflow'])
    contract = readiness.build_readiness(settings, gates, validation, hashes)
    prov_files = [project_path(settings['release_manifest'])] if settings.get('release_manifest') else []
    summary = dict(
        protocol_id=settings['protocol_id'],
        settings_sha256=sha256(SETTINGS),
        code_sha256={relative_path(p): sha256(p) for p in [ROOT / 'src/flow_volatility.py',
                                                           ROOT / 'T14_Flow_Volatility.py',
                                                           ROOT / 'src/cex_label_history.py',
                                                           ROOT / 'src/t14_readiness.py',
                                                           ROOT / 'scripts/validate_t14_release.py']},
        input_sha256={k: sha256(project_path(v)) for k, v in settings['inputs'].items()},
        release_manifest_sha256={relative_path(p): sha256(p) for p in prov_files if p.exists()},
        t12_cohort_sha256=t12_gate['cohort_sha256'], t12_protocol_id=t12_gate['protocol_id'],
        t07_protocol_id=t07_gate['protocol_id'],
        upstream=provenance, days=len(dates), horizons=settings['horizons'],
        horizon_definition=settings['target']['horizon_definition'],
        validation_passed=passed, reproducible=same,
        rows_with_all_controls=int(table[['ret_1d', 'log_volume_usdt', 'log_rv_month']].notna().all(axis=1).sum()),
        rows_with_cex_netflow_z=int(table.cex_netflow_z.notna().sum()),
        rows_with_pit_cex_netflow_z=int(table.pit_cex_netflow_z.notna().sum()),
        rows_with_whaleflow_z_retrospective=int(table.whaleflow_z.notna().sum()),
        rows_with_whaleflow_pit_z=int(table.whaleflow_pit_z.notna().sum()),
        rows_with_large_transfer=int(table.large_transfer_count.notna().sum()),
        days_without_cohort=int((~table.has_cohort).sum()),
        days_without_pit_labels=int(table.n_pit_cex_endpoints.eq(0).sum()),
        t07_approved_addresses=int(len(history)),
        n_pit_cex_endpoint_days=int(table.n_pit_cex_endpoints.gt(0).sum()),
        cohort_cex_pit_overlap_member_days=overlap_member_days,
        cohort_cex_pit_overlap_unique_addresses=len(unique_overlap),
        cohort_cex_retro_overlap_member_days=int(table.n_cohort_cex_retro_overlap.sum()),
        predictor_sets=fv.predictor_sets(),
        target_columns=[c for c in table.columns if c.startswith('target_')],
        computation_validated=validated,
        retrospective_analysis_ready=bool(validated and t12_gate.get('ready_for_descriptive_retrospective_sensitivity')),
        readiness_contract_version=readiness.VERSION,
        forecast_inputs_ready_cex=contract['forecast_inputs_ready_cex'],
        forecast_inputs_ready_activity_cohort=contract['forecast_inputs_ready_activity_cohort'],
        ready_for_individual_investor_inference=False, rq3_answered=False,
        blocking_reasons=contract['blocking_reasons'],
        t07_gate_ready_for_endpoint_lookup=t07_open, t12_gate_ready_for_cohort_whaleflow=t12_open,
        upstream_rq3_flags_informational_only=dict(t07=t07_gate.get('ready_for_rq3_pit_forecast'),
                                                  t12=t12_gate.get('ready_for_rq3_pit_forecast')),
        whaleflow_scope=scope,
        caveats=[
            'Retrospective branch (cex_*, whaleflow_*, large_cex_*) uses current T07 labels: not point-in-time evidence.',
            'PIT branch (pit_cex_*, whaleflow_pit_*, pit_large_*) uses C_D = approved public-history registry with '
            'public_available_at, effective_from < D and effective_to > D or null. This is public-information PIT, '
            'not the research-knowledge policy of T12 v2.',
            'Days without any approved label are NaN, not zero; days with labels and no transfers are 0.',
            'Known-CEX coverage is the observed share of the thresholded USDT network, not CEX recall; '
            'unknown addresses may be exchange wallets.',
            'Network covers netted USDT transfers >= 500000 only, not all Ethereum flows.',
            'spread_cs_proxy is a Corwin-Schultz high-low proxy, not a quoted spread; T06 has trades only.',
            'Cohort = unidentified high-activity addresses (T12 v2); no individual ownership inference.',
            'WhaleFlow PIT keeps v2 membership/rank. On the flow boundary a node in W and C_D is treated as CEX '
            '(core = W minus C_D acts as cohort side); overlap counts and edge volume are reported, not hidden. '
            'This is NOT a new top-50 cohort and the choice of scope belongs to the team.',
            'CEX->CEX volume is reported as internal and is excluded from external NetFlow; no DEX/bridge/market maker/'
            'issuer treasury is merged into CEX.',
        ])
    write_json(folder / 't14_summary.json', summary)
    write_json(folder / 't14_reproducibility.json', dict(all_match=same, hashes=hashes))
    contract.update(protocol_id=settings['protocol_id'], source_sha256=summary['code_sha256'],
                    config_sha256={relative_path(SETTINGS): sha256(SETTINGS)}, input_sha256=input_hashes,
                    output_sha256={name: sha256(folder / name) for name in REPRODUCED +
                        ['t14_validation.parquet', 't14_summary.json', 't14_reproducibility.json']},
                    upstream_protocols=dict(t07=t07_gate['protocol_id'], t12=t12_gate['protocol_id']))
    write_json(folder / 't14_downstream_gate.json', contract)
    artifacts = REPRODUCED + ['t14_validation.parquet', 't14_summary.json',
                              't14_reproducibility.json', 't14_downstream_gate.json']
    release = dict(repo_id=cfg['huggingface']['repo_id'], repo_type='dataset',
        tasks_accepted={'t14_computation': validated}, upload_performed=False,
        publication_state='local_only_pending_user_upload_instruction',
        readiness_contract_version=readiness.VERSION, policy=contract['policy'],
        forecast_inputs_ready_cex=contract['forecast_inputs_ready_cex'],
        forecast_inputs_ready_activity_cohort=contract['forecast_inputs_ready_activity_cohort'],
        source_base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_state='working_tree_pinned_by_sha256',
        source_sha256=summary['code_sha256'], config_sha256=contract['config_sha256'],
        input_sha256=input_hashes, blocked_upload_files=[] if validated else artifacts, missing_files=[],
        upload_files=[dict(path=relative_path(folder / name), sha256=sha256(folder / name),
                           bytes=(folder / name).stat().st_size) for name in artifacts],
        remote_dependencies=[dict(path=path, sha256=digest) for path, digest in input_hashes.items()
                             if Path(path).suffix in {'.parquet', '.json', '.csv'}],
        note='Scoped input certification only, not individual ownership or a completed RQ3 result. No upload performed.')
    write_json(folder / 't14_release_manifest.json', release)
    print(json.dumps({k: summary[k] for k in summary
                      if k not in ('predictor_sets', 'input_sha256', 'code_sha256', 'upstream', 'caveats')},
                     indent=2, ensure_ascii=False), flush=True)
    if not passed:
        print(validation[validation.status.ne('PASS')].to_string())
        raise SystemExit('T14 validation failed')


if __name__ == '__main__':
    main()
