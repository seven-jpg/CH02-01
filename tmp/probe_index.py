"""C 模块可行性探测：真实打开官方 Web 索引 + BGE 编码 + 查询一次。

只读取工作副本（D:\\CH02-01\\search_indices\\index_working），不碰 HF 缓存里那份已校验的快照。
输出：集合元信息（含距离空间，用于确定 m3.v1 的 score_kind）、命中、耗时、峰值内存。
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import time
from pathlib import Path

INDEX_WORKING = Path(r"D:\CH02-01\search_indices\index_working")
BGE_REVISION = "d4aa6901d3a41ba39fb536a557fa166f842b0e09"

# ---- 峰值内存（Windows PeakWorkingSetSize）----


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def mem_mb() -> tuple[float, float]:
    """返回 (当前工作集, 峰值工作集) MB。必须设置 argtypes/restype，否则静默返回 0。"""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)

    k32.GetCurrentProcess.restype = wt.HANDLE
    k32.GetCurrentProcess.argtypes = []
    psapi.GetProcessMemoryInfo.restype = wt.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [
        wt.HANDLE,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
        wt.DWORD,
    ]

    c = PROCESS_MEMORY_COUNTERS()
    c.cb = ctypes.sizeof(c)
    ok = psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    if not ok:
        return -1.0, -1.0
    return c.WorkingSetSize / 1024**2, c.PeakWorkingSetSize / 1024**2


# ---- 官方编码配方（照抄 cragmm-search-pipeline 0.5.1 的 extract_features）----

def mean_pooling(token_embeddings, attention_mask):
    import torch

    m = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * m, 1) / torch.clamp(m.sum(1), min=1e-9)


def extract_features(model, tokenizer, text, device):
    import torch

    single = isinstance(text, str)
    if single:
        text = [text]
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        outputs = model(**inputs)
        feats = mean_pooling(outputs.last_hidden_state, inputs["attention_mask"])
    feats = feats / feats.norm(dim=-1, keepdim=True)   # L2 归一化
    feats = feats.cpu().numpy()
    return feats[0] if single else feats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="What is the capital of France?")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    args = ap.parse_args()

    print("=" * 72)
    ws0, peak0 = mem_mb()
    print(f"[mem] 启动: working={ws0:.0f}MB peak={peak0:.0f}MB")

    # ---------- 1. 打开索引 ----------
    t0 = time.time()
    import chromadb

    print(f"[chromadb] {chromadb.__version__}")
    client = chromadb.PersistentClient(path=str(INDEX_WORKING))
    collection = client.get_collection(name="web_search_embeddings")
    t_open = time.time() - t0
    ws1, peak1 = mem_mb()
    print(f"[open] 集合打开耗时 {t_open:.1f}s, working={ws1:.0f}MB peak={peak1:.0f}MB")

    n = collection.count()
    print(f"[collection] name=web_search_embeddings  count={n:,}")
    print(f"[collection] metadata      = {collection.metadata}")
    try:
        cfg = collection.configuration
        print(f"[collection] configuration = {cfg}")
    except Exception as e:
        print(f"[collection] configuration 读取失败: {type(e).__name__}: {e}")

    # ---------- 2. 加载 BGE ----------
    import torch
    from transformers import AutoModel, AutoTokenizer

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    print(f"[bge] device = {device}")

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained("BAAI/bge-large-en-v1.5", revision=BGE_REVISION)
    model = AutoModel.from_pretrained("BAAI/bge-large-en-v1.5", revision=BGE_REVISION).to(device)
    model.eval()
    print(f"[bge] 加载耗时 {time.time() - t0:.1f}s")
    ws2, peak2 = mem_mb()
    print(f"[mem] BGE 加载后: working={ws2:.0f}MB peak={peak2:.0f}MB")

    # ---------- 3. 编码 + 查询 ----------
    t0 = time.time()
    emb = extract_features(model, tok, args.query, device)
    t_enc = time.time() - t0

    t0 = time.time()
    res = collection.query(query_embeddings=emb.reshape(1, -1).tolist(), n_results=args.top_k)
    t_q = time.time() - t0
    ws3, peak3 = mem_mb()

    print(f"\n[query] {args.query!r}")
    print(f"[timing] 编码 {t_enc * 1000:.0f}ms | 查询 {t_q * 1000:.0f}ms")
    print(f"[mem] 查询后: working={ws3:.0f}MB  **峰值={peak3:.0f}MB**")

    ids = res["ids"][0]
    dists = res["distances"][0] if res.get("distances") else [None] * len(ids)
    metas = res["metadatas"][0] if res.get("metadatas") else [None] * len(ids)

    print(f"\n命中 {len(ids)} 条:")
    for i, (doc_id, d, meta) in enumerate(zip(ids, dists, metas), 1):
        score = None if d is None else round(1.0 - d, 6)
        meta = meta or {}
        print(f"  #{i} distance={d!r}  1-d={score}")
        print(f"      doc_id : {doc_id}")
        print(f"      title  : {str(meta.get('page_name'))[:80]}")
        print(f"      url    : {str(meta.get('page_url'))[:100]}")
        print(f"      text   : {str(meta.get('page_snippet'))[:120]}...")

    print("\n" + "=" * 72)
    print(f"[结论] 索引可查 ✓  集合 {n:,} 条  **峰值内存 {peak3:.0f} MB**")


if __name__ == "__main__":
    main()
