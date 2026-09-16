"""Tests for the name comparison and the payload shapes an MCP client sees."""

import json
import subprocess
import sys

import pytest

from nameguard import frameworks
from nameguard.scan import names_from_payload, scan_names, scan_payload


def test_detects_a_reserved_name_across_every_framework_that_reserves_it():
    findings = scan_names(["set_model_response"])
    keys = {f.framework.key for f in findings}
    assert keys == {"adk-python", "adk-go", "adk-java"}


def test_a_safe_name_produces_nothing():
    assert scan_names(["get_weather", "search_flights"]) == []


def test_transfer_to_agent_is_caught():
    findings = scan_names(["transfer_to_agent"])
    assert findings and all(f.tool == "transfer_to_agent" for f in findings)


def test_scanning_can_be_limited_to_one_framework():
    findings = scan_names(["set_model_response"], [frameworks.get("adk-go")])
    assert [f.framework.key for f in findings] == ["adk-go"]


def test_results_are_sorted_and_deduplicated():
    findings = scan_names(["b", "a", "a", "transfer_to_agent", "a"])
    assert findings == sorted(findings, key=lambda f: (f.tool, f.framework.key))
    assert len([f for f in findings if f.tool == "a"]) == 0


# ---- payload shapes -------------------------------------------------------

def test_accepts_a_tools_list_result():
    payload = {"tools": [{"name": "get_weather"}, {"name": "transfer_to_agent"}]}
    assert names_from_payload(payload) == ["get_weather", "transfer_to_agent"]

    findings = scan_payload(payload)
    # One finding per framework that reserves the name, so the report can say
    # which framework is actually affected.
    assert {f.tool for f in findings} == {"transfer_to_agent"}
    assert {f.framework.key for f in findings} == {"adk-python", "adk-go", "adk-java"}
    assert all(f.tool != "get_weather" for f in findings)


def test_accepts_a_bare_list_of_strings():
    assert names_from_payload(["a", "b"]) == ["a", "b"]


def test_accepts_a_single_tool_object():
    assert names_from_payload({"name": "transfer_to_agent"}) == ["transfer_to_agent"]


@pytest.mark.parametrize("bad", [42, "not-a-payload", {"unexpected": 1}, [{"no_name": 1}]])
def test_malformed_input_raises_instead_of_looking_clean(bad):
    with pytest.raises(TypeError):
        names_from_payload(bad)


# ---- CLI ------------------------------------------------------------------

def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "nameguard.cli", *args],
        capture_output=True, text=True,
    )


def test_cli_exits_1_on_a_collision(tmp_path):
    f = tmp_path / "tools.json"
    f.write_text(json.dumps({"tools": [{"name": "set_model_response"}]}))
    result = _run("check", str(f))
    assert result.returncode == 1
    assert "COLLISION" in result.stdout
    assert "set_model_response" in result.stdout


def test_cli_exits_0_when_clean(tmp_path):
    f = tmp_path / "tools.json"
    f.write_text(json.dumps({"tools": [{"name": "get_weather"}]}))
    result = _run("check", str(f))
    assert result.returncode == 0
    assert "No collisions." in result.stdout


def test_cli_json_output_is_parseable(tmp_path):
    f = tmp_path / "tools.json"
    f.write_text(json.dumps({"tools": [{"name": "transfer_to_agent"}]}))
    result = _run("check", str(f), "--json")
    data = json.loads(result.stdout)
    assert data[0]["tool"] == "transfer_to_agent"
    assert data[0]["framework"] in {"adk-python", "adk-go", "adk-java"}


def test_cli_reads_a_plain_name_list(tmp_path):
    f = tmp_path / "names.txt"
    f.write_text("get_weather\ntransfer_to_agent\n")
    result = _run("check", str(f))
    assert result.returncode == 1
    assert "transfer_to_agent" in result.stdout


def test_cli_frameworks_lists_all():
    result = _run("frameworks")
    assert result.returncode == 0
    for key in ("adk-python", "adk-go", "adk-java"):
        assert key in result.stdout


def test_every_framework_cites_a_source_file():
    for fw in frameworks.FRAMEWORKS:
        assert fw.source and "/" in fw.source, fw.key
        assert fw.note, fw.key
        assert fw.reserved, fw.key


def test_explanation_is_specific_to_the_name():
    """A generic reserved name must not be explained with another name's story."""
    adk_python = frameworks.get("adk-python")
    assert "output-schema" in adk_python.explain("set_model_response")
    assert "output-schema" not in adk_python.explain("transfer_to_agent")
    assert adk_python.explain("transfer_to_agent") != adk_python.explain("set_model_response")


def test_explanation_falls_back_to_the_framework_note():
    adk_go = frameworks.get("adk-go")
    assert adk_go.explain("google_maps") == adk_go.note
