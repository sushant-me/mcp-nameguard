"""Reserved tool names published by agent frameworks.

A name here is one the framework itself puts on the wire. If an MCP server
advertises the same name, the two tools compete for it, and depending on the
framework the server's tool can end up holding it - so the framework's own tool
becomes unreachable, or a call meant for the framework is dispatched to the
server instead.

Two different things are tracked, because they are not the same thing:

``guarded``
    Names the framework refuses at MCP-server registration *today*. These are
    transcribed from the framework's own source, and that file is cited.

``reserved``
    Every name the framework itself puts on the wire, guarded or not. The
    difference between the two sets is the set of names a server can currently
    take for itself.

A ``reserved`` name that is *not* in ``guarded`` is the more interesting finding,
not the less: the framework owns the name and does not defend it. Where a name
sits in that position the per-name reason says so explicitly.

Nothing here is inferred from behaviour. Where a framework has no guard at all,
that is stated rather than papered over with a citation to a file that does not
contain one.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Framework:
    key: str
    name: str
    reserved: frozenset[str]
    guarded: frozenset[str]
    source: str
    note: str
    # Optional per-name detail. `note` describes the framework's guard as a
    # whole, so without this a generic name would be explained with a fact that
    # only applies to a different one.
    why: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        stray = self.guarded - self.reserved
        if stray:
            # A name cannot be refused at registration without also being a
            # framework-owned wire name. Catch the contradiction at import
            # rather than reporting a status that cannot exist.
            raise ValueError(
                f"{self.key}: guarded names missing from reserved: "
                f"{sorted(stray)}"
            )

    def is_guarded(self, tool: str) -> bool:
        """True when the framework refuses this name at MCP registration."""
        return tool in self.guarded

    def status(self, tool: str) -> str:
        """``"guarded"`` or ``"unguarded"``, as a stable machine-readable token."""
        return "guarded" if self.is_guarded(tool) else "unguarded"

    def explain(self, tool: str) -> str:
        """The most specific explanation available for `tool`."""
        if tool in self.why:
            return self.why[tool]
        if not self.is_guarded(tool):
            return (
                f"{self.name} puts '{tool}' on the wire but does not refuse the "
                f"name at MCP registration, so a server can take it."
            )
        return self.note


# google/adk-python - src/google/adk/tools/mcp_tool/mcp_tool.py
# Verified against upstream: _RESERVED_TOOL_NAMES holds exactly the four
# guarded names below. set_model_response is a framework-owned wire name that
# the guard omits - the gap reported in google/adk-python#7144 and fixed by
# #7145, which was still unmerged when this list was last checked.
_ADK_PYTHON = Framework(
    key="adk-python",
    name="Google ADK (Python)",
    reserved=frozenset({
        "adk_request_credential",       # REQUEST_EUC_FUNCTION_CALL_NAME
        "adk_request_confirmation",     # REQUEST_CONFIRMATION_FUNCTION_CALL_NAME
        "adk_request_input",            # REQUEST_INPUT_FUNCTION_CALL_NAME
        "transfer_to_agent",
        "set_model_response",
    }),
    guarded=frozenset({
        "adk_request_credential",
        "adk_request_confirmation",
        "adk_request_input",
        "transfer_to_agent",
    }),
    source="src/google/adk/tools/mcp_tool/mcp_tool.py, _RESERVED_TOOL_NAMES",
    note="Refused at MCP registration when the server advertises the name.",
    why={
        "set_model_response": (
            "Injected by the output-schema processor whenever output_schema is "
            "set alongside other tools (flows/llm_flows/prompt/_schema.py) and "
            "read back by name in base_llm_flow.py. Request processors run "
            "before tool resolution, so a server advertising this name is the "
            "last-wins survivor. It was missing from _RESERVED_TOOL_NAMES until "
            "google/adk-python#7144."
        ),
        "transfer_to_agent": (
            "The framework's own agent-transfer tool; also the name a server "
            "would need to hijack a hand-off."
        ),
    },
)

# google/adk-go - tool/mcptoolset/set.go
#
# Checked against upstream main: there is no reserved-name guard in this file,
# or anywhere else in the repository, so every name below is unguarded. The
# guard that would refuse them is proposed in google/adk-go#1606.
#
# Every name here was verified as a string literal in the Go sources. An
# earlier revision of this file copied the Java list, which was wrong in both
# directions: Go has no `google_maps` tool (its grounded-maps tool is
# `google_maps_grounding`, built by the factory in
# internal/configurable/configurable_utils.go) and no `vertex_ai_search` at all.
# Both were reported as collisions against a framework that does not use them,
# while `google_maps_grounding` was not watched for.
_ADK_GO = Framework(
    key="adk-go",
    name="Google ADK (Go)",
    reserved=frozenset({
        "set_model_response", "transfer_to_agent", "finish_task",
        "task_completed", "google_search", "google_maps_grounding",
        "url_context", "code_execution", "load_artifacts", "load_memory",
    }),
    guarded=frozenset(),
    source="tool/mcptoolset/set.go (no guard present upstream)",
    note=(
        "No reserved-name guard exists in this framework upstream: an "
        "McpToolset loads server tools without checking their names."
    ),
)

# google/adk-java -
# core/src/main/java/com/google/adk/tools/mcp/McpToolset.java
#
# Same finding as Go: no reserved-name guard upstream, so nothing is guarded.
# Guard proposed in google/adk-java#1515.
#
# Java's tool set differs from Go's, and the two must not share a list. Every
# name below is a `super("...")` literal in a non-test Java source, plus the two
# the framework contributes outside a tool class: `set_model_response`
# (added by the output-schema path) and `transfer_to_agent`.
#
# Two names in the previous revision were absent from Java entirely —
# `finish_task` and `task_completed` — so they were reported as collisions
# against a framework that does not define them.
#
# `LoadMemoryTool` exists but takes its name from the `loadMemory` method
# rather than a literal, so its exact wire name was not verified and it is
# deliberately left out rather than guessed at.
_ADK_JAVA = Framework(
    key="adk-java",
    name="Google ADK (Java)",
    reserved=frozenset({
        "set_model_response", "transfer_to_agent", "google_search",
        "google_maps", "url_context", "vertex_ai_search", "code_execution",
        "load_artifacts",
    }),
    guarded=frozenset(),
    source="core/src/main/java/com/google/adk/tools/mcp/McpToolset.java "
           "(no guard present upstream)",
    note=(
        "No reserved-name guard exists in this framework upstream: McpToolset "
        "loads server tools without checking their names."
    ),
)

FRAMEWORKS: tuple[Framework, ...] = (_ADK_PYTHON, _ADK_GO, _ADK_JAVA)

_BY_KEY = {f.key: f for f in FRAMEWORKS}


def get(key: str) -> Framework:
    try:
        return _BY_KEY[key]
    except KeyError:
        raise KeyError(
            f"unknown framework {key!r}; known: {', '.join(sorted(_BY_KEY))}"
        ) from None


def all_reserved() -> frozenset[str]:
    """Union of every framework's reserved names."""
    out: set[str] = set()
    for f in FRAMEWORKS:
        out |= f.reserved
    return frozenset(out)


def all_guarded() -> frozenset[str]:
    """Union of the names every framework actually refuses today."""
    out: set[str] = set()
    for f in FRAMEWORKS:
        out |= f.guarded
    return frozenset(out)
