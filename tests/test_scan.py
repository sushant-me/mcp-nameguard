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
    assert "UNGUARDED" in result.stdout
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
    """A guarded name with no bespoke reason is explained by the framework note."""
    adk_python = frameworks.get("adk-python")
    assert adk_python.explain("adk_request_input") == adk_python.note


def test_unguarded_name_is_explained_as_unguarded():
    """The fallback for an unguarded name must say the framework does not refuse it."""
    adk_go = frameworks.get("adk-go")
    text = adk_go.explain("google_search")
    assert "does not refuse" in text
    assert adk_go.name in text


# --------------------------------------------------------------------------
# guarded vs reserved: the distinction the tool now reports
# --------------------------------------------------------------------------

def test_guarded_is_always_a_subset_of_reserved():
    for fw in frameworks.FRAMEWORKS:
        assert fw.guarded <= fw.reserved, fw.key


def test_python_reports_the_single_unguarded_framework_owned_name():
    fw = frameworks.get("adk-python")
    assert fw.guarded == {
        "adk_request_credential", "adk_request_confirmation",
        "adk_request_input", "transfer_to_agent",
    }
    assert fw.reserved - fw.guarded == {"set_model_response"}


def test_frameworks_without_an_upstream_guard_report_nothing_guarded():
    """Go and Java have no reserved-name guard upstream; that must be visible.

    Reporting these names as *reserved* without saying they are unguarded would
    describe a defence that does not exist.
    """
    for key in ("adk-go", "adk-java"):
        fw = frameworks.get(key)
        assert fw.guarded == frozenset(), key
        assert fw.reserved, key
        assert "no guard" in fw.source.lower() or "No guard" in fw.note, key


def test_status_is_reported_per_finding():
    guarded, unguarded = scan_names(
        ["transfer_to_agent", "set_model_response"],
        targets=[frameworks.get("adk-python")],
    )
    by_tool = {f.tool: f.status for f in [guarded, unguarded]}
    assert by_tool == {
        "transfer_to_agent": "guarded",
        "set_model_response": "unguarded",
    }


def test_json_output_carries_the_status():
    (finding,) = scan_names(["set_model_response"], targets=[frameworks.get("adk-go")])
    assert finding.as_dict()["status"] == "unguarded"


def test_a_guarded_name_outside_reserved_is_rejected():
    """A contradiction must fail at construction, not produce an impossible status."""
    with pytest.raises(ValueError, match="guarded names missing from reserved"):
        frameworks.Framework(
            key="broken", name="Broken", reserved=frozenset({"a"}),
            guarded=frozenset({"b"}), source="x/y.py", note="n",
        )


# --------------------------------------------------------------------------
# Each framework's list must come from that framework
# --------------------------------------------------------------------------

def test_the_go_and_java_lists_are_not_interchangeable():
    """They are different codebases with different tool sets.

    An earlier revision carried one list into both. That is how a name defined
    only in one framework came to be reported as a collision against the other,
    in both directions: a false positive for the framework that lacks it, and a
    blind spot for the name it actually uses.
    """
    go = frameworks.get("adk-go").reserved
    java = frameworks.get("adk-java").reserved
    assert go != java
    assert go - java, "at least one name must be Go-only"
    assert java - go, "at least one name must be Java-only"


def test_go_does_not_claim_names_it_does_not_define():
    go = frameworks.get("adk-go").reserved
    # `google_maps` is the Java tool name; Go's grounded-maps tool is built as
    # `google_maps_grounding`. Go has no vertex_ai_search at all.
    assert "google_maps" not in go
    assert "vertex_ai_search" not in go
    assert "google_maps_grounding" in go


def test_java_does_not_claim_names_it_does_not_define():
    java = frameworks.get("adk-java").reserved
    # Neither of these exists anywhere in the Java sources.
    assert "finish_task" not in java
    assert "task_completed" not in java
    # Java-specific names, absent from Go.
    assert "google_maps" in java
    assert "vertex_ai_search" in java


def test_java_memory_tool_uses_the_java_spelling():
    """`loadMemory`, not the `load_memory` the other ports use.

    Java derives a tool's name from the method name when there is no
    @Annotations.Schema on the method, which is the case for LoadMemoryTool.
    Getting this wrong is a silent gap: the guard would never see the name the
    framework actually puts on the wire.
    """
    java = frameworks.get("adk-java").reserved
    assert "loadMemory" in java
    assert "load_memory" not in java


def test_names_common_to_both_frameworks_are_shared():
    go = frameworks.get("adk-go").reserved
    java = frameworks.get("adk-java").reserved
    for name in ("set_model_response", "transfer_to_agent", "google_search",
                 "url_context", "code_execution", "load_artifacts"):
        assert name in go, name
        assert name in java, name
