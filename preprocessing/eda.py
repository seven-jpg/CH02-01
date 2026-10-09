"""B 岗位正式交付物：M2 数据 EDA（Single-turn 与 Multi-turn 两类 QA）。

对 config["eda"]["datasets"] 中每个数据集做只读统计：
    - 规模与结构：session 数、turn 数、去重图像数、每会话轮数分布
    - 标签分布：领域、题型、动态性、图像质量（经官方 ClassLabel 词表解码）
    - 文本：query 与答案长度（字符），含超 75-token 估计线的答案占比
    - 图像：来源（内嵌/URL）、尺寸与长宽比、亮度与清晰度代理指标（含与官方质量标签的对照）
    - 数据质量：重复（ID/query 文本/图像）、缺失答案、加载失败的计数与排除规则
    - 多轮专属：跨轮内容复用率与句首指代率
输出：
    <output-dir>/eda_report.json            统计报告（正式交付）
    <output-dir>/charts/<name>_*.png        图表（正式交付）

CLI：
    python preprocessing/eda.py --config experiments/m3/data.json --output-dir results/eda
    可选 --offline（只用本地缓存，不访问网络；本机数据已缓存时推荐）

规则与限制：
    - revision 必须是不可变 commit SHA（config 中写死）
    - 分批读图：逐行处理，图像用完即释放，不同时解码全部图片（16GB RAM）
    - image_quality 取自 turns 列（顶层没有）；标签经官方 ClassLabel names 解码，不写死数字
    - 亮度 = 灰度图均值（0-255）；清晰度 = 拉普拉斯卷积方差（代理指标，非官方标签，公式在此注明）
    - EDA 只统计不筛选：缺失答案/空 query/无 ID 计数报告，不排除
    - 外链图（仅 image_url）不下载，其亮度/清晰度/尺寸不统计，来源记 url_only
    - --help 不下载数据、不加载模型
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # 无显示环境，仅存图

REPO_ROOT = Path(__file__).resolve().parents[1]  # 仓库根目录，不写死盘符
sys.path.insert(0, str(REPO_ROOT))  # 从仓库根运行时也能 import preprocessing 包

# 图表样式（dataviz 规范：单一蓝色阶、细条形、浅色表面、弱网格；标签全英文避免中文字体问题）
SERIES_HUE = "#2a78d6"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"


def _label_names(features: Any) -> dict[str, list[str] | None]:
    """从 features 提取官方标签词表（支持 ClassLabel 与 List(ClassLabel)）。"""
    names: dict[str, list[str] | None] = {}
    turns_feat = features.get("turns")
    if isinstance(turns_feat, dict):
        for k in ("domain", "query_category", "dynamism", "image_quality"):
            feat = turns_feat.get(k)
            if feat is not None and hasattr(feat, "names"):
                names[k] = list(feat.names)
            elif feat is not None and hasattr(feat, "feature") and hasattr(feat.feature, "names"):
                names[k] = list(feat.feature.names)
            else:
                names[k] = None
    else:
        names = {k: None for k in ("domain", "query_category", "dynamism", "image_quality")}
    return names


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _image_proxies(img: Any) -> dict[str, float | None]:
    """亮度（灰度均值）与清晰度（拉普拉斯方差）代理指标；失败返回 None。"""
    from PIL import ImageFilter
    import numpy as np

    try:
        gray = img.convert("L")
        brightness = float(np.asarray(gray, dtype=np.float64).mean())
        lap = gray.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1))
        sharpness = float(np.asarray(lap, dtype=np.float64).var())
        return {"brightness": brightness, "sharpness": sharpness}
    except Exception:
        return {"brightness": None, "sharpness": None}


def _barchart(counter: Counter, path: Path, title: str, xlabel: str,
              order: list[str] | None = None, emphasis: str | None = None) -> None:
    """水平条形图：单一蓝色、细条形、直接标值。默认按数量降序；order 给定时按给定语义顺序。
    emphasis 给定时该标签用蓝、其余用灰（强调式：normal 作为参照组）。"""
    import matplotlib.pyplot as plt

    if not counter:
        return
    if order is not None:
        items = [(l, counter.get(l, 0)) for l in order if counter.get(l)]
        items += sorted(((k, v) for k, v in counter.items() if k not in order), key=lambda kv: -kv[1])
    else:
        items = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)
    labels, values = zip(*items)
    labels = [str(l) for l in labels]
    fig, ax = plt.subplots(figsize=(7, max(2.4, 0.32 * len(items))))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    y = list(range(len(items)))[::-1]
    colors = [SERIES_HUE if emphasis is None or l == emphasis else "#c3c2b7" for l in labels]
    bars = ax.barh(y, values, height=0.62, color=colors)
    for bar, v in zip(bars, values):
        ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                str(v), va="center", ha="left", fontsize=9, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9, color=INK)
    ax.set_xlabel(xlabel, fontsize=9, color=INK)
    fig.suptitle(title, fontsize=11, color=INK, y=0.95)
    ax.tick_params(axis="x", colors=INK, labelsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def _histogram(values: list[float], path: Path, title: str, xlabel: str, bins: int = 30) -> None:
    """直方图：单一蓝色阶（由浅入深）。"""
    import matplotlib.pyplot as plt

    if not values:
        return
    fig, ax = plt.subplots(figsize=(7, 3.2))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.hist(values, bins=bins, color=SERIES_HUE, alpha=0.9, edgecolor=SURFACE, linewidth=0.5)
    ax.set_xlabel(xlabel, fontsize=9, color=INK)
    ax.set_ylabel("count", fontsize=9, color=INK)
    fig.suptitle(title, fontsize=11, color=INK, y=0.95)
    ax.tick_params(colors=INK, labelsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def _stats(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {"n": len(xs), "mean": round(statistics.fmean(xs), 2),
            "median": round(statistics.median(xs), 2), "min": min(xs), "max": max(xs)}


STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "do", "does", "did",
    "has", "have", "had", "of", "in", "on", "at", "to", "for", "with", "this", "that",
    "it", "its", "these", "those", "what", "when", "where", "who", "why", "how",
    "can", "could", "should", "would", "and", "or", "but", "not", "no", "yes",
    "there", "here", "from", "by", "as", "if", "then", "than", "so", "many", "much",
}

REFERENCE_OPENERS = {"this", "that", "it", "the", "these", "those"}


def _content_words(text: str) -> set[str]:
    """内容词集合：小写化、去停用词、长度>=3 的纯字母词（无 nltk 依赖）。"""
    import re
    return {w for w in re.findall(r"[a-z]+", str(text).lower())
            if len(w) >= 3 and w not in STOPWORDS}


def _opener_referent(text: str) -> bool:
    """query 是否以指代词/定冠词开头（词法代理：指图式措辞的对照指标）。"""
    import re
    m = re.match(r"[^a-z]*([a-z]+)", str(text).lower())
    return bool(m and m.group(1) in REFERENCE_OPENERS)


def _histogram_with_threshold(values: list[float], threshold: float, path: Path,
                              title: str, xlabel: str, bins: int = 30) -> None:
    """带参考线的直方图：虚线标出阈值并标注超线占比。"""
    import matplotlib.pyplot as plt

    if not values:
        return
    over = sum(1 for v in values if v > threshold)
    frac = over / len(values)
    fig, ax = plt.subplots(figsize=(7, 3.2))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.hist(values, bins=bins, color=SERIES_HUE, alpha=0.9, edgecolor=SURFACE, linewidth=0.5)
    ax.axvline(threshold, color="#d03b3b", linewidth=1.2, linestyle="--")
    ymax = ax.get_ylim()[1]
    ax.text(threshold + max(values) * 0.02, ymax * 0.92,
            f"{frac:.1%} > {int(threshold)} chars\n(est. 75 tokens @ 4 chars/token)",
            color="#d03b3b", fontsize=9, va="top")
    ax.set_xlabel(xlabel, fontsize=9, color=INK)
    ax.set_ylabel("count", fontsize=9, color=INK)
    fig.suptitle(title, fontsize=10, color=INK, y=0.95)
    ax.tick_params(colors=INK, labelsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def _line_chart(points: dict[int, float], path: Path, title: str,
                xlabel: str, ylabel: str) -> None:
    """折线图：单序列蓝色、点标注百分比、y 轴 0-100%。"""
    import matplotlib.pyplot as plt

    xs = sorted(points)
    ys = [points[x] for x in xs]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.plot(xs, ys, color=SERIES_HUE, linewidth=2, marker="o", markersize=6)
    for x, y in zip(xs, ys):
        ax.annotate(f"{y:.1%}", (x, y), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=9, color=INK)
    ax.set_xlabel(xlabel, fontsize=9, color=INK)
    ax.set_ylabel(ylabel, fontsize=9, color=INK)
    fig.suptitle(title, fontsize=10, color=INK, y=0.95)
    ax.set_xticks(xs)  # 固定刻度为真实轮次（2,3,4,5,6），避免出现 0.5 步进
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.tick_params(colors=INK, labelsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def analyze_dataset(cfg_entry: dict, chart_dir: Path) -> dict[str, Any]:
    """对一个数据集跑完整 EDA，返回统计字典。图表写入 chart_dir。"""
    from datasets import load_dataset
    from preprocessing.prepare_data import extract_row_turns

    name = cfg_entry["name"]
    dname = "Single-turn" if name == "single-turn" else "Multi-turn"
    ds = load_dataset(cfg_entry["dataset_id"], revision=cfg_entry["revision"])
    split = ds[cfg_entry["split"]]
    label_names = _label_names(split.features)

    t0 = time.time()
    n_sessions = 0
    n_turns_total = 0
    turns_per_session: list[int] = []
    dom_counter: Counter = Counter()
    cat_counter: Counter = Counter()
    dyn_counter: Counter = Counter()
    qual_counter: Counter = Counter()
    query_lens: list[int] = []
    answer_lens: list[int] = []
    img_sources: Counter = Counter()
    img_hash_counter: Counter = Counter()
    id_counter: Counter = Counter()
    qtext_counter: Counter = Counter()
    img_widths: list[int] = []
    img_heights: list[int] = []
    brightness: list[float] = []
    sharpness: list[float] = []
    exclusions: Counter = Counter()
    load_failures: Counter = Counter()
    opener_count = 0
    mt_t1_total, mt_t1_openers = 0, 0
    mt_later_total, mt_later_openers = 0, 0
    session_histories: list[list[tuple[str, str]]] = []
    proxy_by_quality: dict[str, list[tuple[float, float]]] = {}

    for row in split:
        try:
            turns, lookup, _ = extract_row_turns(row, label_names)
        except Exception:
            load_failures["row_parse_error"] += 1
            continue
        n_sessions += 1
        n_turns_total += len(turns)
        turns_per_session.append(len(turns))
        hist: list[tuple[str, str]] = []
        for ti, t in enumerate(turns):
            iid = str(t["interaction_id"]) if t.get("interaction_id") is not None else None
            q = t.get("query")
            gt = lookup.get(iid) if iid is not None else None
            if iid is None:
                exclusions["turn_no_interaction_id"] += 1
            if q is None or not str(q).strip():
                exclusions["empty_query"] += 1
            if gt is None or not str(gt).strip():
                exclusions["missing_answer"] += 1
            if iid is not None:
                id_counter[iid] += 1
            if q:
                qtext_counter[str(q)] += 1
            dom_counter[t.get("domain")] += 1
            cat_counter[t.get("query_category")] += 1
            dyn_counter[t.get("dynamism")] += 1
            qual_counter[t.get("image_quality")] += 1
            if q:
                query_lens.append(len(str(q)))
                if _opener_referent(str(q)):
                    opener_count += 1
                if name == "multi-turn":
                    if ti == 0:
                        mt_t1_total += 1
                        if _opener_referent(str(q)):
                            mt_t1_openers += 1
                    else:
                        mt_later_total += 1
                        if _opener_referent(str(q)):
                            mt_later_openers += 1
            if gt:
                answer_lens.append(len(str(gt)))
            hist.append((str(q) if q else "", str(gt) if gt else ""))
        session_histories.append(hist)
        img = row.get("image")
        url = row.get("image_url")
        if img is not None:
            img_sources["embedded"] += 1
            try:
                img_widths.append(img.size[0])
                img_heights.append(img.size[1])
                img_hash_counter[_sha256(img.tobytes())] += 1
                p = _image_proxies(img)
                if p["brightness"] is not None:
                    brightness.append(p["brightness"])
                    sharpness.append(p["sharpness"])
                    qlabel = turns[0].get("image_quality") if turns else None
                    proxy_by_quality.setdefault(qlabel, []).append((p["brightness"], p["sharpness"]))
                else:
                    exclusions["proxy_failed"] += 1
            except Exception:
                load_failures["image_hash_error"] += 1
        elif isinstance(url, str) and url:
            img_sources["url_only"] += 1
        else:
            img_sources["none"] += 1
        # 图像随循环作用域释放，不驻留内存

    # 跨轮内容复用：后续轮 query 的内容词有多少来自前几轮（query 或 answer）
    reuse_num: Counter = Counter()
    turn_den: Counter = Counter()
    for hist in session_histories:
        seen: set[str] = set()
        for idx, (q, a) in enumerate(hist):
            cw = _content_words(q)
            if idx >= 1:
                turn_den[idx] += 1
                if cw & seen:
                    reuse_num[idx] += 1
            seen |= cw | _content_words(a)
    reuse_by_turn = {k + 1: reuse_num[k] / turn_den[k] for k in sorted(turn_den)}  # 1 基：真实轮次 2~6
    reuse_overall = sum(reuse_num.values()) / sum(turn_den.values()) if sum(turn_den.values()) else None
    over_75 = sum(1 for x in answer_lens if x > 300)

    chart_name = name
    _barchart(dom_counter, chart_dir / f"{chart_name}_domain.png",
              f"{dname} Validation - Domain Distribution", "turns")
    _barchart(cat_counter, chart_dir / f"{chart_name}_query_category.png",
              f"{dname} Validation - Query Category Distribution", "turns")
    _barchart(qual_counter, chart_dir / f"{chart_name}_image_quality.png",
              f"{dname} Validation - Image Quality Distribution (from Turns)", "turns",
              order=["normal", "low light", "blurred", "occluded", "rotated", "truncated"])
    _barchart(dyn_counter, chart_dir / f"{chart_name}_dynamism.png",
              f"{dname} Validation - Dynamism Distribution", "turns")
    _histogram([float(v) for v in query_lens], chart_dir / f"{chart_name}_query_len.png",
               f"{dname} Validation - Query Length (Chars)", "chars")
    _histogram_with_threshold([float(v) for v in answer_lens], 300,
                              chart_dir / f"{chart_name}_answer_len.png",
                              f"{dname} Validation - Answer Length (Chars; dashed = est. 75 tokens)",
                              "chars")
    if name == "multi-turn":  # 单轮数据集每会话恒为 1 轮，画图无信息量
        turn_counter = Counter(int(v) for v in turns_per_session)
        _barchart(turn_counter, chart_dir / f"{chart_name}_turns_per_session.png",
                  f"{dname} Validation - Turns per Session", "sessions",
                  order=["2", "3", "4", "5", "6"])
    if img_widths:
        # 尺寸恒定（3024x4032）时直方图无信息量，仅报告数值，不画图
        _histogram([float(v) for v in brightness], chart_dir / f"{chart_name}_brightness.png",
                   f"{dname} Validation - Brightness (Grayscale Mean, 0-255)", "mean gray value")
        _histogram([math.log10(float(v)) for v in sharpness], chart_dir / f"{chart_name}_sharpness.png",
                   f"{dname} Validation - Sharpness (log10 Laplacian Variance)", "log10 variance")
    if proxy_by_quality:  # 代理指标 × 官方质量标签对照（normal 为参照组，蓝色；退化标签灰色）
        qorder = ["normal", "low light", "blurred", "occluded", "rotated", "truncated"]
        _barchart(Counter({k: round(statistics.median([x[0] for x in v]), 1)
                           for k, v in proxy_by_quality.items()}),
                  chart_dir / f"{chart_name}_proxy_brightness_by_quality.png",
                  f"{dname} Validation - Median Brightness by Official Quality Label",
                  "median gray value", order=qorder, emphasis="normal")
        _barchart(Counter({k: round(statistics.median([x[1] for x in v]), 1)
                           for k, v in proxy_by_quality.items()}),
                  chart_dir / f"{chart_name}_proxy_sharpness_by_quality.png",
                  f"{dname} Validation - Median Sharpness by Official Quality Label",
                  "median Laplacian variance", order=qorder, emphasis="normal")

    result = {
        "name": name,
        "dataset_id": cfg_entry["dataset_id"],
        "revision": cfg_entry["revision"],
        "split": cfg_entry["split"],
        "actual_splits_in_dataset": list(ds.keys()),
        "sessions": n_sessions,
        "turns_total": n_turns_total,
        "turns_per_session_stats": _stats([float(v) for v in turns_per_session]),
        "turns_per_session_distribution": {str(k): v for k, v in sorted(Counter(turns_per_session).items())},
        "unique_images": {"embedded_sha256_distinct": len(img_hash_counter), "url_only": img_sources["url_only"]},
        "duplicates": {
            "duplicate_interaction_ids": sum(1 for v in id_counter.values() if v > 1),
            "duplicate_query_texts": sum(1 for v in qtext_counter.values() if v > 1),
            "image_dup_group_sizes": {str(k): v for k, v in sorted(Counter(img_hash_counter.values()).items()) if k > 1},
        },
        "image_source_counts": dict(img_sources),
        "distributions": {
            "domain": {str(k): v for k, v in sorted(dom_counter.items(), key=lambda kv: -kv[1])},
            "query_category": {str(k): v for k, v in sorted(cat_counter.items(), key=lambda kv: -kv[1])},
            "dynamism": {str(k): v for k, v in sorted(dyn_counter.items(), key=lambda kv: -kv[1])},
            "image_quality": {str(k): v for k, v in sorted(qual_counter.items(), key=lambda kv: -kv[1])},
        },
        "query_len_chars": _stats([float(v) for v in query_lens]),
        "answer_len_chars": _stats([float(v) for v in answer_lens]),
        "image_size_px": {"width": _stats([float(v) for v in img_widths]),
                          "height": _stats([float(v) for v in img_heights]),
                          "aspect_ratio_mean": (round(statistics.fmean(img_widths) / statistics.fmean(img_heights), 4)
                                                if img_widths else None)},
        "brightness_proxy": _stats(brightness),
        "sharpness_proxy": _stats(sharpness),
        "exclusion_counts": dict(exclusions),
        "load_failures": dict(load_failures),
        "elapsed_seconds": round(time.time() - t0, 2),
        "opener_reference_rate": round(opener_count / len(query_lens), 4) if query_lens else None,
        "answer_over_75token_estimate": {
            "n": over_75,
            "fraction": round(over_75 / len(answer_lens), 4) if answer_lens else None,
            "rule": "chars / 4 approx tokens; threshold = 300 chars",
        },
        "proxy_by_quality": {
            str(k): {
                "n": len(v),
                "brightness_median": round(statistics.median([x[0] for x in v]), 2),
                "brightness_mean": round(statistics.fmean([x[0] for x in v]), 2),
                "sharpness_median": round(statistics.median([x[1] for x in v]), 2),
                "sharpness_mean": round(statistics.fmean([x[1] for x in v]), 2),
            }
            for k, v in proxy_by_quality.items()
        },
    }
    if name == "multi-turn":
        result["turn1_opener_rate"] = round(mt_t1_openers / mt_t1_total, 4) if mt_t1_total else None
        result["later_opener_rate"] = round(mt_later_openers / mt_later_total, 4) if mt_later_total else None
        result["history_reuse_by_turn"] = {str(k): round(v, 4) for k, v in reuse_by_turn.items()}
        result["history_reuse_overall"] = round(reuse_overall, 4) if reuse_overall is not None else None
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="B 的数据配置文件（JSON）")
    parser.add_argument("--output-dir", required=True, help="输出目录，如 results/eda（相对仓库根）")
    parser.add_argument("--offline", action="store_true",
                        help="只用本地缓存（HF_HUB_OFFLINE=1），不访问网络；数据未缓存时会直接报错")
    args = parser.parse_args(argv)

    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"

    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = REPO_ROOT / cfg_path
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    eda_cfg = cfg.get("eda") or {}
    datasets = eda_cfg.get("datasets") or []
    if not datasets:
        print("ERROR: config[\"eda\"][\"datasets\"] is empty", file=sys.stderr)
        return 1
    for entry in datasets:
        if not all(k in entry for k in ("name", "dataset_id", "revision", "split")):
            print(f"ERROR: bad eda dataset entry: {entry}", file=sys.stderr)
            return 1
        if not (isinstance(entry["revision"], str) and len(entry["revision"]) == 40):
            print(f"ERROR: eda revision must be an immutable 40-char commit SHA: {entry['revision']!r}",
                  file=sys.stderr)
            return 1

    out_root = Path(args.output_dir)
    if not out_root.is_absolute():
        out_root = REPO_ROOT / out_root
    chart_dir = out_root / "charts"
    out_root.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for entry in datasets:
        print(f"analyzing {entry['name']} @ {entry['revision'][:10]} ...")
        results[entry["name"]] = analyze_dataset(entry, chart_dir)
        print(json.dumps({
            "sessions": results[entry["name"]]["sessions"],
            "turns_total": results[entry["name"]]["turns_total"],
            "image_source_counts": results[entry["name"]]["image_source_counts"],
            "exclusions": results[entry["name"]]["exclusion_counts"],
            "elapsed_seconds": results[entry["name"]]["elapsed_seconds"],
        }, ensure_ascii=False))

    # 多轮跨轮内容复用率折线
    mt = results.get("multi-turn")
    if mt and mt.get("history_reuse_by_turn"):
        _line_chart({int(k): v for k, v in mt["history_reuse_by_turn"].items()},
                    chart_dir / "multi_turn_history_reuse.png",
                    "Multi-turn Validation - Cross-turn Content Reuse Rate (later queries reusing earlier words)",
                    "turn index", "reuse rate")

    report = {
        "schema_version": "m3.v1",
        "checked_date": time.strftime("%Y-%m-%d"),
        "analysis_scope": "M2 EDA over official validation splits, pinned revisions; stats only, no sampling",
        "datasets": results,
        "proxies_note": {
            "brightness": "mean of grayscale (0-255); embedded images only, url_only images not downloaded",
            "sharpness": "variance of 3x3 Laplacian kernel convolution on grayscale; embedded images only; chart uses log10 scale",
            "thresholds": "none defined: proxies are continuous indicators, compared with official labels only (C3); no cutoff applied",
            "status": "proxy metrics, NOT official labels",
        },
        "exclusion_rules": {
            "turn_no_interaction_id": "turn has no interaction_id; counted, not filtered",
            "empty_query": "query is empty or whitespace-only; counted, not filtered",
            "missing_answer": "no ans_full matched by interaction_id, or ans_full is blank; counted, not filtered",
            "proxy_failed": "embedded image failed brightness/sharpness computation",
            "image_hash_error": "embedded image failed SHA256 hashing",
            "row_parse_error": "row failed turn/answer extraction",
            "note": "EDA does not exclude rows: it only counts these conditions (no filtering)",
        },
        "limitations": [
            "url_only images not downloaded: size/brightness/sharpness not measured for them",
            "unique-image count is byte-level SHA256 over embedded images; url_only counted by URL presence only",
            "EDA counts missing answers/empty queries but does not exclude rows (no filtering)",
            "history reuse (C1) is a lexical proxy: stopword-filtered word overlap with earlier turns; not a semantic judgement",
            "opener reference rate (C1) is a lexical proxy: leading this/that/it/the/these/those; image-referential phrasing baseline",
            "answer over-75-token estimate (C2) uses chars/4 rule; official tokenizer belongs to E, not measured here",
        ],
    }
    report_path = out_root / "eda_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"report written: {report_path}")
    print(f"charts written: {chart_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
