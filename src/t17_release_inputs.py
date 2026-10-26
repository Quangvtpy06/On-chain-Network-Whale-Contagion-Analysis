"""Xác minh release T15/T16 chỉ đọc; không sửa output hoặc review upstream."""
import json

from src.analysis_release import SOURCE_FILES
from src.forecast_inputs import ROOT, file_hash, hash_paths, local_path, read_config, require, verify_hashes


def artifact_names(task):
    if task == 't15':
        return {'t15_volatility_regression_results.parquet', 't15_volatility_regression_summary.parquet',
                't15_sample_membership.parquet', 't15_validation.parquet', 't15_report.md', 't15_flow_coefficients.png'}
    return {'t16_event_study_results.parquet', 't16_event_selection.parquet', 't16_event_windows.parquet',
            't16_event_candidates.parquet', 't16_validation.parquet', 't16_report.md'} | {
                f't16_{event}_response.png' for event in
                ['large_transfer', 'cex_net_inflow', 'activity_cohort_net_inflow', 'concentration']}


def verify_release(task, config, directory, gate, t14_hashes):
    config, directory = local_path(config), local_path(directory)
    cfg = read_config(config)
    require(directory == local_path(cfg['output_dir']), 'Upstream output/config path mismatch')
    summary_path = directory / f'{task}_summary.json'
    review_path = directory / f'{task}_independent_review.json'
    names = artifact_names(task)
    before = hash_paths([config, summary_path, review_path] + [directory / n for n in sorted(names)])
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    review = json.loads(review_path.read_text(encoding='utf-8'))
    require(summary.get('computation_validated') is True and review.get('all_pass') is True, 'Unaccepted ' + task)
    require(summary['parameters'] == cfg and summary['protocol_id'] == cfg['protocol_id'], 'Upstream config changed')
    sources = hash_paths([ROOT / n for n in SOURCE_FILES] + [config])
    require(summary['source_config_sha256'] == review['source_config_sha256'] == sources, 'Upstream source/config changed')
    require(review['summary_sha256'] == file_hash(summary_path), 'Upstream summary/review mismatch')
    require(set(summary['output_sha256']) == names, 'Incomplete upstream artifact manifest')
    require(summary['output_sha256'] == review['output_sha256'], 'Upstream output/review mismatch')
    require(summary['input_sha256'] == review['input_sha256'], 'Upstream input/review mismatch')
    for name in sorted(names):
        require(file_hash(directory / name) == summary['output_sha256'][name], 'Changed upstream artifact: ' + name)
    for name, expected in t14_hashes.items():
        require(summary['input_sha256'].get(name) == expected, 'Upstream T14 release mismatch: ' + name)
    tables = {n for n in names if n.endswith('.parquet')}
    require(set(summary['content_hashes']) == set(review['content_hashes']) == tables, 'Incomplete reproduction evidence')
    for name, pair in summary['content_hashes'].items():
        require(pair['run1'] == pair['run2'] == review['content_hashes'][name], 'Upstream content/review mismatch')
    require(summary['policy'] == gate['policy'], 'Upstream policy differs')
    require(summary['rq3_answered'] is False and summary['ready_for_individual_investor_inference'] is False,
            'Unsupported upstream research claim')
    verify_hashes(summary['input_sha256']); verify_hashes(sources); verify_hashes(before)
    return cfg, summary, {**before, **sources, **summary['input_sha256']}
