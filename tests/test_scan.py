"""Tests for the name comparison and the payload shapes an MCP client sees."""

import json
import subprocess
import sys

import pytest

from nameguard import frameworks
from nameguard.scan import (
    InputError,
    names_from_payload,
    payload_from_text,
    scan_names,
    scan_payload,
)


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


# ---- the input must be readable, or it is not a clean scan -----------------

def _run_stdin(text, *args):
    return subprocess.run(
        [sys.executable, "-m", "nameguard.cli", *args],
        input=text, capture_output=True, text=True,
    )


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "mcp-inspector: command not found",
        "Traceback (most recent call last):\n  File ...",
        '{"tools": [',
    ],
)
def test_cli_fails_closed_on_unreadable_stdin(text):
    """Regression: this was a fail-open, and it was the documented pipeline.

    `check -` treated anything not starting with `[` or `{` as a
    newline-separated list of names. The README documents

        mcp-inspector list-tools --json | mcp-nameguard check -

    so when the command on the left failed, its error text arrived here, became
    a one-element "name list" that matched nothing, and the tool printed
    "No collisions." and exited 0. The names were never read and the scan
    reported that nothing was wrong -- the failure the exit-code contract
    exists to prevent, in the tool that documents it.
    """
    result = _run_stdin(text, "check", "-")
    assert result.returncode == 2, result.stdout
    assert "No collisions" not in result.stdout


def test_cli_fails_closed_on_a_missing_file(tmp_path):
    result = _run("check", str(tmp_path / "nope.json"))
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_cli_fails_closed_on_a_payload_of_the_wrong_shape(tmp_path):
    f = tmp_path / "wrong.json"
    f.write_text('{"unexpected": 1}')
    result = _run("check", str(f))
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_a_plain_name_list_still_works_after_the_fix():
    """The feature this must not break: names copied by hand."""
    result = _run_stdin("get_weather\ntransfer_to_agent\n", "check", "-")
    assert result.returncode == 1
    assert "transfer_to_agent" in result.stdout


def test_payload_from_text_accepts_both_documented_forms():
    assert payload_from_text('{"tools": [{"name": "a"}]}') == {"tools": [{"name": "a"}]}
    assert payload_from_text("a\nb\n") == ["a", "b"]


@pytest.mark.parametrize("text", ["", "   \n  \n", "not json", "two words"])
def test_payload_from_text_rejects_what_it_cannot_read(text):
    with pytest.raises(InputError):
        payload_from_text(text)


def test_payload_from_text_accepts_the_separators_tool_names_use():
    names = ["tool_one", "mcp.server.name", "ns:tool", "a/b"]
    assert payload_from_text("\n".join(names)) == names


def test_payload_from_text_accepts_a_leading_separator():
    """`_tool` and `-tool` are ordinary names, so the first character is not
    special. The list used to be rejected whole, and with it every other name on
    every line, on the strength of that one leading character.
    """
    names = ["_get_weather", "-tool", ".hidden", "__dunder__", "_"]
    assert payload_from_text("\n".join(names)) == names


def test_a_leading_underscore_name_is_not_read_as_a_failed_command():
    """The rejected-name message used to assert the pipeline command had failed.

    That claim is not available from the text, and here it was also false: the
    name is legal and the command succeeded.
    """
    assert payload_from_text("_get_weather\n") == ["_get_weather"]


@pytest.mark.parametrize("text", ["null", "true", "false", "123", "-4.5"])
def test_payload_from_text_rejects_a_bare_json_scalar(text):
    """A failed `--json` command prints one of these; read as a name list each
    becomes a single tool that collides with nothing, which is a clean scan for
    a payload that was never a tool list."""
    with pytest.raises(InputError) as excinfo:
        payload_from_text(text)
    assert "not a tools/list payload" in str(excinfo.value)


def test_a_bare_json_scalar_does_not_reach_the_scanner():
    """The whole point: it must not exit 0 with "No collisions"."""
    result = _run_stdin("null\n", "check", "-")
    assert result.returncode == 2
    assert "No collisions" not in result.stdout


def test_the_rejection_message_does_not_claim_the_command_failed():
    """It cannot know that, and saying so sent the reader after the wrong bug."""
    with pytest.raises(InputError) as excinfo:
        payload_from_text("not json")
    assert "probably failed" not in str(excinfo.value)


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
    """An unguarded name must be explained as a name the framework does not refuse."""
    adk_go = frameworks.get("adk-go")
    assert "does not refuse" in adk_go.explain("google_search")


def test_generic_unguarded_fallback_names_the_framework():
    """A reserved-but-unguarded name with no bespoke reason must still say so."""
    fw = frameworks.Framework(
        key="synthetic", name="Synthetic Framework",
        reserved=frozenset({"thing"}), guarded=frozenset(),
        source="nowhere", note="n/a",
    )
    text = fw.explain("thing")
    assert "does not refuse" in text
    assert "Synthetic Framework" in text


# --------------------------------------------------------------------------
# guarded vs reserved: the distinction the tool now reports
# --------------------------------------------------------------------------

def test_guarded_is_always_a_subset_of_reserved():
    for fw in frameworks.FRAMEWORKS:
        assert fw.guarded <= fw.reserved, fw.key


def test_python_reports_the_upstream_guard_exactly():
    """Guarded is what the upstream set literally contains; the rest is the gap."""
    fw = frameworks.get("adk-python")
    assert fw.guarded == {
        "adk_request_credential", "adk_request_confirmation",
        "adk_request_input", "transfer_to_agent",
    }
    # Everything else this framework owns is unguarded, set_model_response and
    # the skill/loop tools included.
    assert "set_model_response" in fw.reserved - fw.guarded
    assert len(fw.reserved - fw.guarded) > 1


def test_go_and_java_guard_the_packed_callables_not_the_builtins():
    """Neither has a reserved-name list, but neither is undefended either.

    A previous revision of this file reported Go and Java as guarding nothing,
    on the strength of there being no reserved-name list to cite. That was
    wrong: a server cannot take a name the framework packs, because PackTool
    (Go) and appendTools (Java) refuse the duplicate, so the request fails
    instead. What actually stays open is the in-model built-ins, which are
    appended straight to config.Tools and never pass through either check.
    """
    builtins = {"google_search", "google_maps_grounding", "url_context",
                "code_execution"}

    go = frameworks.get("adk-go")
    assert "set_model_response" in go.guarded          # packed via PackTool
    assert "transfer_to_agent" in go.guarded
    assert builtins <= go.reserved - go.guarded        # the real gap
    assert "PackTool" in go.source

    java = frameworks.get("adk-java")
    assert "set_model_response" in java.guarded        # appendTools throws
    assert "transfer_to_agent" in java.guarded
    assert {"google_search", "google_maps", "url_context",
            "vertex_ai_search", "code_execution"} <= java.reserved - java.guarded
    assert "appendTools" in java.source


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
    """Go refuses the packed callable, and leaves the built-in name open."""
    go = frameworks.get("adk-go")
    (packed,) = scan_names(["set_model_response"], targets=[go])
    assert packed.as_dict()["status"] == "guarded"

    (builtin,) = scan_names(["google_search"], targets=[go])
    assert builtin.as_dict()["status"] == "unguarded"


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


def test_framework_shipped_tools_are_reserved_in_every_framework():
    """Skill and loop tools are framework-owned in all three ports.

    None of them were in any list. The sets had grown by hand, one reported name
    at a time, and nothing ever enumerated the tools the frameworks actually
    ship -- so three successive corrections each found more gaps. This test asks
    the question the hand-edits did not.
    """
    for name in ("exit_loop", "list_skills", "load_skill", "load_skill_resource"):
        for fw in frameworks.FRAMEWORKS:
            assert name in fw.reserved, f"{name!r} missing from {fw.key}"
