# mcp-nameguard

[![CI](https://github.com/sushant-me/mcp-nameguard/actions/workflows/ci.yml/badge.svg)](https://github.com/sushant-me/mcp-nameguard/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.11%20%7C%203.13-blue)](https://github.com/sushant-me/mcp-nameguard/actions/workflows/ci.yml)

Check the tool names an MCP server advertises against the names agent
frameworks **put on the wire themselves**.

A framework-owned name is one the framework itself registers. When a server
advertises the same name the two tools compete for it — and depending on the
framework the server's tool can end up holding it, so a call meant for the
framework is dispatched to the server instead.

Findings are reported in two grades, because *"the framework refuses this name"*
and *"the framework owns this name and does not defend it"* are different facts,
and only one of them is a server breaking a rule:

| grade | meaning |
|---|---|
| `GUARDED` | the framework refuses the name at MCP registration — a server advertising it has broken a documented rule |
| `UNGUARDED` | the framework puts the name on the wire and does **not** refuse it, so a server can simply take it |

`UNGUARDED` is the more actionable of the two, and it is the reason this tool
reports a framework's gaps rather than only its rules.

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

Point it at a live server (stdio or HTTP), a `tools/list` result, a JSON list, or a file of names:

```bash
# Ask a running MCP server for its tools, before you wire it into an agent:
$ mcp-nameguard check --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"

# Remote servers speak HTTP:
$ mcp-nameguard check --http https://example.com/mcp --header "Authorization: Bearer …"

# Or check a saved tools/list payload:
$ mcp-nameguard check tools.json
UNGUARDED  set_model_response  (Google ADK (Python))
           src/google/adk/tools/mcp_tool/mcp_tool.py, _RESERVED_TOOL_NAMES
           Injected by the output-schema processor whenever output_schema is
           set alongside other tools (flows/llm_flows/prompt/_schema.py) and
           read back by name in base_llm_flow.py. Request processors run
           before tool resolution, so a server advertising this name is the
           last-wins survivor.

GUARDED    transfer_to_agent  (Google ADK (Python))
           src/google/adk/tools/mcp_tool/mcp_tool.py, _RESERVED_TOOL_NAMES
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

Stdin accepts either a JSON payload or one tool name per line, and the two are
told apart by shape: a name list is names and separators only. That is enough to
refuse a shell message or a traceback, and it is *not* enough to refuse a single
bare word, which is a legal name and also what a failed `--json` command
sometimes prints. Complete JSON values are the exception and are classified -
`null`, `true`, `false` and a bare number are rejected rather than read as a tool
named `null`. For a pipeline, prefer `--json`, where the payload is unambiguous.

### Exit codes

| code | meaning |
|---|---|
| `0` | no collisions |
| `1` | collisions found |
| `2` | the server or input could not be read |

Code `2` matters: a server that fails to start, times out, or answers with a
malformed `tools/list` is reported as an **error**, never as an empty — and
therefore apparently clean — result. A checker that fails open is worse than no
checker.

## Supported frameworks

| key | framework | guarded / owned | transcribed from |
|---|---|---|---|
| `adk-python` | Google ADK (Python) | **4 / 9** | `src/google/adk/tools/mcp_tool/mcp_tool.py`, `_RESERVED_TOOL_NAMES` |
| `adk-go` | Google ADK (Go) | **10 / 14** | `tool/toolutils/toolutils.go` — `PackTool` refuses a duplicate name |
| `adk-java` | Google ADK (Java) | **8 / 13** | `models/LlmRequest.java` — `appendTools` merger throws on a duplicate |

The `guarded` column is what the framework actually refuses today, transcribed
from its source. The total is every name it puts on the wire. Where the two
differ, the difference is a name a server can currently take.

**Neither Go nor Java has a reserved-name list, and an earlier revision of this
file reported that as "nothing is guarded". That was wrong**, and it is worth
saying plainly because the mistake is easy to repeat: absence of a *list* is not
absence of a *check*. A server cannot take a name the framework packs, because a
duplicate is refused when the request is built — `toolutils.PackTool` returns
`duplicate tool: %q`, and Java's `appendTools` merger throws
`Duplicate tool name`. Both fail closed, so the packed callables are guarded.

What stays open is the **in-model built-ins** (`google_search`,
`google_maps_grounding`, `url_context`, `code_execution`). `geminitool.setTool`
in Go, and `GoogleSearchTool` / `GoogleMapsTool` / `UrlContextTool` /
`VertexAiSearchTool` / `BuiltInCodeExecutionTool` in Java, append straight to
`config.Tools` and never pass through either check — so a server advertising one
is accepted, and both tools end up advertised under the same name. On
[google/adk-go#1606](https://github.com/google/adk-go/pull/1606) a maintainer
measured the consequence: the model became non-deterministic about which of the
two it called. That PR is withdrawn — refusing the server's tool is a policy
trade-off rather than the fix — but the measurement is what corrected this
table.

**The Go and Java lists are different, and deliberately so.** They are separate
codebases with separate tool sets, and an earlier revision of this file carried
one list into both — which produced false positives against whichever framework
lacked a name, and a blind spot for the name it used instead. Go has no
`google_maps` tool (its grounded-maps tool is `google_maps_grounding`, built by
`internal/configurable/configurable_utils.go`) and no `vertex_ai_search`; Java
has no `finish_task` or `task_completed`, and spells its memory tool
`loadMemory` rather than the other ports' `load_memory`. Tests assert the two sets are not
interchangeable.

Adding a framework is a data edit in `nameguard/frameworks.py`; a `guarded` name
that is not also `reserved` raises at import rather than reporting a status that
cannot exist.

## Has it found anything?

Being straight about this, because a checker that cannot fail is not worth
running. Every line below is a live `tools/list` against a real server, not a
static reading of source, and you can reproduce the whole table:

```bash
python scripts/reality_check.py --markdown
```

Hand-picked examples cannot falsify anything — the first version of this table
cited three servers I had chosen myself. The script exists so the set is fixed
and checkable rather than illustrative.

| server | tools | result |
|---|---|---|
| `server-filesystem` | 14 | no collisions |
| `server-everything` | 13 | no collisions |
| `server-memory` | 9 | no collisions |
| `server-sequential-thinking` | 1 | no collisions |
| `@google-cloud/storage-mcp` | 15 | no collisions |
| `firecrawl-mcp` | 25 | no collisions |
| `chrome-devtools-mcp` | 29 | no collisions |
| `@google-cloud/observability-mcp` | 13 | no collisions |
| `@upstash/context7-mcp` | 2 | no collisions |

**121 tools across 9 servers, zero collisions.** The Google Cloud servers are the
interesting ones to have clean: they are the implementations most plausibly
tempted to name a tool `google_search`, and they do not.

Five more servers could not be read — `mcp-server-gsc`,
`@sentry/mcp-server`, `@google-cloud/gcloud-mcp`,
`mcp-server-google-search-console`, `@fdcicyber/google-search-mcp` — all failing
or timing out because they need credentials this machine does not have. **Each
was reported as an error, not as a clean scan.** That is the exit-code-2 design
working on real, failing servers rather than on a fixture.

So treat this as **preventive**, not as a report of a known-broken situation. The
collision it guards against is real — `google/adk-python` shipped a guard for
exactly this and was still missing a name from it
([#7144](https://github.com/google/adk-python/issues/7144)) — but every server I
have been able to read names its tools sensibly. The check is cheap insurance at
the moment you add a server, which is the moment nothing else checks.

## Scope, honestly

* Talking to a server is deliberately minimal: `initialize`,
  `notifications/initialized`, `tools/list`, over stdio or Streamable HTTP. It
  does not call any tool and does not read tool output. Reply framing in plain
  JSON and in SSE is accepted; the older HTTP+SSE transport is not supported.
* It checks **name collisions only**. It does not read tool descriptions, so it
  will not catch prompt injection or tool poisoning hidden in prose — those are
  different problems with different tools.
* The server is treated as **untrusted input**. Replies are capped at 8 MiB — HTTP bodies and
  stdio lines alike — and refused above that rather than buffered. A scanner that dies on the
  server it was asked to inspect fails open: it reports nothing about a server that may be
  hostile, which is the one outcome this tool must not produce.
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

82 tests covering the comparison, the guarded/unguarded split and its
import-time contradiction check, every payload shape, both transports driven by
stub servers that banner, error, hang, return HTTP 500, send SSE, answer
malformed, and send a reply too large to read, the failure mode where a bad
response must not look like a clean scan, the CLI exit codes, and the per-name
explanation.

## Licence

MIT — see [LICENSE](LICENSE).

Authored by [Sushant Poudel](https://github.com/sushant-me).
