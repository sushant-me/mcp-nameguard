"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from . import __version__
from . import frameworks
from .mcp_http import McpHttpError, list_tools_http
from .mcp_stdio import McpError, McpStdioError, list_tools_stdio
from .scan import load, scan_payload, scan_names


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
        "check",
        help=(
            "check a tools/list JSON payload, a file of names, stdin, or a live "
            "MCP server over stdio"
        ),
    )
    check.add_argument(
        "path",
        nargs="?",
        help="JSON file, newline-separated names, or - for stdin",
    )
    check.add_argument(
        "--stdio",
        metavar="COMMAND",
        help=(
            "start an MCP server with this command and ask it for its tools, "
            'e.g. --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"'
        ),
    )
    check.add_argument(
        "--http",
        metavar="URL",
        help="check a remote MCP server over Streamable HTTP",
    )
    check.add_argument(
        "--header",
        action="append",
        metavar="'Name: value'",
        help="extra header for --http (repeatable), e.g. --header 'Authorization: Bearer ...'",
    )
    check.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        metavar="SECONDS",
        help="how long to wait for the server (default 20)",
    )
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


def _by_severity(findings):
    """Unguarded collisions first: nothing in the framework refuses those names."""
    return sorted(findings, key=lambda f: (f.status == "guarded", f.tool, f.framework.key))


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "frameworks":
        for fw in frameworks.FRAMEWORKS:
            print(
                f"{fw.key}\t{len(fw.guarded)}/{len(fw.reserved)} guarded\t{fw.name}"
            )
        return 0

    if args.command == "list":
        for fw in _select(args.framework):
            for name in sorted(fw.reserved):
                print(f"{fw.key}\t{name}")
        return 0

    targets = _select(args.framework)

    if args.stdio and args.http:
        print("error: give either --stdio or --http, not both", file=sys.stderr)
        return 2

    if args.stdio or args.http:
        headers: dict[str, str] = {}
        for raw in args.header or []:
            name, _, value = raw.partition(":")
            if not name.strip() or not value.strip():
                print(f"error: --header wants 'Name: value', got {raw!r}", file=sys.stderr)
                return 2
            headers[name.strip()] = value.strip()

        try:
            if args.http:
                names = list_tools_http(args.http, timeout_s=args.timeout, headers=headers)
            else:
                names = list_tools_stdio(args.stdio, timeout_s=args.timeout)
        except McpError as exc:
            # A server we could not query is not a clean result.
            print(f"error: {exc}", file=sys.stderr)
            return 2
        findings = scan_names(names, targets)
        if args.json:
            print(json.dumps([f.as_dict() for f in findings], indent=2))
        elif findings:
            for f in _by_severity(findings):
                print(f"{f.status.upper():9}  {f.tool}  ({f.framework.name})")
                print(f"           {f.framework.source}")
                print(f"           {f.framework.explain(f.tool)}")
        else:
            print(f"No collisions among {len(names)} tool(s).")
        return 1 if findings else 0

    if not args.path:
        print("error: give a path, or --stdio COMMAND", file=sys.stderr)
        return 2

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
        for f in _by_severity(findings):
            print(f"{f.status.upper():9}  {f.tool}  ({f.framework.name})")
            print(f"           {f.framework.source}")
            print(f"           {f.framework.explain(f.tool)}")
    else:
        print("No collisions.")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
