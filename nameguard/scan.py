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
# MCP servers actually use. A leading separator is part of the name - `_tool`
# and `-tool` are ordinary - so the first character is drawn from the same class
# rather than from a narrower one. Anything else on a line means the input was
# not a list of names.
_PLAUSIBLE_NAME = re.compile(r"^[A-Za-z0-9_.:/-]+$")

# Sentinel for "this text is not a JSON document at all", which is not the same
# answer as "it is the JSON document `null`".
_NOT_JSON = object()


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

    What the two forms can and cannot be told apart by is worth stating, because
    it bounds what this function can promise. Error text carrying a space or a
    bracket is recognisably not a name list and is refused outright. A *single
    bare word* is not: `null` from a failed `--json` command and a server whose
    only tool is named `null` are the same bytes. Only a complete JSON document
    can be classified, and those are rejected as payloads; a lone word that is
    not JSON is taken at face value, which is why the JSON form is the one the
    README documents for pipelines.
    """
    stripped = text.strip()
    if stripped.startswith(("[", "{")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InputError(f"input looks like JSON but could not be parsed: {exc}") from exc

    # `null`, `true`, `false` and a bare number are complete JSON documents that
    # are not a tool list. Read as a name list each becomes one tool - `null` -
    # that collides with nothing, which turns a command that failed into a clean
    # scan. A name list never parses as JSON, so this cannot catch one.
    try:
        document = json.loads(stripped)
    except json.JSONDecodeError:
        document = _NOT_JSON
    if document is not _NOT_JSON and not isinstance(document, (list, dict)):
        raise InputError(
            f"input is the JSON value {stripped!r}, which is not a tools/list "
            f"payload or a list of tool names. A command that failed and printed "
            f"this must not be read as a scan that found nothing."
        )

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if not lines:
        raise InputError(
            "input is empty: expected a tools/list payload or a list of tool names"
        )

    implausible = [line for line in lines if not _PLAUSIBLE_NAME.match(line)]
    if implausible:
        raise InputError(
            f"input is neither a JSON payload nor one tool name per line "
            f"(first offending line: {implausible[0]!r}). Plain input is refused "
            f"whole rather than in part, because text that is not a name list is "
            f"usually a failed command's output, and reading part of it as a scan "
            f"would report collisions found: none."
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
