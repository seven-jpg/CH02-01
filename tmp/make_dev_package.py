"""生成 tmp 下的**开发用**小样本，用于端到端自测。

⚠️ 这不是正式数据：questions 是自拟的普通事实问句，只为验证
   CLI / schema / 状态行 / run_meta 是否合规。绝不放进 data/processed/m3
   或 results/m3，也不得当作 smoke 证据。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "tmp" / "dev"
SUBSET = "smoke"
MANIFEST_REVISION = "0123456789abcdef0123456789abcdef01234567"  # 仅占位，格式合法
DATASET_ID = "dev-only/not-official-not-for-results"

QUESTIONS = [
    ("dev-001", "sess-dev", "What is the capital of France?", "Paris"),
    ("dev-002", "sess-dev", "Who wrote the novel Pride and Prejudice?", "Jane Austen"),
    ("dev-003", "sess-dev", "What is the tallest mountain in the world?", "Mount Everest"),
]


def dump_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "m3.v1",
        "data_origin": "official",
        "dataset_id": DATASET_ID,
        "revision": MANIFEST_REVISION,
        "split": "validation",
        "seed": 42,
        "grouping": "dev placeholder",
        "id_rule": "dev-### sequential, development self-test only",
        "subsets": {
            "smoke": {"ids": [q[0] for q in QUESTIONS], "count": len(QUESTIONS)},
            "dev": {"ids": [], "count": 0},
            "eval": {"ids": [], "count": 0},
        },
        "fixture_notice": "DEVELOPMENT SELF-TEST ONLY: 自拟问句，非官方数据，不是正式证据",
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    print(f"manifest sha256 = {manifest_hash}")

    common = {"schema_version": "m3.v1", "subset": SUBSET,
              "dataset_manifest_sha256": manifest_hash}

    dump_jsonl(OUT / "questions.jsonl", [
        {**common, "interaction_id": ident, "session_id": session, "query": query}
        for ident, session, query, _ in QUESTIONS
    ])
    dump_jsonl(OUT / "answers.jsonl", [
        {**common, "interaction_id": ident, "ground_truth": answer}
        for ident, _, _, answer in QUESTIONS
    ])
    dump_jsonl(OUT / "metadata.jsonl", [
        {**common, "interaction_id": ident, "session_id": session,
         "source_interaction_id": ident, "source_dataset": DATASET_ID,
         "source_split": "validation", "source_revision": MANIFEST_REVISION,
         "turn_index": 0, "domain": None, "query_category": None,
         "image_group_id": None, "is_egocentric": None}
        for ident, session, _, _ in QUESTIONS
    ])
    print(f"已写出开发小样本到 {OUT}")


if __name__ == "__main__":
    main()
