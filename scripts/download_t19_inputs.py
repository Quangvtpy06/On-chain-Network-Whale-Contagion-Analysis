"""Download all T19 required input files from Hugging Face."""
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'config/config.yaml'
T19_CONFIG_PATH = ROOT / 'config/t19.yaml'


def download_file(repo_id, filename, local_dir):
    from huggingface_hub import hf_hub_download
    dest = local_dir / filename
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [SKIP] {filename} already exists", flush=True)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [DOWNLOAD] {filename}...", flush=True)
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        repo_type="dataset",
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
    )
    return Path(path)


def main():
    if not CONFIG_PATH.is_file() or not T19_CONFIG_PATH.is_file():
        print("Missing config files.")
        sys.exit(1)

    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding='utf-8'))
    t19_cfg = yaml.safe_load(T19_CONFIG_PATH.read_text(encoding='utf-8'))
    repo_id = cfg['huggingface']['repo_id']

    needed = []
    for w in t19_cfg['window_types']:
        for k, v in t19_cfg['inputs'].items():
            needed.append(v.format(window=w))
    needed = sorted(set(needed))

    print(f"=== Downloading T19 inputs from Hugging Face ({repo_id}) ===", flush=True)
    for rel in needed:
        try:
            download_file(repo_id, rel, ROOT)
        except Exception as e:
            print(f"  [ERROR] Failed to download {rel}: {e}", flush=True)

    print("=== T19 inputs download completed ===", flush=True)


if __name__ == '__main__':
    main()
