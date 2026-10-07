"""B 岗位正式交付物：从官方 CRAG-MM 单轮数据集生成 m3.v1 数据包。

生成（相对仓库根目录）：
    data/processed/m3/manifest.json
    data/processed/m3/{smoke,dev,eval}/{questions,answers,metadata}.jsonl

CLI：
    python preprocessing/prepare_data.py --config experiments/m3/data.json --output-dir data/processed/m3
    可选 --subsets smoke（逗号分隔；默认全部。manifest 始终含三集合完整 ID 清单与哈希）

规则：
    - revision 必须是不可变 commit SHA（config 中指定）
    - turns/answers 按 interaction_id 配对，禁止 zip 假设顺序；ground_truth 来自真实 ans_full
    - 官方 ID 全局唯一则保留；不唯一则命名空间 st:<split>:<session_id>:<turn_index>，metadata 保存原编号映射
    - 按 session / 相同图像字节(SHA256) / 相同官方 image_url / 相同 query 文本分组，seed=42，同一组不跨集合
    - 按真实 domain 分布近似分层采样（组为采样单元，域配额贪心分配）
    - manifest 先最终写出，再计算原字节 SHA256；所有逐题文件引用同一 dataset_manifest_sha256
    - JSONL：UTF-8 无 BOM、ID 全 string、无 NaN/Infinity、缺值 null、schema_version="m3.v1"

已知限制：内嵌图仅识别字节级相同（SHA256）；外链图以官方 image_url 作为同一图像标识；内嵌图与外链图之间无法互认。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]  # 仓库根目录，不写死盘符

SCHEMA_VERSION = "m3.v1"


def _stable_bytes(obj: dict) -> bytes:
    """规范序列化为 UTF-8 字节：无 BOM、\\n 换行、末尾一个换行。用于计算原字节 SHA256（manifest/报告）。"""
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    return text.encode("utf-8")


def _jsonl_bytes(obj: dict) -> bytes:
    """JSONL 行：紧凑单行 JSON（协议要求一行一个 JSON 对象），UTF-8 无 BOM。"""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    if not p.exists():
        print(f"ERROR: config not found: {p}", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    required = ["dataset_id", "revision", "split", "seed", "subsets", "subset_order"]
    missing = [k for k in required if k not in cfg]
    if missing:
        print(f"ERROR: config missing keys: {missing}", file=sys.stderr)
        sys.exit(1)
    # revision 必须是 40 位十六进制 commit SHA
    if not (isinstance(cfg["revision"], str) and len(cfg["revision"]) == 40 and
            all(c in "0123456789abcdef" for c in cfg["revision"].lower())):
        print(f"ERROR: config revision must be an immutable 40-char commit SHA, got: {cfg['revision']!r}",
              file=sys.stderr)
        sys.exit(1)
    if cfg["seed"] != 42:
        print(f"ERROR: protocol requires seed=42, got {cfg['seed']}", file=sys.stderr)
        sys.exit(1)
    for name in cfg["subsets"]:
        if name not in ("smoke", "dev", "eval"):
            print(f"ERROR: unknown subset {name!r} (allowed: smoke/dev/eval)", file=sys.stderr)
            sys.exit(1)
    return cfg


def decode_label(feature_names: list[str] | None, value: Any) -> Any:
    """ClassLabel 整数索引 → 官方名称；无官方映射或值缺失 → null。"""
    if value is None:
        return None
    if feature_names is not None and isinstance(value, int) and 0 <= value < len(feature_names):
        return feature_names[value]
    if isinstance(value, str):
        return value
    return value  # 解码失败保留原值并计入报告


def extract_row_turns(row: dict, label_names: dict[str, list[str] | None]) -> tuple[list[dict], list[dict], str]:
    """把一行（一个 session）解析为 turn 列表和 answer 查找表。

    兼容 v0.1.2 dict-of-columns 与旧 list-of-dicts 两种格式。
    返回 (turns, answers_lookup, format_kind)。
    """
    turns_raw = row.get("turns")
    if isinstance(turns_raw, dict):  # v0.1.2 dict-of-columns
        n = len(turns_raw.get("interaction_id", []))
        turns = [{k: (v[i] if i < len(v) else None) for k, v in turns_raw.items()} for i in range(n)]
        fmt = "dict-of-columns"
    elif isinstance(turns_raw, list):  # 旧 list-of-dicts
        turns = [dict(t) for t in turns_raw if isinstance(t, dict)]
        fmt = "list-of-dicts"
    else:
        return [], {}, "unknown"

    answers_raw = row.get("answers")
    lookup: dict[str, str] = {}
    if isinstance(answers_raw, dict):
        ids = answers_raw.get("interaction_id", [])
        anss = answers_raw.get("ans_full", [])
        for i, aid in enumerate(ids):
            if aid is not None and aid not in lookup and i < len(anss):
                lookup[str(aid)] = anss[i] if anss[i] is not None else None
    elif isinstance(answers_raw, list):
        for a in answers_raw:
            if isinstance(a, dict) and a.get("interaction_id") is not None:
                lookup.setdefault(str(a["interaction_id"]), a.get("ans_full"))

    for t in turns:
        for k in ("domain", "query_category", "dynamism", "image_quality"):
            t[k] = decode_label(label_names.get(k), t.get(k))
    return turns, lookup, fmt


def image_hash(row: dict) -> tuple[str | None, str | None, int | None, int | None]:
    """计算图像字节级 SHA256 及尺寸。返回 (hash, format, width, height)。"""
    img = row.get("image")
    if img is None:
        return None, None, None, None
    try:
        fmt = getattr(img, "format", None)
        w, h = img.size
        hsh = sha256_hex(img.tobytes())
        return hsh, fmt, w, h
    except Exception:
        return "unhashable", fmt, None, None


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="B 的数据配置文件（JSON）")
    parser.add_argument("--output-dir", required=True, help="输出目录，如 data/processed/m3（相对仓库根）")
    parser.add_argument("--subsets", default="smoke,dev,eval",
                        help="本次导出的子集（逗号分隔）。manifest 始终含三集合完整 ID 清单与哈希")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    out_root = Path(args.output_dir)
    if not out_root.is_absolute():
        out_root = REPO_ROOT / out_root
    export_subsets = [s.strip() for s in args.subsets.split(",") if s.strip()]

    # 延迟导入：--help 不下载索引/数据
    from datasets import load_dataset

    t0 = time.time()
    ds = load_dataset(cfg["dataset_id"], revision=cfg["revision"])
    if cfg["split"] not in ds:
        print(f"ERROR: split {cfg['split']!r} not found. actual: {list(ds.keys())}", file=sys.stderr)
        sys.exit(1)
    split = ds[cfg["split"]]
    features = split.features
    label_names: dict[str, list[str] | None] = {}
    turns_feat = features.get("turns")
    if isinstance(turns_feat, dict):
        for k in ("domain", "query_category", "dynamism", "image_quality"):
            feat = turns_feat.get(k)
            if feat is not None and hasattr(feat, "names"):
                label_names[k] = list(feat.names)
            elif feat is not None and hasattr(feat, "feature") and hasattr(feat.feature, "names"):
                label_names[k] = list(feat.feature.names)  # List(ClassLabel) 解包
            else:
                label_names[k] = None
    else:
        label_names = {k: None for k in ("domain", "query_category", "dynamism", "image_quality")}

    # ---------- 逐行解析（只保留 turn 记录，不驻留图像） ----------
    rows_info: list[dict] = []      # 每行（session）的原始信息，供分组
    all_turns: list[dict] = []      # 所有 turn 记录
    counts: Counter = Counter()     # 缺失/重复等计数
    n_rows = 0
    for row in split:
        if cfg.get("max_rows") is not None and n_rows >= cfg["max_rows"]:
            break
        n_rows += 1
        session_id = str(row["session_id"]) if row.get("session_id") is not None else None
        turns, ans_lookup, fmt = extract_row_turns(row, label_names)
        ih, ifmt, iw, ihh = image_hash(row)
        url = row.get("image_url")
        uhash = sha256_hex(url.encode("utf-8")) if isinstance(url, str) and url else None
        row_idx = len(rows_info)
        rows_info.append({
            "session_id": session_id, "image_hash": ih, "image_url_hash": uhash,
            "image_format": ifmt, "image_width": iw, "image_height": ihh,
            "format": fmt, "n_turns": len(turns),
        })
        for i, t in enumerate(turns):
            iid = str(t["interaction_id"]) if t.get("interaction_id") is not None else None
            query = t.get("query")
            gt = ans_lookup.get(iid) if iid is not None else None
            if iid is None:
                counts["turn_no_interaction_id"] += 1
                continue
            if query is None or (isinstance(query, str) and not query.strip()):
                counts["empty_query_excluded"] += 1
                continue
            if gt is None:
                counts["missing_answer_excluded"] += 1
                continue
            all_turns.append({
                "interaction_id": iid, "session_id": session_id, "turn_index": i,
                "domain": t.get("domain"), "query_category": t.get("query_category"),
                "dynamism": t.get("dynamism"), "image_quality": t.get("image_quality"),
                "query": query, "ground_truth": gt, "row_idx": row_idx,
            })

    # ---------- ID 唯一性检查 ----------
    id_counter = Counter(t["interaction_id"] for t in all_turns)
    dup_ids = {k: v for k, v in id_counter.items() if v > 1}
    counts["duplicate_interaction_ids"] = len(dup_ids)
    if dup_ids:
        id_rule = "st:<split>:<session_id>:<turn_index>"
    else:
        id_rule = "official-id-kept"
    for t in all_turns:
        if t["interaction_id"] in dup_ids or len(t["interaction_id"]) == 0:
            t["final_id"] = f"st:{cfg['split']}:{t['session_id']}:{t['turn_index']}"
            t["id_renamed"] = True
        else:
            t["final_id"] = t["interaction_id"]
            t["id_renamed"] = False
    final_ids = [t["final_id"] for t in all_turns]
    if len(set(final_ids)) != len(final_ids):
        print("ERROR: final IDs still not unique after namespace rule", file=sys.stderr)
        sys.exit(1)

    # ---------- 分组：session / 相同图像字节 / 相同官方 image_url / 相同 query 文本 ----------
    uf = UnionFind(len(rows_info))
    img_map: dict[str, int] = {}
    url_map: dict[str, int] = {}
    q_map: dict[str, list[int]] = {}
    for ri, info in enumerate(rows_info):
        if info["image_hash"] is not None:
            if info["image_hash"] in img_map:
                uf.union(ri, img_map[info["image_hash"]])
            else:
                img_map[info["image_hash"]] = ri
    for ri, info in enumerate(rows_info):
        if info["image_url_hash"] is not None:
            if info["image_url_hash"] in url_map:
                uf.union(ri, url_map[info["image_url_hash"]])
            else:
                url_map[info["image_url_hash"]] = ri
    for t in all_turns:
        q_map.setdefault(t["query"], []).append(t["row_idx"])
    for ridxs in q_map.values():
        for j in range(1, len(ridxs)):
            uf.union(ridxs[0], ridxs[j])

    groups: dict[int, list[dict]] = {}
    for t in all_turns:
        g = uf.find(t["row_idx"])
        groups.setdefault(g, []).append(t)
    group_list = [{"turns": ts} for ts in groups.values()]
    for g in group_list:
        doms = Counter(t["domain"] for t in g["turns"] if t["domain"] is not None)
        g["domain"] = doms.most_common(1)[0][0] if doms else None

    # ---------- 按真实 domain 分布近似分层，seed=42 ----------
    rng = random.Random(cfg["seed"])
    rng.shuffle(group_list)
    targets = cfg["subsets"]
    order = cfg["subset_order"]
    n_valid = len(all_turns)
    dom_props = Counter(t["domain"] for t in all_turns if t["domain"] is not None)
    quota: dict[str, Counter] = {}
    for s in order:
        q = Counter({d: round(dom_props[d] / n_valid * targets[s]) for d in dom_props})
        diff = targets[s] - sum(q.values())
        if diff != 0 and dom_props:
            top = dom_props.most_common(1)[0][0]
            q[top] += diff
        quota[s] = q
    assigned: dict[str, Counter] = {s: Counter() for s in order}
    totals: dict[str, int] = {s: 0 for s in order}
    for g in group_list:
        d = g["domain"]
        best_s, best_def = None, -float("inf")
        for s in order:
            if totals[s] >= targets[s]:
                continue
            deficit = quota[s].get(d, 0) - assigned[s].get(d, 0)
            if deficit > best_def:
                best_def, best_s = deficit, s
        if best_s is None:
            break
        n = len(g["turns"])
        for t in g["turns"]:
            t["subset"] = best_s
        assigned[best_s][d] = assigned[best_s].get(d, 0) + n
        totals[best_s] += n

    # ---------- 写 manifest（先最终写出，再计算原字节 SHA256） ----------
    subset_ids = {s: sorted(t["final_id"] for t in all_turns if t.get("subset") == s) for s in order}
    grouping_desc = (
        "union-find groups over session, identical image (embedded byte SHA256 or official image_url) "
        "and identical query text; seed=42 shuffled order with per-domain quota greedy assignment to "
        "smoke/dev/eval; groups never cross subsets; subset closes at target size"
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "data_origin": "official",
        "dataset_id": cfg["dataset_id"],
        "revision": cfg["revision"],
        "split": cfg["split"],
        "seed": cfg["seed"],
        "grouping": grouping_desc,
        "id_rule": id_rule,
        "subsets": {s: {"ids": subset_ids[s], "count": len(subset_ids[s])} for s in order},
    }
    out_root.mkdir(parents=True, exist_ok=True)
    manifest_bytes = _stable_bytes(manifest)
    manifest_sha = sha256_hex(manifest_bytes)
    manifest_path = out_root / "manifest.json"
    with open(manifest_path, "wb") as f:
        f.write(manifest_bytes)

    # ---------- 写逐题文件 ----------
    turn_by_id = {t["final_id"]: t for t in all_turns}
    for s in export_subsets:
        sdir = out_root / s
        sdir.mkdir(parents=True, exist_ok=True)
        ids = subset_ids[s]
        with open(sdir / "questions.jsonl", "wb") as fq, \
             open(sdir / "answers.jsonl", "wb") as fa, \
             open(sdir / "metadata.jsonl", "wb") as fm:
            for iid in ids:
                t = turn_by_id[iid]
                base = {"schema_version": SCHEMA_VERSION, "subset": s,
                        "interaction_id": iid, "dataset_manifest_sha256": manifest_sha}
                fq.write(_jsonl_bytes({**base, "session_id": t["session_id"], "query": t["query"]}))
                fa.write(_jsonl_bytes({**base, "ground_truth": t["ground_truth"]}))
                src = rows_info[t["row_idx"]]
                meta = {
                    **base,
                    "session_id": t["session_id"],
                    "source_interaction_id": t["interaction_id"],
                    "source_dataset": cfg["dataset_id"],
                    "source_split": cfg["split"],
                    "source_revision": cfg["revision"],
                    "turn_index": t["turn_index"],
                    "domain": t["domain"],
                    "query_category": t["query_category"],
                    "image_group_id": (
                        f"img:{src['image_hash'][:16]}" if src["image_hash"]
                        else (f"url:{src['image_url_hash'][:16]}" if src["image_url_hash"] else None)
                    ),
                    "is_egocentric": None,  # 官方无此字段
                    # metadata 额外统计字段
                    "dynamism": t["dynamism"],
                    "image_quality": t["image_quality"],
                    "image_sha256": src["image_hash"],
                    "image_format": src["image_format"],
                    "image_width": src["image_width"],
                    "image_height": src["image_height"],
                }
                fm.write(_jsonl_bytes(meta))

    # 控制台打印统计信息
    print(json.dumps({
        "manifest_sha256": manifest_sha,
        "subset_actual_turns": totals,
        "turns_parsed": len(all_turns),
        "groups": len(group_list),
        "exclusions": dict(counts),
        "elapsed_seconds": round(time.time() - t0, 2),
    }, ensure_ascii=False, indent=2))
    print(f"manifest written: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
