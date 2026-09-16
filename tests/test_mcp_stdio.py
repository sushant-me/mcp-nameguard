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
