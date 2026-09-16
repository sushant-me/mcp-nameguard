"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from . import __version__
from . import frameworks
from .scan import load, scan_payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-nameguard",
        description=(
            "Check the tool names an MCP server advertises against the names "
            "agent frameworks reserve for their own tools."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser(
        "check", help="scan a tools/list JSON payload (or a file of names, or - for stdin)"
    )
    check.add_argument("path", help="JSON file, newline-separated names, or - for stdin")
    check.add_argument(
        "--framework", action="append", metavar="KEY",
        help="limit to a framework (repeatable); default is all",
    )
    check.add_argument("--json", action="store_true", help="machine-readable output")

    ls = sub.add_parser("list", help="print the reserved names")
    ls.add_argument("--framework", action="append", metavar="KEY")

    sub.add_parser("frameworks", help="list the supported frameworks")
    return parser


def _select(keys: Sequence[str] | None) -> tuple[framework, ...]:
    """The frameworks to check against: all of them unless --framework is given."""
    if not keys:
        return frameworks.FRAMEWORKS
    return tuple(frameworks.get(k) for k in keys)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "frameworks":
        for fw in frameworks.FRAMEWORKS:
            print(f"{fw.key}\t{len(fw.reserved)} names\t{fw.name}")
        return 0

    if args.command == "list":
        for fw in _select(args.framework):
            for name in sorted(fw.reserved):
                print(f"{fw.key}\t{name}")
        return 0

    targets = _select(args.framework)

    if args.path == "-":
        text = sys.stdin.read().strip()
        payload = (
            json.loads(text)
            if text.startswith(("[", "{"))
            else [line.strip() for line in text.splitlines() if line.strip()]
        )
    else:
        payload = load(args.path)

    findings = scan_payload(payload, targets)

    if args.json:
        print(json.dumps([f.as_dict() for f in findings], indent=2))
    elif findings:
        for f in findings:
            print(f"COLLISION  {f.tool}  ({f.framework.name})")
            print(f"           reserved in {f.framework.source}")
            print(f"           {f.framework.explain(f.tool)}")
    else:
        print("No collisions.")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
