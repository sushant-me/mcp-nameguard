"""Tests for the Streamable HTTP client, driven by a stub server (no network)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from nameguard.mcp_http import McpHttpError, list_tools_http

TOOLS = ["get_weather", "transfer_to_agent", "set_model_response"]


class _Handler(BaseHTTPRequestHandler):
    mode = "json"
    seen_headers: list[dict] = []

    def log_message(self, *args):  # keep pytest output clean
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        message = json.loads(self.rfile.read(length) or b"{}")
        type(self).seen_headers.append(dict(self.headers))

        method = message.get("method")
        msg_id = message.get("id")

        if method == "initialize":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Mcp-Session-Id", "sess-1")
            self.end_headers()
            self.wfile.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {
                "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "stub", "version": "0"}}}).encode())
        elif method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
        elif method == "tools/list":
            if type(self).mode == "http500":
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b'{"error":"boom"}')
                return
            if type(self).mode == "sse":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                payload = {"jsonrpc": "2.0", "id": msg_id,
                           "result": {"tools": [{"name": n} for n in TOOLS]}}
                self.wfile.write(f"event: message\ndata: {json.dumps(payload)}\n\n".encode())
                return
            if type(self).mode == "huge":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"x" * (256 * 1024))
                return
            if type(self).mode == "huge-declared":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(64 * 1024 * 1024))
                self.end_headers()
                self.wfile.write(b"{}")
                return
            if type(self).mode == "broken":
                body = {"jsonrpc": "2.0", "id": msg_id, "result": {"nope": []}}
            elif type(self).mode == "garbage":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"not json at all")
                return
            else:
                body = {"jsonrpc": "2.0", "id": msg_id,
                        "result": {"tools": [{"name": n} for n in TOOLS]}}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")


@pytest.fixture()
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    _Handler.seen_headers = []
    yield f"http://127.0.0.1:{httpd.server_address[1]}/mcp"
    httpd.shutdown()
    httpd.server_close()


def test_lists_tools_over_http(server):
    _Handler.mode = "json"
    assert list_tools_http(server, timeout_s=10) == TOOLS


def test_accepts_an_sse_reply(server):
    """The spec allows the same JSON in an event stream."""
    _Handler.mode = "sse"
    assert list_tools_http(server, timeout_s=10) == TOOLS


def test_sends_the_session_id_returned_by_initialize(server):
    _Handler.mode = "json"
    list_tools_http(server, timeout_s=10)
    tools_call = [h for h in _Handler.seen_headers if h.get("Mcp-Session-Id")]
    assert tools_call, "the session id from initialize was not reused"


def test_passes_extra_headers(server):
    _Handler.mode = "json"
    list_tools_http(server, timeout_s=10, headers={"Authorization": "Bearer t"})
    assert any(h.get("Authorization") == "Bearer t" for h in _Handler.seen_headers)


def test_html_error_status_is_reported(server):
    _Handler.mode = "http500"
    with pytest.raises(McpHttpError) as excinfo:
        list_tools_http(server, timeout_s=10)
    assert "HTTP 500" in str(excinfo.value)


def test_non_json_body_is_an_error_not_an_empty_list(server):
    _Handler.mode = "garbage"
    with pytest.raises(McpHttpError):
        list_tools_http(server, timeout_s=10)


def test_result_without_a_tool_array_is_an_error(server):
    _Handler.mode = "broken"
    with pytest.raises(McpHttpError) as excinfo:
        list_tools_http(server, timeout_s=10)
    assert "tool array" in str(excinfo.value)


def test_unreachable_server_is_reported_clearly():
    with pytest.raises(McpHttpError) as excinfo:
        list_tools_http("http://127.0.0.1:9/mcp", timeout_s=3)
    assert "could not reach" in str(excinfo.value) or "failed" in str(excinfo.value)


def test_an_oversized_reply_is_refused_not_buffered(server, monkeypatch):
    """A hostile server must not be able to kill the scanner that is inspecting it.

    This client exists to look at MCP servers it does not trust, so an unbounded read is a denial
    of service against the scanner: the process dies on the reply before it can report anything,
    which is failing open against the exact adversary the tool was pointed at.
    """
    from nameguard import mcp_http
    monkeypatch.setattr(mcp_http, "MAX_RESPONSE_BYTES", 4096)
    _Handler.mode = "huge"
    with pytest.raises(McpHttpError) as excinfo:
        list_tools_http(server, timeout_s=10)
    assert "more than" in str(excinfo.value)


def test_an_announced_oversized_reply_is_refused_before_reading(server, monkeypatch):
    """Content-Length is refused up front, so the bytes are never pulled into memory at all."""
    from nameguard import mcp_http
    monkeypatch.setattr(mcp_http, "MAX_RESPONSE_BYTES", 4096)
    _Handler.mode = "huge-declared"
    with pytest.raises(McpHttpError) as excinfo:
        list_tools_http(server, timeout_s=10)
    assert "announced" in str(excinfo.value)


def test_a_normal_reply_still_fits_under_the_cap(server):
    """The cap must not be so eager that a legitimate server is refused."""
    _Handler.mode = "json"
    assert list_tools_http(server, timeout_s=10) == TOOLS
