# mcp-nameguard

Check the tool names an MCP server advertises against the names agent
frameworks **reserve for their own tools**.

A reserved name is one the framework itself puts on the wire. When a server
advertises the same name, the two tools compete for it — and depending on the
framework the server's tool can end up holding it, so a call meant for the
framework is dispatched to the server instead.

This is a [cross-server tool shadowing](https://mcpsafe.io/threats/MCP-046)
check, done as a **lookup against the frameworks' own source**, not a heuristic.

## Why this exists

`google/adk-python` ships an explicit guard for exactly this problem. Its
comment states the invariant:

```python
# Tool names the framework itself puts on the wire. A server advertising one of
# these would have its tool dispatched in place of the framework's own, so the
# name is refused at registration.
_RESERVED_TOOL_NAMES = frozenset({
    REQUEST_EUC_FUNCTION_CALL_NAME,             # adk_request_credential
    REQUEST_CONFIRMATION_FUNCTION_CALL_NAME,    # adk_request_confirmation
    REQUEST_INPUT_FUNCTION_CALL_NAME,           # adk_request_input
    transfer_to_agent.__name__,                 # transfer_to_agent
})
```

`set_model_response` is a framework-owned wire name too — the output-schema
processor injects `SetModelResponseTool` whenever `output_schema` is set
alongside other tools, the framework tells the model to answer *through that
name*, and `base_llm_flow.py` reads the result back **by that name**. It was
missing from the set, and because `LlmRequest.append_tools` resolves a duplicate
name by last-wins with only a warning, a server advertising it could receive the
agent's structured final answer.

I reported that as [google/adk-python#7144](https://github.com/google/adk-python/issues/7144)
and sent the fix in [#7145](https://github.com/google/adk-python/pull/7145).
This tool exists so the *next* server can be checked before it is wired in,
rather than after.

## Install

```bash
pip install -e .
```

No runtime dependencies, Python 3.9+.

## Use

Point it at a `tools/list` result, a JSON list, or a file of names:

```bash
$ mcp-nameguard check tools.json
COLLISION  set_model_response  (Google ADK (Python))
           reserved in src/google/adk/tools/mcp_tool/mcp_tool.py
           Injected by the output-schema processor whenever output_schema is
           set alongside other tools (flows/llm_flows/prompt/_schema.py) and
           read back by name in base_llm_flow.py. It was missing from
           _RESERVED_TOOL_NAMES until google/adk-python#7144.

COLLISION  transfer_to_agent  (Google ADK (Python))
           reserved in src/google/adk/tools/mcp_tool/mcp_tool.py
           The framework's own agent-transfer tool; also the name a server
           would need to hijack a hand-off.
```

Exit code is `1` when anything collides, so it works as a CI gate:

```bash
mcp-nameguard check tools.json --json
mcp-nameguard check tools.json --framework adk-python
mcp-nameguard list --framework adk-go
mcp-nameguard frameworks
```

`-` reads from stdin:

```bash
mcp-inspector list-tools --json | mcp-nameguard check -
```

## Supported frameworks

| key | framework | names | transcribed from |
|---|---|---|---|
| `adk-python` | Google ADK (Python) | 5 | `src/google/adk/tools/mcp_tool/mcp_tool.py` |
| `adk-go` | Google ADK (Go) | 11 | `tool/mcptoolset/set.go` |
| `adk-java` | Google ADK (Java) | 11 | `core/src/main/java/com/google/adk/tools/mcp/McpToolset.java` |

Every list is transcribed from the framework's own source and cites the file it
came from; nothing is inferred. Adding a framework is a data edit in
`nameguard/frameworks.py`.

## Scope, honestly

* It checks **name collisions only**. It does not read tool descriptions, so it
  will not catch prompt injection or tool poisoning hidden in prose — those are
  different problems with different tools.
* A collision is not automatically exploitable. It means the framework and the
  server disagree about who owns a name, which is worth resolving before
  deployment; whether it is exploitable depends on the framework's dispatch
  behaviour.
* Coverage is currently the ADK family, because those are the lists I could
  verify line by line. Other frameworks are welcome as pull requests with a
  source citation.

## Tests

```bash
python -m pytest tests/
```

20 tests covering the comparison, every payload shape, the failure mode where
malformed input must not look like a clean scan, the CLI exit codes, and the
per-name explanation.

## Licence

MIT — see [LICENSE](LICENSE).

Authored by [Sushant Poudel](https://github.com/sushant-me).
