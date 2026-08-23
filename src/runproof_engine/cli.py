from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path
from typing import Any

from .auto import auto_run
from .replay import LoadedRun, load_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="runproof", description="Inspect and compare RunProof artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run a Python script with automatic observation")
    run_parser.add_argument("script", type=Path)
    run_parser.add_argument("script_args", nargs="*")
    run_parser.add_argument("--root", type=Path, default=Path("runs"))
    run_parser.add_argument("--backend", choices=("auto", "monitoring", "trace"), default="auto")
    run_parser.add_argument("--no-audit", action="store_true", help="disable runtime audit events")
    run_parser.add_argument("--capture-output", action="append", default=[], help="capture a file written by the script")

    replay_parser = subparsers.add_parser("replay", help="re-run a Python script and compare it with an artifact")
    replay_parser.add_argument("artifact", type=Path)
    replay_parser.add_argument("script", type=Path)
    replay_parser.add_argument("script_args", nargs="*")
    replay_parser.add_argument("--root", type=Path, default=Path("runs"))
    replay_parser.add_argument("--backend", choices=("auto", "monitoring", "trace"), default="auto")
    replay_parser.add_argument("--no-audit", action="store_true", help="disable runtime audit events")
    replay_parser.add_argument("--capture-output", action="append", default=[], help="capture a file written by the script")
    replay_parser.add_argument("--mode", choices=("strict", "fresh"), default="strict")

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
        if args.command == "run":
            return _run_script(args)
        if args.command == "replay":
            return _replay_script(args)
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


def _execute_script(args: argparse.Namespace, *, name: str | None = None) -> tuple[Any, int]:
    script = args.script.expanduser().resolve()
    if not script.is_file():
        raise FileNotFoundError(script)
    old_argv = sys.argv
    sys.argv = [str(script), *args.script_args]
    captured = auto_run(
        name or script.stem,
        root=args.root,
        backend=args.backend,
        include_paths=[script.parent],
        capture_audit=not args.no_audit,
        capture_outputs=args.capture_output,
    )
    exit_code = 0
    try:
        with captured:
            runpy.run_path(str(script), run_name="__main__")
    except SystemExit as error:
        exit_code = int(error.code) if isinstance(error.code, int) else 1
    except BaseException as error:  # noqa: BLE001 - the target script may raise any exception
        print(f"runproof: target failed: {error}", file=sys.stderr)
        exit_code = 1
    finally:
        sys.argv = old_argv
    return captured.context.result, exit_code


def _run_script(args: argparse.Namespace) -> int:
    result, exit_code = _execute_script(args)
    print(f"status: {result.status}")
    print(f"run_id: {result.run_id}")
    print(f"artifact_dir: {result.artifact_dir}")
    return exit_code if exit_code else (0 if result.status == "verified" else 2)


def _replay_script(args: argparse.Namespace) -> int:
    previous = load_run(args.artifact)
    replayed, exit_code = _execute_script(args, name=f"{previous.name}_replay")
    report = previous.replay(mode=args.mode, runner=lambda _previous: replayed.artifact_dir)
    print(f"status: {report.status}")
    print(f"run_id: {report.run_id}")
    print(f"compared_run_id: {report.compared_run_id}")
    print(f"artifact_dir: {replayed.artifact_dir}")
    if exit_code:
        return exit_code
    return 0 if report.status == "verified" else 2


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
