"""Ask a remote MCP server for its tool list over Streamable HTTP.

Most MCP deployments that are not local processes speak HTTP rather than stdio,
so a checker that only understands stdio misses them. This speaks the same three
messages as the stdio client, over POST, and accepts either reply framing the
spec allows: a plain JSON body, or an SSE stream carrying the same JSON.

Same policy as the stdio client: anything we cannot read becomes a typed error,
never an empty tool list, because an empty list reports "no collisions" for a
server that was never actually read.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .mcp_stdio import CLIENT_INFO, PROTOCOL_VERSION, McpError

__all__ = ["McpHttpError", "list_tools_http"]

# The spec requires the client to accept both framings.
_ACCEPT = "application/json, text/event-stream"

# A reply larger than this is refused rather than buffered. This client is pointed at servers it
# does not trust BY DESIGN - inspecting a possibly-hostile MCP server is the tool's whole purpose -
# so an unbounded read is a denial of service against the scanner: the process is killed by the
# reply before it can report anything about the server. A scanner that dies on the server it was
# asked to inspect has failed open, which is the one outcome it must not produce.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class McpHttpError(McpError):
    """Failure talking to an MCP server over HTTP."""


def _decode(body: str, content_type: str, want_id: int) -> dict[str, Any]:
    """Pull the JSON-RPC reply with `want_id` out of either framing."""
    body = body.strip()
    if not body:
        raise McpHttpError("the server sent an empty body")

    if "text/event-stream" in content_type or body.startswith("event:") or body.startswith("data:"):
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            chunk = line[len("data:"):].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                message = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and message.get("id") == want_id:
                return message
        raise McpHttpError("the event stream contained no reply to our request")

    try:
        message = json.loads(body)
    except json.JSONDecodeError:
        raise McpHttpError("the server did not send JSON") from None
    if isinstance(message, list):
        for entry in message:
            if isinstance(entry, dict) and entry.get("id") == want_id:
                return entry
        raise McpHttpError("the JSON batch contained no reply to our request")
    if not isinstance(message, dict):
        raise McpHttpError("the server sent an unexpected JSON shape")
    return message


def _result(message: dict[str, Any], what: str) -> dict[str, Any]:
    if "error" in message:
        err = message["error"]
        detail = err.get("message") if isinstance(err, dict) else err
        raise McpHttpError(f"the server returned an error for {what}: {detail}")
    result = message.get("result")
    if not isinstance(result, dict):
        raise McpHttpError(f"the {what} reply had no result object")
    return result


def list_tools_http(
    url: str,
    timeout_s: float = 20.0,
    headers: dict[str, str] | None = None,
) -> list[str]:
    """Return the tool names a Streamable HTTP MCP server advertises.

    `headers` carries any auth the deployment needs (for example an
    `Authorization` value); it is applied to every request.
    """
    # Auth is per-deployment, so extra headers are simply merged in.
    extra = headers or {}

    def post(payload: dict[str, Any], session: str | None):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": _ACCEPT,
                "MCP-Protocol-Version": PROTOCOL_VERSION,
                **({"Mcp-Session-Id": session} if session else {}),
                **extra,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                # Refuse up front when the server announces an oversized body, so those bytes are
                # never pulled into memory at all.
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    try:
                        if int(declared) > MAX_RESPONSE_BYTES:
                            raise McpHttpError(
                                f"the server announced a {declared}-byte reply, over the "
                                f"{MAX_RESPONSE_BYTES}-byte limit"
                            )
                    except ValueError:
                        pass  # a malformed Content-Length is not a reason to drop the cap
                # The cap on the read is kept regardless, because the header is advisory: it can be
                # absent, wrong, or a lie. Reading one byte past the limit is how overflow is seen.
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise McpHttpError(
                        f"the server replied with more than {MAX_RESPONSE_BYTES} bytes"
                    )
                return (
                    raw.decode("utf-8", errors="replace"),
                    response.headers.get("Mcp-Session-Id") or session,
                    (response.headers.get("Content-Type") or "").lower(),
                )
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:  # pragma: no cover
                pass
            raise McpHttpError(
                f"the server returned HTTP {exc.code}{f': {detail}' if detail else ''}"
            ) from None
        except urllib.error.URLError as exc:
            raise McpHttpError(f"could not reach {url}: {exc.reason}") from None
        except (TimeoutError, OSError) as exc:
            raise McpHttpError(f"request to {url} failed: {exc}") from None

    body, session, content_type = post({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        },
    }, None)
    _result(_decode(body, content_type, 1), "initialize")

    # A notification may be answered with 202 and no body; a server that
    # rejects it is still usable, so a failure here is not fatal.
    try:
        post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    except McpHttpError:
        pass

    body, _, content_type = post(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session
    )
    result = _result(_decode(body, content_type, 2), "tools/list")

    tools = result.get("tools")
    if not isinstance(tools, list):
        raise McpHttpError("the tools/list result did not contain a tool array")

    names: list[str] = []
    for entry in tools:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
        else:
            raise McpHttpError(f"a tool entry had no string name: {entry!r}")
    return names
