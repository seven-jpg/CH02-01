#!/usr/bin/env python3
"""Offline judge-request audit and checked evaluation merges. No API calls."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command",required=True)
    audit = commands.add_parser("audit",help="Count failures, unknown usage and cross-run repeated requests")
    audit.add_argument("--journal",action="append",required=True)
    audit.add_argument("--output",required=True)
    merge = commands.add_parser("merge",help="Reconstruct scores and merge a full subset without overwriting history")
    for name in ("questions","answers","metadata","manifest","predictions","config","output-dir","run-id"):
        merge.add_argument("--"+name,required=True)
    merge.add_argument("--source-dir",action="append",required=True)
    merge.add_argument("--journal",action="append",required=True)
    args = parser.parse_args(argv)
    from src.contracts.m3 import ContractError
    from src.evaluation.inputs import resolve
    from src.evaluation.records import audit_requests, merge_evaluations
    from src.evaluation.score import write_new
    try:
        journals = [resolve(p) for p in args.journal]
        if args.command=="audit":
            output = resolve(args.output)
            if output in journals:
                raise ContractError("Audit output cannot overwrite an input journal")
            result = audit_requests(journals)
            write_new(output,result)
            status = 0
        else:
            paths = {k:resolve(getattr(args,k)) for k in ("questions","answers","metadata","manifest","predictions")}
            result = merge_evaluations(paths,resolve(args.config),[resolve(p) for p in args.source_dir],
                                      journals,resolve(args.output_dir),args.run_id)
            status = 0 if result["N_scored"]==result["N_fixed"] else 2
        print(json.dumps(result,ensure_ascii=False))
        return status
    except Exception as exc:
        print("Record operation stopped: "+(str(exc) if isinstance(exc,ContractError) else type(exc).__name__),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
