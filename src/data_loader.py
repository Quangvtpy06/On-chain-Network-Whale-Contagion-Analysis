"""
Central Data Loader for On-chain Whale Contagion Analysis
==========================================================
Manages selective downloading, Git LFS resolution, and streaming
for datasets stored on Hugging Face and GitHub LFS.

Features:
- Selective download: Tải đúng file cần thiết từ Hugging Face Hub.
- Tự động cache: Tránh tải lại dữ liệu giữa các lần chạy.
- Tự động nhận diện & giải phóng Git LFS Pointer: Khi Hugging Face
  chỉ lưu pointer (~134 bytes), data_loader tự động truy vấn GitHub LFS
  để tải dữ liệu thực (tránh lỗi ArrowInvalid Parquet magic bytes).
- Parquet Batch Streaming: Đọc dữ liệu theo từng batch với pyarrow
  giúp tiết kiệm RAM, tránh lỗi OOM (Out Of Memory).
"""

from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path
from typing import Iterator, List, Optional, Tuple, Union

import pandas as pd
import pyarrow.parquet as pq
import requests
from huggingface_hub import hf_hub_download
from tqdm import tqdm

# Fix encoding cho Windows console
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ==============================================================================
# CONFIGURATION
# ==============================================================================

HF_REPO_ID = "team-crypto/Market-data-crypto-project"
HF_REPO_TYPE = "dataset"
GIT_LFS_ORIGIN = "https://github.com/Quangvtpy06/On-chain-Network-Whale-Contagion-Analysis.git"

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"


# ==============================================================================
# LFS POINTER UTILITIES
# ==============================================================================

def is_lfs_pointer_file(path: Path) -> bool:
    """Kiểm tra xem file có phải là file con trỏ Git LFS (~130B) thay vì file dữ liệu thật."""
    if not path.is_file():
        return False
    size = path.stat().st_size
    if size > 2048:
        return False
    try:
        with open(path, "rb") as f:
            header = f.read(45)
            return header.startswith(LFS_POINTER_PREFIX)
    except Exception:
        return False


def parse_lfs_pointer(pointer_text: str) -> Tuple[str, int]:
    """Trích xuất OID sha256 và kích thước file từ nội dung con trỏ Git LFS."""
    oid_match = re.search(r"oid sha256:([a-f0-9]{64})", pointer_text)
    size_match = re.search(r"size (\d+)", pointer_text)
    if not oid_match or not size_match:
        raise ValueError("Invalid Git LFS pointer format")
    return oid_match.group(1), int(size_match.group(1))


def resolve_lfs_download_url(oid: str, size: int, git_repo_url: str = GIT_LFS_ORIGIN) -> str:
    """Gửi yêu cầu tới Git LFS Batch API để lấy link tải trực tiếp (S3 presigned URL)."""
    lfs_url = git_repo_url.rstrip("/") + "/info/lfs/objects/batch"
    payload = {
        "operation": "download",
        "transfers": ["basic"],
        "objects": [{"oid": oid, "size": size}],
    }
    headers = {
        "Accept": "application/vnd.git-lfs+json",
        "Content-Type": "application/vnd.git-lfs+json",
    }
    resp = requests.post(lfs_url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    objects = data.get("objects", [])
    if not objects or "actions" not in objects[0] or "download" not in objects[0]["actions"]:
        raise RuntimeError(f"Git LFS object not found or cannot be downloaded: {oid}")
    return objects[0]["actions"]["download"]["href"]


def download_file_with_progress(url: str, dest_path: Path, expected_size: Optional[int] = None) -> Path:
    """Tải file từ URL trực tiếp với thanh tiến trình tqdm."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_name(dest_path.name + ".part")

    print(f"[*] Đang tải dữ liệu thực ({expected_size / (1024 * 1024):.2f} MB)..." if expected_size else "[*] Đang tải dữ liệu thực...")
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    total = int(response.headers.get("content-length", expected_size or 0))
    chunk_size = 1024 * 1024  # 1MB chunk

    with open(temp_path, "wb") as f, tqdm(
        total=total,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        desc=dest_path.name,
    ) as pbar:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                pbar.update(len(chunk))

    os.replace(temp_path, dest_path)
    print(f"[+] Tải thành công: {dest_path.name} ({dest_path.stat().st_size / (1024 * 1024):.2f} MB)")
    return dest_path


# ==============================================================================
# MAIN DATA PATH RESOLVER
# ==============================================================================

def get_data_path(
    repo_relative_path: Union[str, Path],
    local_fallback: bool = True,
    force_download: bool = False,
    repo_id: str = HF_REPO_ID,
    repo_type: str = HF_REPO_TYPE,
) -> Path:
    """
    Lấy đường dẫn file dữ liệu sẵn sàng để đọc (Path).
    
    Quy trình:
    1. Nếu local_fallback=True: Kiểm tra file tại PROJECT_ROOT / repo_relative_path.
       - Nếu file tồn tại VÀ không phải LFS pointer -> dùng file local.
    2. Nếu không có file local hợp lệ:
       - Tải file từ Hugging Face Hub thông qua `hf_hub_download` (có cache tự động).
    3. Nếu file từ HF là LFS pointer text (~134B):
       - Tự động truy vấn Git LFS Batch API để tải binary thật vào cache/local.
    4. Trả về đối tượng Path trỏ tới dữ liệu thực.
    """
    clean_rel = str(repo_relative_path).replace("\\", "/").lstrip("/")
    local_path = PROJECT_ROOT / clean_rel

    # 1. Kiểm tra file local nếu có
    if local_fallback and not force_download and local_path.is_file():
        if not is_lfs_pointer_file(local_path):
            return local_path
        print(f"[!] File local {clean_rel} là Git LFS pointer. Đang giải quyết dữ liệu thực...")

    # 2. Tải từ Hugging Face Hub (tận dụng cache Hugging Face)
    try:
        hf_cached_path = Path(
            hf_hub_download(
                repo_id=repo_id,
                filename=clean_rel,
                repo_type=repo_type,
                force_download=force_download,
            )
        )
    except Exception as exc:
        raise FileNotFoundError(
            f"[-] Không thể tải {clean_rel} từ Hugging Face Hub ({repo_id}): {exc}"
        ) from exc

    # 3. Kiểm tra xem file tải về có phải là LFS pointer không
    if is_lfs_pointer_file(hf_cached_path):
        pointer_text = hf_cached_path.read_text(encoding="utf-8")
        oid, expected_size = parse_lfs_pointer(pointer_text)

        # File dữ liệu thực tế sẽ được lưu cạnh pointer hoặc trong thư mục data local
        real_cached_file = hf_cached_path.with_name(hf_cached_path.name + f".{oid[:12]}.data")
        
        # Đồng thời kiểm tra nếu đã có ở thư mục local đích
        target_local_file = local_path if local_path.parent.exists() else None
        if target_local_file and target_local_file.is_file() and not is_lfs_pointer_file(target_local_file):
            return target_local_file

        if real_cached_file.is_file() and real_cached_file.stat().st_size == expected_size:
            return real_cached_file

        # Cần tải binary thật qua Git LFS
        print(f"[*] Phát hiện file Git LFS trên Hugging Face ({clean_rel}).")
        print(f"    OID: {oid}")
        print(f"    Kích thước dự kiến: {expected_size / (1024 * 1024):.2f} MB")
        
        download_url = resolve_lfs_download_url(oid, expected_size)
        
        # Ưu tiên lưu vào local target nếu thư mục tồn tại, hoặc lưu vào HF cache
        dest = target_local_file if target_local_file else real_cached_file
        download_file_with_progress(download_url, dest, expected_size)
        return dest

    return hf_cached_path


# ==============================================================================
# PARQUET STREAMING & BATCH ITERATOR
# ==============================================================================

def stream_parquet_batches(
    repo_relative_path: Union[str, Path],
    columns: Optional[List[str]] = None,
    batch_size: int = 100_000,
) -> Iterator[pd.DataFrame]:
    """
    Generator đọc và yield từng DataFrame batch từ file Parquet (tiết kiệm RAM).
    
    Args:
        repo_relative_path: Đường dẫn tương đối (e.g. 'data/interim/usdt_whale_transfers_interim.parquet')
        columns: Danh sách các cột cần lấy (bỏ qua cột không cần thiết để tối ưu RAM)
        batch_size: Kích thước mỗi batch (mặc định 100,000 dòng)
        
    Yields:
        pd.DataFrame của từng batch.
    """
    resolved_path = get_data_path(repo_relative_path)
    pf = pq.ParquetFile(resolved_path)

    for batch in pf.iter_batches(columns=columns, batch_size=batch_size):
        yield batch.to_pandas()


def get_parquet_metadata(repo_relative_path: Union[str, Path]) -> pq.FileMetaData:
    """Lấy metadata của file parquet (số dòng, số cột, schema) mà không cần nạp toàn bộ vào RAM."""
    resolved_path = get_data_path(repo_relative_path)
    pf = pq.ParquetFile(resolved_path)
    return pf.metadata
