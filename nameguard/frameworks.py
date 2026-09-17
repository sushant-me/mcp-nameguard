"""Reserved tool names published by agent frameworks.

A name here is one the framework itself puts on the wire. If an MCP server
advertises the same name, the two tools compete for it, and depending on the
framework the server's tool can end up holding it - so the framework's own tool
becomes unreachable, or a call meant for the framework is dispatched to the
server instead.

Two different things are tracked, because they are not the same thing:

``guarded``
    Names the framework refuses for a server-supplied tool before the request
    reaches the model - at MCP-server registration, or when the request is
    built. These are transcribed from the framework's own source, and that file
    is cited.

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
                f"{self.name} puts '{tool}' on the wire but does not refuse a "
                f"server-supplied tool of that name, so a server can take it."
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
        # Framework-shipped tools a caller can add. None are in the upstream
        # guard either, so they are unguarded like set_model_response.
        "exit_loop",
        "list_skills",
        "load_skill",
        "load_skill_resource",
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

# google/adk-go - tool/mcptoolset/set.go, tool/toolutils/toolutils.go
#
# There is no reserved-name *list* in this repository, and McpToolset loads
# server tools without checking their names. Reporting that as "nothing is
# guarded" was nevertheless wrong, and an earlier revision of this file did.
#
# Tools that are packed into a request go through toolutils.PackTool, which
# refuses a duplicate name outright:
#
#     if _, ok := req.Tools[name]; ok {
#         return fmt.Errorf("duplicate tool: %q", name)
#     }
#
# set_model_response is packed that way (internal/llminternal/
# outputschema_processor.go -> PackTool), and so is every MCP tool
# (tool/mcptoolset/tool.go -> PackTool). A server therefore cannot take a name
# the framework packs; the request build fails instead. Fail-closed, but a
# refusal, so those names are guarded here.
#
# The gap is the in-model built-ins. geminitool.setTool appends them straight
# to req.Config.Tools (tool/geminitool/tool.go), so they never enter req.Tools,
# PackTool never sees the name, and a server advertising one is accepted. Both
# tools are then advertised under the same name - observed on
# google/adk-go#1606, where the model was non-deterministic about which it
# called.
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
        "exit_loop", "list_skills", "load_skill", "load_skill_resource",
    }),
    # Packed through toolutils.PackTool, which errors on a duplicate name.
    guarded=frozenset({
        "set_model_response", "transfer_to_agent", "finish_task",
        "task_completed", "load_artifacts", "load_memory",
        "exit_loop", "list_skills", "load_skill", "load_skill_resource",
    }),
    source="tool/toolutils/toolutils.go (PackTool duplicate check); "
           "tool/mcptoolset/set.go has no reserved list",
    note=(
        "No reserved-name list exists here, but every packed tool goes through "
        "toolutils.PackTool, which refuses a duplicate name - so those names "
        "cannot be taken. In-model built-ins bypass PackTool and are not "
        "refused."
    ),
    why={
        "google_search": "in-model built-in: geminitool.setTool appends it to "
                         "Config.Tools, so PackTool never checks the name and "
                         "the framework does not refuse it",
        "google_maps_grounding": "in-model built-in: appended to Config.Tools, "
                                 "never enters req.Tools; the framework does "
                                 "not refuse it",
        "url_context": "in-model built-in: appended to Config.Tools, never "
                       "enters req.Tools; the framework does not refuse it",
        "code_execution": "in-model built-in: appended to Config.Tools, never "
                          "enters req.Tools; the framework does not refuse it",
    },
)

# google/adk-java -
# core/src/main/java/com/google/adk/tools/mcp/McpToolset.java
#
# Same shape as Go, and the same correction. There is no reserved-name list,
# but LlmRequest.Builder.appendTools refuses a duplicate through a throwing
# merger (models/LlmRequest.java), and every tool enters through
# tools/BaseTool.java. A server cannot take a name the framework packs:
# google/adk-java#1513 records the probe, where a server tool named
# set_model_response produced "Duplicate tool name: set_model_response".
#
# The gap is again the in-model built-ins. GoogleSearchTool, GoogleMapsTool,
# UrlContextTool, VertexAiSearchTool and BuiltInCodeExecutionTool override
# processLlmRequest to append only to config.Tools and never call appendTools,
# so the merger never sees the name. The same probe shows a callable tool
# advertising google_search being accepted, with the dispatch map resolving
# google_search to the server's tool (Functions.handleFunctionCalls resolves by
# name).
#
# Java's tool set differs from Go's, and the two must not share a list. Every
# name below is a `super("...")` literal in a non-test Java source, plus the two
# the framework contributes outside a tool class: `set_model_response`
# (added by the output-schema path) and `transfer_to_agent`.
#
# Two names in the previous revision were absent from Java entirely -
# `finish_task` and `task_completed` - so they were reported as collisions
# against a framework that does not define them.
_ADK_JAVA = Framework(
    key="adk-java",
    name="Google ADK (Java)",
    reserved=frozenset({
        "set_model_response", "transfer_to_agent", "google_search",
        "google_maps", "url_context", "vertex_ai_search", "code_execution",
        "load_artifacts", "loadMemory",
        "exit_loop", "list_skills", "load_skill", "load_skill_resource",
    }),
    # Enter through appendTools, whose merger throws on a duplicate name.
    guarded=frozenset({
        "set_model_response", "transfer_to_agent", "load_artifacts",
        "loadMemory", "exit_loop", "list_skills", "load_skill",
        "load_skill_resource",
    }),
    source="models/LlmRequest.java (appendTools throwing merger) + "
           "tools/BaseTool.java; McpToolset.java has no reserved list",
    note=(
        "No reserved-name list exists here, but callable tools enter through "
        "appendTools, whose merger throws on a duplicate name - so those names "
        "cannot be taken. In-model built-ins bypass appendTools and are not "
        "refused."
    ),
    why={
        "google_search": "in-model built-in: GoogleSearchTool appends only to "
                         "config.Tools, so appendTools never checks the name "
                         "and the framework does not refuse it",
        "google_maps": "in-model built-in: appends only to config.Tools; the "
                       "framework does not refuse it",
        "url_context": "in-model built-in: appends only to config.Tools; the "
                       "framework does not refuse it",
        "vertex_ai_search": "in-model built-in: appends only to config.Tools; "
                            "the framework does not refuse it",
        "code_execution": "in-model built-in: appends only to config.Tools; "
                          "the framework does not refuse it",
    },
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
