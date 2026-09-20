"""Tests for the stdio MCP client, driven by a stub server (no network)."""

import sys
from pathlib import Path

import pytest

from nameguard.mcp_stdio import McpStdioError, list_tools_stdio

STUB = str(Path(__file__).parent / "fixtures" / "stub_mcp_server.py")


def _cmd(mode="normal"):
    return f"{sys.executable} {STUB} {mode}"


def test_lists_tool_names_from_a_live_server():
    names = list_tools_stdio(_cmd(), timeout_s=15)
    assert names == ["get_weather", "transfer_to_agent", "set_model_response"]


def test_skips_a_non_json_banner():
    """Servers occasionally print a banner; protocol frames are JSON."""
    names = list_tools_stdio(_cmd("banner"), timeout_s=15)
    assert "transfer_to_agent" in names


def test_propagates_a_json_rpc_error():
    with pytest.raises(McpStdioError) as excinfo:
        list_tools_stdio(_cmd("error"), timeout_s=15)
    assert "not supported" in str(excinfo.value)


def test_a_server_that_exits_is_an_error_not_an_empty_list():
    """An empty result would look like a clean scan, which would be a false negative."""
    with pytest.raises(McpStdioError):
        list_tools_stdio(_cmd("exit"), timeout_s=15)


def test_a_reply_without_a_tool_array_is_an_error():
    with pytest.raises(McpStdioError):
        list_tools_stdio(_cmd("broken"), timeout_s=15)


def test_a_silent_server_times_out_rather_than_hanging():
    with pytest.raises(McpStdioError) as excinfo:
        list_tools_stdio(_cmd("quiet"), timeout_s=3)
    assert "within" in str(excinfo.value)


def test_missing_command_is_reported_clearly():
    with pytest.raises(McpStdioError) as excinfo:
        list_tools_stdio("definitely-not-a-real-command-xyz")
    assert "not found" in str(excinfo.value)


def test_empty_command_is_rejected():
    with pytest.raises(McpStdioError):
        list_tools_stdio("   ")


def test_a_server_that_logs_to_stderr_still_answers():
    """The MCP spec designates stderr for logging, so logging is not a failure.

    This server is the `normal` one with log output added; the only variable is
    how much it writes. Piping stderr without reading it blocks the server in
    `write()` once the pipe buffer is full, and the client then reports a server
    that already replied as one that never did.
    """
    names = list_tools_stdio(_cmd("chatty"), timeout_s=15)
    assert names == ["get_weather", "transfer_to_agent", "set_model_response"]


def test_a_small_log_is_below_the_pipe_buffer_and_answers(monkeypatch):
    """The paired fixture for the test above: the same server, same protocol
    traffic, and only the log volume changed.

    Small logs fit in the pipe buffer, so they always worked; large ones did not.
    Pinning both is what shows the buffer, and not the server, was deciding.
    """
    monkeypatch.setenv("STUB_CHATTY_LINES", "200")
    names = list_tools_stdio(_cmd("chatty"), timeout_s=15)
    assert names == ["get_weather", "transfer_to_agent", "set_model_response"]


def test_a_failure_quotes_what_the_server_said_on_stderr():
    """The reason a server refused is already in hand; report it, not just that
    nothing arrived."""
    with pytest.raises(McpStdioError) as excinfo:
        list_tools_stdio(_cmd("noisy-fail"), timeout_s=15)
    message = str(excinfo.value)
    assert "config file not found" in message
    assert "stderr" in message


def test_an_oversized_message_is_refused_not_buffered(monkeypatch):
    """Same reasoning as the HTTP cap: the subprocess is not trusted, so a line that would grow
    without bound is refused rather than read into memory."""
    from nameguard import mcp_stdio
    monkeypatch.setattr(mcp_stdio, "MAX_MESSAGE_BYTES", 64 * 1024)
    with pytest.raises(McpStdioError) as excinfo:
        list_tools_stdio(_cmd("huge"), timeout_s=15)
    assert "larger than" in str(excinfo.value)
