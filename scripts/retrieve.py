#!/usr/bin/env python3
"""C：官方 Web 文本检索与证据导出（m3.v1）。

用法::

    python scripts/retrieve.py \\
        --questions data/processed/m3/smoke/questions.jsonl \\
        --manifest  data/processed/m3/manifest.json \\
        --config    experiments/m3/retrieval.json \\
        --output    results/m3/smoke/evidence.jsonl \\
        [--batch-ids batch.json] [--index-path DIR] [--device auto|cpu|cuda] \\
        [--run-meta PATH] [--no-resume]

约定要点：
  * 输入**只有原始 query**：本程序从不读取 answers.jsonl，也不接触图片、图片 URL、
    OCR、caption、视觉实体、full_query 或对话历史。
  * 每题状态：``ok``（有 hits）/ ``empty``（检索成功但零命中）/ ``error``（技术故障）。
    每个预期 ID 都必有一行；技术故障绝不伪装成 empty，也绝不删题。
  * ``run_id`` 由 (subset, 配置哈希, manifest 哈希) **确定性派生**，不含时间戳：
    同一配置下的所有批次必须共享同一个 run_id，否则合并时会被统一检查器判为 mixed_run。
  * 数据包核对：questions 每行的 ``dataset_manifest_sha256`` 必须等于本次 manifest 的
    原始字节哈希，否则当场失败，不拿错数据包继续跑。
  * 断点续跑：复用前**逐字段严格校验**历史行（字段集合、状态与 hits 的一致性、rank 连续、
    text 非空、score_kind 取值、query 哈希、版本与配置），任何一条不合法就整份另存后重跑。
  * 索引或编码器**初始化失败**时：为每个未完成的预期 ID 写 ``error`` 状态行并照常产出
    run_meta，不留空文件、不丢题目。
  * ``--help`` 不下载索引、不加载模型、不调用任何 API。

退出码：0 = 全部 ok/empty；1 = 结构/编号/哈希/配置错误；2 = 遍历完成但仍有技术失败。
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.contracts.m3 import (  # noqa: E402
    ContractError,
    canonical_json,
    config_sha256,
    file_sha256,
    find_secret_keys,
    load_json,
    parse_json,
    query_sha256,
)
from src.retrieval.text_retrieval import (  # noqa: E402
    SCORE_KINDS,
    ConfigError,
    RetrievalConfig,
    RetrievalError,
    WebTextRetriever,
    prepare_working_copy,
    resolve_index_path,
)

SCHEMA_VERSION = "m3.v1"
SUBSETS = ("smoke", "dev", "eval")

# 历史记录复用前的完整校验：字段集合必须**完全相等**，多一个少一个都不复用
HIT_KEYS = frozenset({"rank", "doc_id", "url", "title", "text", "score", "score_kind"})
EVENT_KEYS = frozenset({
    "schema_version", "subset", "interaction_id", "dataset_manifest_sha256", "query_sha256",
    "run_id", "retrieval_status", "retrieval_config_sha256", "index_revision",
    "encoder_revision", "latency_ms", "error_code", "hits",
})

EXIT_OK = 0
EXIT_STRUCTURAL = 1
EXIT_TECHNICAL = 2


class StructuralError(RuntimeError):
    """配置/编号/哈希不一致：结构性错误，不产出正式结果。"""


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------


class _MEMORY_COUNTERS(ctypes.Structure):
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


def peak_memory_mb() -> float | None:
    """本进程峰值工作集（MB）。非 Windows 或调用失败时返回 None（协议允许 null）。"""
    if os.name != "nt":
        return None
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        k32.GetCurrentProcess.restype = wt.HANDLE
        k32.GetCurrentProcess.argtypes = []
        psapi.GetProcessMemoryInfo.restype = wt.BOOL
        psapi.GetProcessMemoryInfo.argtypes = [
            wt.HANDLE, ctypes.POINTER(_MEMORY_COUNTERS), wt.DWORD
        ]
        counters = _MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            k32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            return None
        return round(counters.PeakWorkingSetSize / 1024**2, 1)
    except Exception:
        return None


def hardware_facts() -> dict[str, Any]:
    """机器简况。取不到就写 null，不猜。"""
    facts: dict[str, Any] = {"platform": sys.platform, "python": sys.version.split()[0]}
    try:
        facts["cpu_logical"] = os.cpu_count()
    except Exception:
        facts["cpu_logical"] = None
    if os.name == "nt":
        try:
            class _MEMSTATUS(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _MEMSTATUS()
            status.dwLength = ctypes.sizeof(_MEMSTATUS)
            if ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(status)):
                facts["ram_total_gb"] = round(status.ullTotalPhys / 1024**3, 2)
                facts["ram_available_gb"] = round(status.ullAvailPhys / 1024**3, 2)
        except Exception:
            facts["ram_total_gb"] = None
    return facts


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _is_number(value: Any) -> bool:
    """真正的数字（bool 不算，避免 True 被当成 score=1）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """严格读取 JSONL：UTF-8、无 BOM、无空行、无 NaN/Infinity、无重复键。"""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StructuralError(f"无法以 UTF-8 读取 {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            raise StructuralError(f"{path} 第 {line_number} 行为空行")
        try:
            value = parse_json(line)
        except ContractError as exc:
            raise StructuralError(f"{path} 第 {line_number} 行不是合法 JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise StructuralError(f"{path} 第 {line_number} 行不是 JSON 对象")
        rows.append(value)
    return rows


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    """原子写入；写完后文件一定是完整、无重复、可直接续跑的状态。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    payload = "".join(canonical_json(row) + "\n" for row in rows)
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def git_commit() -> str:
    """尽力取当前提交；取不到或工作区脏时明确说明（协议要求不得含糊）。"""
    import subprocess

    try:
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=20,
        )
        if head.returncode != 0:
            return "uncommitted:git-unavailable"
        commit = head.stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=20,
        )
        suffix = ":dirty" if dirty.returncode == 0 and dirty.stdout.strip() else ""
        return f"{commit}{suffix}"
    except Exception:
        return "uncommitted:git-unavailable"


# --------------------------------------------------------------------------
# 输入核对
# --------------------------------------------------------------------------


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    """读取 manifest 并返回 (对象, 原始字节 SHA256)。"""
    try:
        manifest = load_json(path)
    except ContractError as exc:
        raise StructuralError(f"manifest 无法解析: {exc}") from exc
    if not isinstance(manifest, dict):
        raise StructuralError("manifest 必须是 JSON 对象")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise StructuralError(f"manifest.schema_version 必须是 {SCHEMA_VERSION!r}")
    revision = manifest.get("revision")
    if not isinstance(revision, str) or not revision.strip():
        raise StructuralError("manifest.revision 缺失")
    if revision.strip().lower() in {"main", "master", "latest", "head"}:
        raise StructuralError("manifest.revision 必须是不可变 commit，不能是 main 之类的移动引用")
    subsets = manifest.get("subsets")
    if not isinstance(subsets, dict) or not all(name in subsets for name in SUBSETS):
        raise StructuralError("manifest.subsets 必须包含 smoke/dev/eval")
    return manifest, file_sha256(path)


def manifest_id_union(manifest: dict[str, Any]) -> list[str]:
    """manifest 三个 subset 的全部 ID——用于判断 questions 是否属于本数据包。"""
    union: list[str] = []
    for name in SUBSETS:
        spec = manifest["subsets"].get(name) or {}
        ids = spec.get("ids")
        if isinstance(ids, list):
            union.extend(item for item in ids if isinstance(item, str) and item)
    return union


def load_questions(
    path: Path, manifest_hash: str, package_ids: list[str]
) -> tuple[str, dict[str, str]]:
    """读取 questions，并核对它来自**同一个数据包**。

    修复点（评审问题 1）：questions 每行都带 ``dataset_manifest_sha256``。旧实现完全忽略它，
    于是拿到别次交付的 questions 也会照着自己的 manifest 哈希一路跑下去，产出"看起来正常"
    但版本错配的证据。现在逐行比对，并拒绝不属于本数据包的 ID。
    """
    rows = read_jsonl(path)
    if not rows:
        raise StructuralError(f"{path} 为空")
    queries: dict[str, str] = {}
    subsets: set[str] = set()
    package = set(package_ids)
    alien: list[str] = []
    for index, row in enumerate(rows, 1):
        ident = row.get("interaction_id")
        query = row.get("query")
        subset = row.get("subset")
        if row.get("schema_version") != SCHEMA_VERSION:
            raise StructuralError(f"{path} 第 {index} 行 schema_version 非法")
        if not isinstance(ident, str) or not ident:
            raise StructuralError(f"{path} 第 {index} 行缺少非空 interaction_id")
        if not isinstance(query, str) or not query.strip():
            raise StructuralError(f"题目 {ident} 的 query 为空")
        if subset not in SUBSETS:
            raise StructuralError(f"题目 {ident} 的 subset 非法: {subset!r}")
        # —— 数据版本核对：拿错数据包必须当场失败 ——
        declared_hash = row.get("dataset_manifest_sha256")
        if declared_hash != manifest_hash:
            raise StructuralError(
                f"数据包不匹配：{path} 第 {index} 行声明的 dataset_manifest_sha256="
                f"{declared_hash!r}，与本机 manifest 的原始字节哈希 {manifest_hash!r} 不一致；"
                "请确认 questions 与 manifest 来自同一次交付"
            )
        if ident in queries:
            raise StructuralError(f"{path} 中 interaction_id 重复: {ident}")
        if ident not in package:
            alien.append(ident)
        queries[ident] = query
        subsets.add(str(subset))
    if alien:
        raise StructuralError(
            f"数据包不匹配：{len(alien)} 个 ID 不在 manifest 清单内（前 5 个）: {sorted(alien)[:5]}"
        )
    if len(subsets) != 1:
        raise StructuralError(f"questions 必须只声明一个 subset，实际 {sorted(subsets)}")
    return next(iter(subsets)), queries


def select_expected(
    manifest: dict[str, Any], subset: str, batch_path: Path | None
) -> tuple[list[str], list[str] | None]:
    """返回 (按 manifest 顺序的预期 ID 列表, 批次 ID 列表或 None)。"""
    declared = manifest["subsets"][subset]
    ids = declared.get("ids")
    count = declared.get("count")
    if not isinstance(ids, list) or not all(isinstance(i, str) and i for i in ids):
        raise StructuralError(f"manifest.subsets.{subset}.ids 非法")
    if isinstance(count, int) and count != len(ids):
        raise StructuralError(f"manifest.subsets.{subset}.count 与 ids 数量不一致")
    if len(set(ids)) != len(ids):
        raise StructuralError(f"manifest.subsets.{subset}.ids 内部重复")

    if batch_path is None:
        return list(ids), None

    try:
        batch = load_json(batch_path)
    except ContractError as exc:
        raise StructuralError(f"batch-ids 无法解析: {exc}") from exc
    if (
        not isinstance(batch, list)
        or not batch
        or any(not isinstance(item, str) or not item for item in batch)
        or len(set(batch)) != len(batch)
    ):
        raise StructuralError("--batch-ids 必须是非空的唯一 ID 字符串数组")
    unknown = sorted(set(batch) - set(ids))
    if unknown:
        # 不跨 subset、不改编号：批次只能取自本 subset 的 manifest 清单
        raise StructuralError(f"--batch-ids 含本 subset 之外的 ID（前 5 个）: {unknown[:5]}")
    wanted = set(batch)
    return [i for i in ids if i in wanted], list(batch)


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise StructuralError(f"config 文件不存在: {path}")
    try:
        config = load_json(path)
    except ContractError as exc:
        raise StructuralError(f"config 无法解析: {exc}") from exc
    if not isinstance(config, dict):
        raise StructuralError("config 必须是 JSON 对象")
    secrets = find_secret_keys(config)
    if secrets:
        # 只报字段路径，绝不回显取值
        raise StructuralError(f"config 内含疑似凭据字段，禁止入库: {secrets}")
    return config


# --------------------------------------------------------------------------
# 续跑：完整校验历史记录
# --------------------------------------------------------------------------


def row_is_sound(row: Any, queries: dict[str, str]) -> bool:
    """一条历史记录是否可以安全复用。

    修复点（评审问题 4）：旧实现只看状态是否 ok/empty 就直接复用，于是一条被截断、
    被手改或结构错乱、但状态写着 ok 的记录会被当成成功结果带进正式产物。
    这里做完整校验：字段集合完全相等、状态与 hits 严格一致、rank 从 1 连续、
    text 非空、score_kind 合法、score 是数字或 null、query 哈希对得上、版本字段齐备。
    """
    if not isinstance(row, dict):
        return False
    if set(row) != EVENT_KEYS:
        return False
    if row.get("schema_version") != SCHEMA_VERSION or row.get("subset") not in SUBSETS:
        return False
    ident = row.get("interaction_id")
    if not isinstance(ident, str) or not ident:
        return False
    if row.get("query_sha256") != query_sha256(queries.get(ident, "")):
        return False
    for field in ("dataset_manifest_sha256", "retrieval_config_sha256",
                  "index_revision", "encoder_revision", "run_id"):
        if not isinstance(row.get(field), str) or not row[field]:
            return False
    for field in ("index_revision", "encoder_revision"):
        if row[field].lower() in {"main", "master", "latest"}:
            return False

    status = row.get("retrieval_status")
    hits = row.get("hits")
    error_code = row.get("error_code")
    if status not in {"ok", "empty", "error"} or not isinstance(hits, list):
        return False
    if status == "ok":
        if not hits or error_code is not None:
            return False
    else:
        if hits:
            return False
        if status == "empty" and error_code is not None:
            return False
        if status == "error" and (not isinstance(error_code, str) or not error_code):
            return False

    for position, hit in enumerate(hits, 1):
        if not isinstance(hit, dict) or set(hit) != HIT_KEYS:
            return False
        if hit.get("rank") != position:
            return False
        if not isinstance(hit.get("doc_id"), str) or not hit["doc_id"]:
            return False
        if not isinstance(hit.get("title"), str):
            return False
        if not isinstance(hit.get("text"), str) or not hit["text"].strip():
            return False
        if hit.get("url") is not None and not isinstance(hit.get("url"), str):
            return False
        if hit.get("score_kind") not in SCORE_KINDS:
            return False
        if hit.get("score") is not None and not _is_number(hit.get("score")):
            return False

    latency = row.get("latency_ms")
    if latency is not None and (not _is_number(latency) or latency < 0):
        return False
    return True


def peek_resume(
    output: Path,
    expected_run_id: str,
    compatible: dict[str, str],
    queries: dict[str, str],
    expected: list[str],
) -> dict[str, dict[str, Any]]:
    """检查已有产物能否续跑；返回可复用行。

    任何一行 run_id 不等于本次确定性 run_id、不属于当前配置/版本、落在 scope 之外，
    或**未通过 row_is_sound 的完整校验**，就把整份文件另存后从头重跑——
    绝不在同一份产物里混用版本，也绝不把可疑记录当成功结果。
    """
    if not output.is_file():
        return {}
    try:
        rows = read_jsonl(output)
    except StructuralError:
        rows = []
    if not rows:
        return {}

    expected_set = set(expected)
    stale = 0
    for row in rows:
        ident = row.get("interaction_id") if isinstance(row, dict) else None
        if (
            not isinstance(row, dict)
            or row.get("run_id") != expected_run_id
            or any(row.get(field) != value for field, value in compatible.items())
            or not isinstance(ident, str)
            or ident not in expected_set
            or not row_is_sound(row, queries)
        ):
            stale += 1

    if stale:
        superseded = output.with_name(f"{output.name}.superseded-{utc_stamp()}")
        os.replace(output, superseded)
        print(f"[resume] {stale} 行未通过一致性/完整性校验，已另存为 {superseded.name}；从头重跑")
        return {}
    return {row["interaction_id"]: row for row in rows}


# --------------------------------------------------------------------------
# 逐题记录
# --------------------------------------------------------------------------


def build_row(
    *,
    subset: str,
    ident: str,
    manifest_hash: str,
    query: str,
    run_id: str,
    config_hash: str,
    index_revision: str,
    encoder_revision: str,
    status: str,
    hits: list[Any],
    latency_ms: float | None,
    error_code: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "subset": subset,
        "interaction_id": ident,
        "dataset_manifest_sha256": manifest_hash,
        "query_sha256": query_sha256(query),
        "run_id": run_id,
        "retrieval_status": status,
        "retrieval_config_sha256": config_hash,
        "index_revision": index_revision,
        "encoder_revision": encoder_revision,
        "latency_ms": None if latency_ms is None else round(float(latency_ms), 3),
        "error_code": error_code,
        "hits": [hit.to_m3() for hit in hits],
    }


def summarize(
    rows: dict[str, dict[str, Any]], expected: list[str]
) -> tuple[dict[str, int], list[float]]:
    counts = {"ok": 0, "empty": 0, "error": 0}
    latencies: list[float] = []
    for ident in expected:
        row = rows.get(ident)
        if row is None:
            continue
        counts[row["retrieval_status"]] += 1
        if _is_number(row.get("latency_ms")):
            latencies.append(float(row["latency_ms"]))
    return counts, latencies


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    result.add_argument("--questions", type=Path, help="questions.jsonl（只含 query 与公共字段）")
    result.add_argument("--manifest", type=Path, help="manifest.json（编号与版本的唯一来源）")
    result.add_argument("--config", type=Path, help="检索配置，例如 experiments/m3/retrieval.json")
    result.add_argument("--output", type=Path, help="evidence.jsonl 输出路径")
    result.add_argument("--batch-ids", type=Path,
                        help="批次 ID 的 JSON 数组；只影响 scope，不改变 manifest 哈希与 run_id")
    result.add_argument("--subset", choices=SUBSETS, help="显式指定 subset；默认由 questions 推断")
    result.add_argument("--index-path", type=Path,
                        help="可写的索引目录（优先于 config.index_cache_dir）；不参与配置哈希")
    result.add_argument("--device", choices=("auto", "cpu", "cuda"),
                        help="覆盖 config.device（会改变配置哈希，生成新的 run）")
    result.add_argument("--run-meta", type=Path,
                        help="run_meta 输出路径；默认写到 evidence 同目录的 run_meta_retrieval.json")
    result.add_argument("--no-resume", action="store_true", help="忽略已有产物，从头重跑")
    result.add_argument("--prepare-working-copy", type=Path, metavar="DEST",
                        help="把固定 revision 的索引快照复制成可写工作副本后退出")
    result.add_argument("--overwrite", action="store_true",
                        help="配合 --prepare-working-copy，允许覆盖已存在的目标目录")
    return result


def run_prepare(args: argparse.Namespace) -> int:
    """一次性准备索引工作副本：不加载编码器，不产出证据。"""
    config = load_config(args.config)
    parsed = RetrievalConfig.from_dict(config)
    print(f"[prepare] 从 HF 快照复制索引到 {args.prepare_working_copy}")
    print(f"[prepare] repo={parsed.index_repo} revision={parsed.index_revision}")
    destination = prepare_working_copy(parsed, args.prepare_working_copy, overwrite=args.overwrite)
    print(f"[prepare] 完成: {destination}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = parser().parse_args(argv)
    if args.prepare_working_copy is not None:
        if args.config is None:
            parser().error("--prepare-working-copy 需要 --config")
        try:
            return run_prepare(args)
        except (StructuralError, ConfigError, RetrievalError, ContractError, OSError) as exc:
            print(f"错误: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_STRUCTURAL

    missing = [name for name in ("questions", "manifest", "config", "output")
               if getattr(args, name) is None]
    if missing:
        parser().error("缺少必需参数: " + ", ".join("--" + name for name in missing))

    started_at = utc_now()
    started_clock = time.perf_counter()
    observed_space: str | None = None
    resolved_device: str | None = None
    warmup_seconds: float | None = None
    index_path: Path | None = None
    retries = 0
    init_error: str | None = None

    try:
        # ============ 阶段 A：结构性核对（本阶段不写任何文件）============
        manifest, manifest_hash = load_manifest(args.manifest)
        package_ids = manifest_id_union(manifest)
        subset, queries = load_questions(args.questions, manifest_hash, package_ids)
        if args.subset and args.subset != subset:
            raise StructuralError(f"--subset={args.subset} 与 questions 声明的 {subset!r} 不一致")
        expected, batch_ids = select_expected(manifest, subset, args.batch_ids)

        absent = [i for i in expected if i not in queries]
        if absent:
            raise StructuralError(
                f"{len(absent)} 个预期 ID 在 questions 中缺失（前 5 个）: {absent[:5]}"
            )

        config = load_config(args.config)
        if args.device:
            config = {**config, "device": args.device}
        if args.index_path is not None:
            config = {**config, "index_cache_dir": str(args.index_path.resolve())}
        parsed = RetrievalConfig.from_dict(config)
        config_hash = config_sha256(config)

        # run_id 不含时间戳：同一 (subset, 配置, manifest) 下的所有批次必须一致，
        # 否则第 3 天把各批次合并成完整 subset 时会被检查器判为 mixed_run。
        run_id = f"retrieval-{subset}-{config_hash[:12]}-{manifest_hash[:8]}"

        compatible = {
            "subset": subset,
            "dataset_manifest_sha256": manifest_hash,
            "retrieval_config_sha256": config_hash,
            "index_revision": parsed.index_revision,
            "encoder_revision": parsed.encoder_revision,
        }

        if args.no_resume and args.output.is_file():
            args.output.unlink()
        resumed_rows = peek_resume(args.output, run_id, compatible, queries, expected)
        if resumed_rows:
            print(f"[resume] 复用 {len(resumed_rows)} 条已完成记录，run_id={run_id}")

        rows: dict[str, dict[str, Any]] = {
            ident: row for ident, row in resumed_rows.items() if ident in set(expected)
        }
        todo = [
            ident for ident in expected
            if rows.get(ident, {}).get("retrieval_status") not in {"ok", "empty"}
        ]

        print(f"[run] subset={subset} scope={'batch' if batch_ids is not None else 'full'} "
              f"expected={len(expected)} done={len(expected) - len(todo)} todo={len(todo)}")
        print(f"[run] run_id={run_id}")
        print(f"[run] config_sha256={config_hash}")

        # ============ 阶段 B：技术阶段（索引/编码器可以失败）============
        retriever: WebTextRetriever | None = None
        if todo:
            try:
                index_path = resolve_index_path(parsed, args.index_path)
                resolved_config = {**config, "index_cache_dir": str(index_path.resolve())}
                if config_sha256(resolved_config) != config_hash:
                    raise StructuralError("索引路径意外影响了配置哈希，拒绝继续")
                config = resolved_config
                retriever = WebTextRetriever(parsed, index_path, device=args.device)
                retriever.load()
            except RetrievalError as exc:
                # 修复点（评审问题 2）：初始化失败也要给**每个**未完成的预期 ID 一条
                # error 状态行，并照常产出 run_meta。绝不留下没有状态行的空文件。
                init_error = type(exc).__name__
                print(f"错误: 检索器初始化失败（{init_error}: {exc}）；"
                      f"将为 {len(todo)} 个预期 ID 写出 error 状态行", file=sys.stderr)
                for ident in todo:
                    rows[ident] = build_row(
                        subset=subset, ident=ident, manifest_hash=manifest_hash,
                        query=queries[ident], run_id=run_id, config_hash=config_hash,
                        index_revision=parsed.index_revision,
                        encoder_revision=parsed.encoder_revision,
                        status="error", hits=[], latency_ms=None, error_code=init_error,
                    )
                retriever = None
            else:
                observed_space = retriever.observed_space
                resolved_device = retriever.device
                print(f"[run] device={resolved_device} observed_space={observed_space} "
                      f"top_k={parsed.top_k}")
                print(f"[run] index={index_path}")

                # 每进程冷启动有两块开销：CUDA kernel 编译，以及 Chroma 首次查询把 HNSW
                # 索引载入内存（本机实测约 25s）。做一次**丢弃式**预热检索，让逐题
                # latency_ms 反映稳定态。预热只用占位字符串：不落盘、不产生状态行、
                # 不参与任何证据，也不读取任何题目或参考答案。
                warm_clock = time.perf_counter()
                try:
                    retriever.search("warmup probe (discarded)")
                except RetrievalError as exc:
                    print(f"警告: 预热失败 {type(exc).__name__}；首题耗时会偏高", file=sys.stderr)
                warmup_seconds = round(time.perf_counter() - warm_clock, 3)
                print(f"[run] warmup={warmup_seconds}s（冷启动，已排除在逐题耗时之外）")
                try:
                    for position, ident in enumerate(todo, 1):
                        query = queries[ident]
                        attempt = 0
                        row: dict[str, Any]
                        while True:
                            attempt += 1
                            clock = time.perf_counter()
                            try:
                                hits = retriever.search(query)
                                latency = (time.perf_counter() - clock) * 1000.0
                                row = build_row(
                                    subset=subset, ident=ident, manifest_hash=manifest_hash,
                                    query=query, run_id=run_id, config_hash=config_hash,
                                    index_revision=parsed.index_revision,
                                    encoder_revision=parsed.encoder_revision,
                                    status="ok" if hits else "empty",
                                    hits=hits, latency_ms=latency, error_code=None,
                                )
                            except RetrievalError as exc:
                                latency = (time.perf_counter() - clock) * 1000.0
                                if attempt <= parsed.retry_max:
                                    retries += 1
                                    time.sleep(min(2 ** (attempt - 1), 8))
                                    continue
                                row = build_row(
                                    subset=subset, ident=ident, manifest_hash=manifest_hash,
                                    query=query, run_id=run_id, config_hash=config_hash,
                                    index_revision=parsed.index_revision,
                                    encoder_revision=parsed.encoder_revision,
                                    status="error", hits=[], latency_ms=latency,
                                    error_code=type(exc).__name__,
                                )
                            rows[ident] = row
                            break
                        # 逐题落盘：中断后已完成的题目不会丢
                        write_jsonl_atomic(
                            args.output, [rows[i] for i in expected if i in rows]
                        )
                        print(f"  [{position}/{len(todo)}] {ident} -> {row['retrieval_status']} "
                              f"hits={len(row['hits'])} {row['latency_ms']}ms", flush=True)
                finally:
                    if retriever is not None:
                        retriever.close()
        else:
            print("[run] 无需检索，全部记录已存在")

        # ============ 阶段 C：收尾（正常与初始化失败都要走到）============
        final_rows = [rows[i] for i in expected if i in rows]
        write_jsonl_atomic(args.output, final_rows)

        counts, latencies = summarize(rows, expected)
        n_success = counts["ok"] + counts["empty"]
        n_failed = counts["error"]

        run_meta_path = args.run_meta or args.output.with_name("run_meta_retrieval.json")
        run_meta: dict[str, Any] = {
            "run_id": run_id,
            "stage": "retrieval",
            "subset": subset,
            "schema_version": SCHEMA_VERSION,
            "code_commit": git_commit(),
            "code_files_sha256": {
                "scripts/retrieve.py": file_sha256(Path(__file__).resolve()),
                "src/retrieval/text_retrieval.py":
                    file_sha256(ROOT / "src" / "retrieval" / "text_retrieval.py"),
                "src/contracts/m3.py": file_sha256(ROOT / "src" / "contracts" / "m3.py"),
            },
            "input_files_sha256": {
                str(args.manifest.resolve()): manifest_hash,
                str(args.questions.resolve()): file_sha256(args.questions),
            },
            "output_files_sha256": {str(args.output.resolve()): file_sha256(args.output)},
            "config": config,
            "config_sha256": config_hash,
            "started_at": started_at,
            "finished_at": utc_now(),
            "hardware": hardware_facts(),
            "N_expected": len(expected),
            "N_success": n_success,
            "N_failed": n_failed,
            "retries": retries,
            "peak_memory_mb": peak_memory_mb(),
            "index_path": config.get("index_cache_dir"),
            "index_collection": parsed.collection_name,
            "index_space_observed": observed_space,
            "device_resolved": resolved_device,
            "warmup_seconds_excluded_from_latency": warmup_seconds,
            "initialization_error": init_error,
            "top_k": parsed.top_k,
            "counts_by_status": counts,
            "latency_ms_mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "latency_ms_max": round(max(latencies), 3) if latencies else None,
            "wall_seconds": round(time.perf_counter() - started_clock, 3),
            "notes": (
                "输入只有原始 query；从未读取 answers.jsonl；"
                "score = 1 - distance，集合空间为 cosine 故等价于余弦相似度；"
                "按 _chunk 前缀先页面去重再截断，故 hits 条数可能少于 top_k；"
                "run_id 由 (subset, 配置哈希, manifest 哈希) 确定性派生，批次间共享"
            ),
        }
        if batch_ids is not None:
            run_meta["batch_ids"] = sorted(batch_ids)
        run_meta_path.parent.mkdir(parents=True, exist_ok=True)
        run_meta_path.write_text(
            json.dumps(run_meta, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

        print(f"\n[summary] N_expected={len(expected)} N_success={n_success} "
              f"N_failed={n_failed} retries={retries}")
        print(f"[summary] status={counts} 覆盖率={n_success}/{len(expected)}")
        if latencies:
            print(f"[summary] latency mean={run_meta['latency_ms_mean']}ms "
                  f"max={run_meta['latency_ms_max']}ms")
        print(f"[summary] evidence -> {args.output}")
        print(f"[summary] run_meta -> {run_meta_path}")

        if n_failed:
            reason = f"（初始化失败: {init_error}）" if init_error else ""
            print(f"警告: {n_failed} 题存在技术故障{reason}，已保留完整状态行与 run_meta",
                  file=sys.stderr)
            return EXIT_TECHNICAL
        return EXIT_OK

    except (StructuralError, ConfigError, ContractError, OSError) as exc:
        print(f"错误: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_STRUCTURAL
    except KeyboardInterrupt:
        print("已中断；已完成的题目已逐题落盘，可直接重跑续跑。", file=sys.stderr)
        return EXIT_STRUCTURAL


if __name__ == "__main__":
    raise SystemExit(main())
