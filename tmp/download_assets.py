"""C 资源下载脚本（国内 hf-mirror 路线）。

用法（必须用 TLS 正常的解释器）：
  D:\\CH02-01\\.venv-retrieval\\Scripts\\python.exe tmp\\download_assets.py --target bge
  D:\\CH02-01\\.venv-retrieval\\Scripts\\python.exe tmp\\download_assets.py --target index
  D:\\CH02-01\\.venv-retrieval\\Scripts\\python.exe tmp\\download_assets.py --target all

说明：
  - 走 HF_ENDPOINT=https://hf-mirror.com，不需要代理
  - HF_HOME 指向 D 盘，避免写爆 C 盘
  - revision 全部固定，符合 m3.v1「不可变 revision」要求
  - BGE 用 allow_patterns 只取 safetensors 一份，省掉 ~2.7GB 的 bin/onnx 重复权重
  - 本脚本只负责把资源落到本地，不产生任何正式实验结果
"""

from __future__ import annotations

import argparse
import os
import shutil
import time
from pathlib import Path

# ---- 固定坐标（已通过 hf-mirror API 核实） ----
INDEX_REPO = "crag-mm-2025/web-search-index-public-test"
INDEX_REVISION = "bd32162ffb21626994ad86ab147793561ba8fad2"

ENCODER_REPO = "BAAI/bge-large-en-v1.5"
ENCODER_REVISION = "d4aa6901d3a41ba39fb536a557fa166f842b0e09"

# 只取 sentence-transformers 真正需要的文件，避开 pytorch_model.bin / onnx
ENCODER_ALLOW = [
    "model.safetensors",
    "config.json",
    "config_sentence_transformers.json",
    "sentence_bert_config.json",
    "modules.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "1_Pooling/*",
]

HF_HOME = Path(r"D:\CH02-01\search_indices\hf_home")


def configure_env() -> None:
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HOME", str(HF_HOME))
    # 1.26.1 需要 hf-xet 走 Xet 传输，本机没有可用的 cp313 hf_xet，强制走普通 HTTP LFS
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    # 不要把大文件写到 C 盘
    os.environ.setdefault("HF_HUB_CACHE", str(HF_HOME / "hub"))
    HF_HOME.mkdir(parents=True, exist_ok=True)


def dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def human(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.2f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.2f} GiB"


def download(target: str) -> None:
    from huggingface_hub import snapshot_download

    if target in ("bge", "all"):
        print("=" * 70)
        print(f"[BGE] {ENCODER_REPO} @ {ENCODER_REVISION}")
        print("=" * 70, flush=True)
        t0 = time.time()
        path = snapshot_download(
            repo_id=ENCODER_REPO,
            revision=ENCODER_REVISION,
            allow_patterns=ENCODER_ALLOW,
            max_workers=8,
        )
        dt = time.time() - t0
        size = dir_size(Path(path))
        print(f"[BGE] 完成: {path}")
        print(f"[BGE] 大小 {human(size)}  耗时 {dt:.1f}s  "
              f"均速 {size / max(dt, 1e-9) / 1024 / 1024:.2f} MiB/s", flush=True)

    if target in ("index", "all"):
        print("=" * 70)
        print(f"[INDEX] {INDEX_REPO} @ {INDEX_REVISION}")
        print("[INDEX] 约 17.63 GB，国内镜像可能需要较长时间，请勿中断", flush=True)
        print("=" * 70, flush=True)
        t0 = time.time()
        path = snapshot_download(
            repo_id=INDEX_REPO,
            repo_type="dataset",
            revision=INDEX_REVISION,
            max_workers=8,
        )
        dt = time.time() - t0
        size = dir_size(Path(path))
        print(f"[INDEX] 完成: {path}")
        print(f"[INDEX] 大小 {human(size)}  耗时 {dt:.1f}s  "
              f"均速 {size / max(dt, 1e-9) / 1024 / 1024:.2f} MiB/s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="下载 C 的官方 Web 索引与 BGE 编码器")
    ap.add_argument("--target", choices=["bge", "index", "all"], default="all")
    args = ap.parse_args()

    configure_env()
    from huggingface_hub import constants

    print(f"HF_ENDPOINT   = {os.environ['HF_ENDPOINT']}")
    print(f"HF_HOME       = {constants.HF_HOME}")
    print(f"HF_HUB_CACHE  = {constants.HF_HUB_CACHE}")
    free = shutil.disk_usage("D:\\").free
    print(f"D: 可用空间    = {human(free)}")
    print()

    if free < 25 * 1024**3:
        raise SystemExit("D 盘空间不足 25GB，先清理再下载")

    download(args.target)


if __name__ == "__main__":
    main()
