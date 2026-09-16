"""Compare the tool names an MCP server advertises against framework-reserved names."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from . import frameworks
from .frameworks import Framework


class InputError(RuntimeError):
    """The input could not be read as a payload or as a list of names.

    Distinct from `McpError`, which is about a *server* that could not be asked.
    Both reach the CLI as a reportable reason and exit code 2, because neither is
    a clean result.
    """


# A tool name on the wire is an identifier: letters, digits, and the separators
# MCP servers actually use. Anything else on a line means the input was not a
# list of names.
_PLAUSIBLE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")


def payload_from_text(text: str) -> Any:
    """Read a payload from text that is either JSON or a plain list of names.

    A newline-separated list of names is supported on purpose, because copying
    names by hand is common. It is also what a *failed* command in a pipeline
    looks like, and those two have to be told apart.

    The documented pipeline is

        mcp-inspector list-tools --json | mcp-nameguard check -

    and `--json` output begins with `[` or `{`. If the command on the left
    failed, what arrives instead is its error text - a shell message or a
    traceback. Reading that as a list of tool names produced "No collisions."
    and exit 0, which is the fail-open this module exists to avoid: the names
    were never read, and the scan reported that nothing was wrong.
    """
    stripped = text.strip()
    if stripped.startswith(("[", "{")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InputError(f"input looks like JSON but could not be parsed: {exc}") from exc

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if not lines:
        raise InputError(
            "input is empty: expected a tools/list payload or a list of tool names"
        )

    implausible = [line for line in lines if not _PLAUSIBLE_NAME.match(line)]
    if implausible:
        raise InputError(
            f"input is not JSON and does not look like a list of tool names "
            f"(first offending line: {implausible[0]!r}). If this text came from a "
            f"command in a pipeline, that command probably failed; its error output "
            f"must not be read as a clean scan."
        )
    return lines


@dataclass(frozen=True)
class Finding:
    tool: str
    framework: Framework

    @property
    def status(self) -> str:
        """``guarded`` if the framework refuses the name, else ``unguarded``.

        The distinction is the finding: a guarded collision is a server that
        broke a documented rule, an unguarded one is a server taking a name the
        framework owns and does not defend.
        """
        return self.framework.status(self.tool)

    def as_dict(self) -> dict[str, str]:
        return {
            "tool": self.tool,
            "framework": self.framework.key,
            "framework_name": self.framework.name,
            "status": self.status,
            "source": self.framework.source,
            "why": self.framework.explain(self.tool),
        }


def names_from_payload(payload: Any) -> list[str]:
    """Extract tool names from the shapes an MCP client actually sees.

    Accepts a `tools/list` result (`{"tools": [{"name": ...}]}`), a bare list,
    a single object, or a list of plain strings. Anything else is a TypeError
    rather than a silent empty result, so a malformed input cannot look like a
    clean scan.
    """
    if isinstance(payload, dict):
        if "tools" in payload:
            payload = payload["tools"]
        elif "name" in payload:
            payload = [payload]
        else:
            raise TypeError(
                "object has neither 'tools' nor 'name'; not an MCP tools/list result"
            )

    if not isinstance(payload, list):
        raise TypeError(f"expected a list of tools, got {type(payload).__name__}")

    names: list[str] = []
    for entry in payload:
        if isinstance(entry, str):
            names.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
        else:
            raise TypeError(f"tool entry without a string 'name': {entry!r}")
    return names


def scan_names(
    names: Iterable[str], targets: Iterable[Framework] | None = None
) -> list[Finding]:
    """Return one Finding per (tool, framework) collision, sorted for stable output."""
    selected = tuple(targets) if targets is not None else frameworks.FRAMEWORKS
    findings: list[Finding] = []
    for name in sorted(set(names)):
        for fw in selected:
            if name in fw.reserved:
                findings.append(Finding(tool=name, framework=fw))
    return sorted(findings, key=lambda f: (f.tool, f.framework.key))


def scan_payload(
    payload: Any, targets: Iterable[Framework] | None = None
) -> list[Finding]:
    return scan_names(names_from_payload(payload), targets)


def load(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise InputError(f"could not read {path}: {exc.strerror or exc}") from exc
    return payload_from_text(text)
