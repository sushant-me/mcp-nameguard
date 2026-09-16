#!/usr/bin/env python3
"""Reality check — run the reserved-name check against real, live MCP servers.

The README states a precision result: nine servers read over stdio, 121 tools,
no collisions. A number in a README is a claim; this script is what makes it a
measurement someone else can repeat.

It exists because the first version of that claim was not measured at all. It
cited three hand-picked servers, and hand-picked examples cannot falsify
anything - the same gap that produced four false positives in a sibling tool the
moment its rules met repositories nobody had chosen. Selecting your own test set
is not measuring, it is illustrating.

Usage:

    python scripts/reality_check.py                 # the documented set
    python scripts/reality_check.py --servers file  # one stdio command per line
    python scripts/reality_check.py --markdown      # table for the README

Each server is started and asked for its tools. A server that fails to start or
does not answer is reported as an **error**, never as a clean scan: a checker
that reports success for a server it never read is worse than no checker, and
several of the servers below need credentials most machines do not have. Those
failures are part of the result, not noise to hide.
"""

from __future__ import annotations

import argparse
import sys

from nameguard import frameworks
from nameguard.mcp_stdio import McpError, list_tools_stdio
from nameguard.scan import scan_names

# Servers that start with no credentials, so the result is reproducible by
# anyone. Kept deliberately small and boring: every one of these is a project
# with its own release process, not something chosen because it passes.
DEFAULT_SERVERS: list[str] = [
    "npx -y @modelcontextprotocol/server-filesystem /tmp",
    "npx -y @modelcontextprotocol/server-everything",
    "npx -y @modelcontextprotocol/server-memory",
    "npx -y @modelcontextprotocol/server-sequential-thinking",
    "npx -y @google-cloud/storage-mcp",
    "npx -y firecrawl-mcp",
    "npx -y chrome-devtools-mcp",
    "npx -y @google-cloud/observability-mcp",
    "npx -y @upstash/context7-mcp",
]

# Kept separate: these need credentials, so they are expected to fail here.
# Listing them is the point - a check that only ever runs where it succeeds
# proves nothing about the failure path.
KNOWN_UNREADABLE: list[str] = [
    "npx -y mcp-server-gsc",
    "npx -y @sentry/mcp-server",
    "npx -y @google-cloud/gcloud-mcp",
    "npx -y mcp-server-google-search-console",
]


def check(command: str, timeout_s: float) -> tuple[str, int, str]:
    """Returns (status, tool count, detail) for one server command."""
    try:
        names = list_tools_stdio(command, timeout_s=timeout_s)
    except McpError as exc:
        # The distinction that matters: unreadable is not clean.
        return "error", 0, str(exc)
    findings = scan_names(names, frameworks.FRAMEWORKS)
    if findings:
        detail = ", ".join(f"{f.tool} ({f.framework.key})" for f in findings)
        return "COLLISION", len(names), detail
    return "clean", len(names), ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--servers", help="file of stdio commands, one per line")
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--markdown", action="store_true", help="print a table")
    ap.add_argument(
        "--unreadable",
        action="store_true",
        help="run the credential-gated set instead (failures expected)",
    )
    args = ap.parse_args(argv)

    if args.servers:
        with open(args.servers, encoding="utf-8") as handle:
            commands = [ln.strip() for ln in handle if ln.strip()]
    elif args.unreadable:
        commands = KNOWN_UNREADABLE
    else:
        commands = DEFAULT_SERVERS

    rows: list[tuple[str, str, int, str]] = []
    for command in commands:
        label = command.replace("npx -y ", "")
        status, count, detail = check(command, args.timeout)
        rows.append((label, status, count, detail))
        print(f"  {status:9} {label[:52]:54} {count:>3} tool(s) {detail[:40]}",
              file=sys.stderr)

    if args.markdown:
        print("| server | tools | result |")
        print("|---|---|---|")
        for label, status, count, detail in rows:
            shown = "no collisions" if status == "clean" else status.lower()
            print(f"| `{label}` | {count if count else '-'} | {shown} |")

    total = sum(c for _, s, c, _ in rows if s == "clean")
    clean = sum(1 for _, s, _, _ in rows if s == "clean")
    errored = sum(1 for _, s, _, _ in rows if s == "error")
    print(
        f"\n{total} tools across {clean} readable server(s), "
        f"{errored} unreadable (reported as errors, not as clean scans)",
        file=sys.stderr,
    )
    # A collision is the tool working, but it means the README table is stale.
    return 1 if any(s == "COLLISION" for _, s, _, _ in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
