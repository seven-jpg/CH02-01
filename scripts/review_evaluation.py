#!/usr/bin/env python3
"""E offline suite, manual review import and completed-score comparisons. Never calls a judge."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    suite = sub.add_parser("prepare", help="Validate all six existing groups, deduplicate, sample a blinded review")
    suite.add_argument("--output-dir", required=True)
    suite.add_argument("--run-prefix", required=True)
    suite.add_argument("--resume", action="store_true")
    human = sub.add_parser("human-summary", help="Read manually filled CSV; never treats AI suggestions as human")
    human.add_argument("--human-csv", required=True)
    human.add_argument("--mapping", required=True)
    human.add_argument("--judge-scores", action="append", default=[])
    human.add_argument("--output", required=True)
    compare = sub.add_parser("compare", help="Recompute full and paired metrics from actual completed scores")
    compare.add_argument("--scores", action="append", required=True, metavar="GROUP=PATH")
    compare.add_argument("--output-dir", required=True)
    args = p.parse_args(argv)
    from src.contracts.m3 import ContractError
    from src.evaluation.inputs import resolve
    from src.evaluation.review import compare_groups, human_summary, prepare_suite, save_once
    try:
        if args.command == "prepare":
            if Path(args.run_prefix).name != args.run_prefix or args.run_prefix in ("", ".", ".."):
                raise ContractError("run-prefix must be one directory name")
            result = prepare_suite(resolve(args.output_dir), args.run_prefix, resume=args.resume)
        elif args.command == "human-summary":
            result = human_summary(resolve(args.human_csv), resolve(args.mapping), [resolve(p) for p in args.judge_scores])
            save_once(resolve(args.output), result)
        else:
            mapping = {}
            for arg in args.scores:
                name, separator, path = arg.partition("=")
                if not separator or name in mapping:
                    raise ContractError("Use distinct GROUP=PATH arguments")
                mapping[name] = resolve(path)
            result = compare_groups(mapping, resolve(args.output_dir))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print("Review stopped: " + (str(exc) if isinstance(exc, ContractError) else type(exc).__name__), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
