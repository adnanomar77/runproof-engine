from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .replay import LoadedRun, load_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="runproof", description="Inspect and compare RunProof artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="inspect a run artifact")
    inspect_parser.add_argument("path", type=Path)
    inspect_parser.add_argument("--json", action="store_true", dest="as_json")

    verify_parser = subparsers.add_parser("verify", help="verify input and output integrity")
    verify_parser.add_argument("path", type=Path)
    verify_parser.add_argument("--json", action="store_true", dest="as_json")

    diff_parser = subparsers.add_parser("diff", help="compare two run artifacts")
    diff_parser.add_argument("left", type=Path)
    diff_parser.add_argument("right", type=Path)
    diff_parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            run = load_run(args.path)
            payload = run.manifest
            text = json.dumps(payload, indent=2, ensure_ascii=False) if args.as_json else _inspect_text(run)
        elif args.command == "verify":
            run = load_run(args.path)
            report = run.verify_integrity()
            payload = report.to_dict()
            text = json.dumps(payload, indent=2, ensure_ascii=False) if args.as_json else str(report)
            print(text)
            return 0 if report.status == "verified" else 2
        else:
            left = load_run(args.left)
            right = load_run(args.right)
            comparison = left.diff(right)
            payload = comparison.to_dict()
            text = json.dumps(payload, indent=2, ensure_ascii=False) if args.as_json else comparison.render()
        print(text)
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"runproof: {error}", file=sys.stderr)
        return 2


def _inspect_text(run: LoadedRun) -> str:
    manifest = run.manifest
    run_info = manifest.get("run", {})
    return "\n".join([
        f"name: {run_info.get('name')}",
        f"run_id: {run_info.get('run_id')}",
        f"status: {run_info.get('status')}",
        f"inputs: {len(manifest.get('inputs', []))}",
        f"steps: {len(manifest.get('steps', []))}",
        f"outputs: {len(manifest.get('outputs', []))}",
        f"checks: {len(manifest.get('checks', []))}",
    ])
