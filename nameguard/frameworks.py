"""Reserved tool names published by agent frameworks.

A name here is one the framework itself puts on the wire. If an MCP server
advertises the same name, the two tools compete for it, and depending on the
framework the server's tool can end up holding it - so the framework's own tool
becomes unreachable, or a call meant for the framework is dispatched to the
server instead.

Every list below is transcribed from the framework's own source, and cites the
file it came from. Nothing here is inferred.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Framework:
    key: str
    name: str
    reserved: frozenset[str]
    source: str
    note: str
    # Optional per-name detail. `note` describes the framework's guard as a
    # whole, so without this a generic name would be explained with a fact that
    # only applies to a different one.
    why: dict[str, str] = None  # type: ignore[assignment]

    def explain(self, tool: str) -> str:
        """The most specific explanation available for `tool`."""
        if self.why and tool in self.why:
            return self.why[tool]
        return self.note


# google/adk-python - src/google/adk/tools/mcp_tool/mcp_tool.py
# The four constants are refused at MCP registration; set_model_response is the
# gap reported in issue #7144 (fixed by #7145).
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
    source="src/google/adk/tools/mcp_tool/mcp_tool.py",
    note="Refused at MCP registration when the server advertises the name.",
    why={
        "set_model_response": (
            "Injected by the output-schema processor whenever output_schema is "
            "set alongside other tools (flows/llm_flows/prompt/_schema.py) and "
            "read back by name in base_llm_flow.py. It was missing from "
            "_RESERVED_TOOL_NAMES until google/adk-python#7144."
        ),
        "transfer_to_agent": (
            "The framework's own agent-transfer tool; also the name a server "
            "would need to hijack a hand-off."
        ),
    },
)

# google/adk-go - tool/mcptoolset/set.go
_ADK_GO = Framework(
    key="adk-go",
    name="Google ADK (Go)",
    reserved=frozenset({
        "set_model_response", "transfer_to_agent", "finish_task",
        "task_completed", "google_search", "google_maps", "url_context",
        "vertex_ai_search", "code_execution", "load_artifacts", "load_memory",
    }),
    source="tool/mcptoolset/set.go",
    note="Reserved names are refused when an McpToolset loads server tools.",
)

# google/adk-java - core/src/main/java/com/google/adk/tools/mcp/McpToolset.java
_ADK_JAVA = Framework(
    key="adk-java",
    name="Google ADK (Java)",
    reserved=frozenset({
        "set_model_response", "transfer_to_agent", "finish_task",
        "task_completed", "google_search", "google_maps", "url_context",
        "vertex_ai_search", "code_execution", "load_artifacts", "load_memory",
    }),
    source="core/src/main/java/com/google/adk/tools/mcp/McpToolset.java",
    note="Reserved names are refused when McpToolset loads server tools.",
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
