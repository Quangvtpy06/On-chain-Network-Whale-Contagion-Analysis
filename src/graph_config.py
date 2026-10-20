"""Cấu hình và đường dẫn dùng chung cho T07/T08."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_config(path=None):
    path = Path(path) if path else ROOT / 'config/config.yaml'
    with path.open(encoding='utf-8') as stream:
        return yaml.safe_load(stream)


def project_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def relative_path(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def resolve_raw(config):
    """Ưu tiên file dự án, sau đó cache có sẵn; không tải lại ngầm."""
    rel = config['data']['interim_raw_transfers']
    local = project_path(rel)
    if local.is_file() and local.stat().st_size > 2048:
        return local
    cache = Path.home() / '.cache/huggingface/hub'
    repo = config['huggingface']['repo_id'].replace('/', '--')
    candidates = sorted((cache / f'datasets--{repo}' / 'snapshots').glob(f'*/{rel}*'))
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 2048:
            return candidate
    raise FileNotFoundError(f'Không có dữ liệu thật cho {rel}; hãy tải dữ liệu trước.')
