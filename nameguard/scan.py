"""Compare the tool names an MCP server advertises against framework-reserved names."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from . import frameworks
from .frameworks import Framework


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
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read().strip()
    # A plain newline-separated list is convenient when copying names by hand.
    if not text.startswith(("[", "{")):
        return [line.strip() for line in text.splitlines() if line.strip()]
    return json.loads(text)
