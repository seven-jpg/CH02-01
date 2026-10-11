#!/usr/bin/env python3
"""Create a read-only D demo from questions, evidence, predictions and optional scores.

This script never calls a provider and never reads answers.jsonl. It is intended
for a reproducible classroom demo, not for scoring or experiment generation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def rows(path: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            result[row["interaction_id"]] = row
    return result


def esc(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--questions", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--predictions-b0", type=Path, required=True)
    p.add_argument("--predictions-b1", type=Path, required=True)
    p.add_argument("--scores-b0", type=Path)
    p.add_argument("--scores-b1", type=Path)
    p.add_argument("--ids", nargs="+", help="IDs to show; default is the first three questions")
    p.add_argument("--output", type=Path, required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    questions = rows(args.questions)
    evidence = rows(args.evidence)
    b0 = rows(args.predictions_b0)
    b1 = rows(args.predictions_b1)
    scores0 = rows(args.scores_b0) if args.scores_b0 else {}
    scores1 = rows(args.scores_b1) if args.scores_b1 else {}
    ids = args.ids or list(questions)[:3]
    missing = [ident for ident in ids if ident not in questions or ident not in evidence or ident not in b0 or ident not in b1]
    if missing:
        raise SystemExit(f"Missing demo IDs or artifacts: {missing}")
    lines = ["# D 生成演示", "", "本演示只读取 questions、evidence、predictions 和可选 scores，不调用模型、不读取 answers。", ""]
    for number, ident in enumerate(ids, 1):
        q = questions[ident]
        ev = evidence[ident]
        r0 = b0[ident]
        r1 = b1[ident]
        s0 = scores0.get(ident, {})
        s1 = scores1.get(ident, {})
        lines.extend([
            f"## 案例 {number}: `{ident}`", "",
            f"- Query：{esc(q['query'])}",
            f"- Evidence status：`{ev.get('retrieval_status')}`；命中数：`{len(ev.get('hits', []))}`",
        ])
        for hit in ev.get("hits", [])[:3]:
            lines.append(f"- 来源：{esc(hit.get('title'))}；URL：{esc(hit.get('url'))}")
        lines.extend([
            "", "| 项目 | B0 | B1 |", "|---|---|---|",
            f"| 回答 | {esc(r0.get('agent_response'))} | {esc(r1.get('agent_response'))} |",
            f"| 状态 | `{r0.get('generation_status')}` | `{r1.get('generation_status')}` |",
            f"| 输入 tokens | {r0.get('usage', {}).get('input_tokens')} | {r1.get('usage', {}).get('input_tokens')} |",
            f"| 输出 tokens | {r0.get('usage', {}).get('output_tokens')} | {r1.get('usage', {}).get('output_tokens')} |",
        ])
        if s0 or s1:
            lines.append(f"| 评分 | {esc(s0.get('verdict', '未提供'))} | {esc(s1.get('verdict', '未提供'))} |")
        lines.append("")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
