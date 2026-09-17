"""Ask a live MCP server for its tool list over stdio.

The point of a name-collision check is to run it *before* wiring a server into
an agent, and at that moment the usual input is a command, not a saved
`tools/list` payload. This module speaks just enough of the protocol to get the
names: `initialize`, the `initialized` notification, then `tools/list`.

Deliberately narrow: no third-party SDK, one request at a time, and every
failure resolved into a typed error rather than a hang.
"""

from __future__ import annotations

import json
import queue
import shlex
import subprocess
import threading
from collections import deque
from typing import Any

from ._version import __version__

__all__ = ["McpError", "McpStdioError", "list_tools_stdio", "PROTOCOL_VERSION"]

PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "mcp-nameguard", "version": __version__}


class McpError(RuntimeError):
    """Base class: the server could not be asked for its tools, or answered
    unusably. Every transport raises a subclass so the CLI can report a reason
    instead of a result."""


class McpStdioError(McpError):
    """Failure talking to an MCP server over stdio."""


class _Reader(threading.Thread):
    """Drains stdout on its own thread so a silent server cannot block us."""

    daemon = True

    def __init__(self, stream) -> None:
        super().__init__()
        self._stream = stream
        self.lines: queue.Queue[str | None] = queue.Queue()

    def run(self) -> None:
        try:
            for line in self._stream:
                self.lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            self.lines.put(None)

    def next_message(self, deadline_s: float) -> dict[str, Any] | None:
        """Next JSON-RPC message, or None once the stream ends."""
        while True:
            try:
                line = self.lines.get(timeout=deadline_s)
            except queue.Empty:
                raise McpStdioError(
                    f"the server did not reply within {deadline_s:.0f}s"
                ) from None
            if line is None:
                return None
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                # Servers occasionally print a banner; protocol frames are JSON.
                continue
            if isinstance(message, dict):
                return message
            # A JSON-RPC batch is legal; take the first object in it.
            if isinstance(message, list):
                for entry in message:
                    if isinstance(entry, dict):
                        return entry
        return None


class _StderrDrain(threading.Thread):
    """Reads the server's stderr so that a logging server cannot block on it.

    MCP puts the protocol on stdout and designates stderr for logging, so a
    server that writes there is behaving correctly. Piping stderr and then never
    reading it is the client's error, and it is not a harmless one: once the
    pipe buffer fills, the server blocks inside `write()` and stops answering,
    so a server that already replied is reported as one that never did. Draining
    stdout alone left exactly that hole, because a pipe fills whether or not the
    other end is a protocol stream.

    The last few lines are kept so a failure can quote what the server was
    saying rather than only that nothing arrived.
    """

    daemon = True

    def __init__(self, stream, keep: int = 20) -> None:
        super().__init__()
        self._stream = stream
        self._tail: deque[str] = deque(maxlen=keep)

    def run(self) -> None:
        try:
            for line in self._stream:
                line = line.rstrip()
                if line:
                    self._tail.append(line)
        except (OSError, ValueError):
            # The pipe closed under us, which is what shutdown looks like.
            pass

    def detail(self) -> str:
        """The last stderr lines, one per line, or "" if the server was silent."""
        return "\n           ".join(self._tail)


def _send(proc: subprocess.Popen, message: dict[str, Any]) -> None:
    assert proc.stdin is not None
    try:
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()
    except (BrokenPipeError, OSError) as exc:
        raise McpStdioError(f"the server closed its input: {exc}") from None


def _await_id(reader: _Reader, want_id: int, timeout_s: float) -> dict[str, Any]:
    import time

    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise McpStdioError(f"no reply to request {want_id} within {timeout_s:.0f}s")
        message = reader.next_message(remaining)
        if message is None:
            raise McpStdioError("the server exited before answering")
        if message.get("id") != want_id:
            continue  # a notification, a log line, or an out-of-order reply
        if "error" in message:
            err = message["error"]
            detail = err.get("message") if isinstance(err, dict) else err
            raise McpStdioError(f"the server returned an error for {want_id}: {detail}")
        return message


def list_tools_stdio(command: str, timeout_s: float = 20.0) -> list[str]:
    """Spawn `command` and return the tool names it advertises.

    Raises McpStdioError with a readable reason on any failure, so the CLI can
    report it instead of hanging or printing an empty list that looks clean.
    """
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise McpStdioError(f"could not parse the command: {exc}") from None
    if not argv:
        raise McpStdioError("no command given")

    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        raise McpStdioError(f"command not found: {argv[0]}") from None
    except OSError as exc:
        raise McpStdioError(f"could not start {argv[0]}: {exc}") from None

    reader = _Reader(proc.stdout)
    reader.start()
    # stderr has to be drained too, and for the same reason as stdout: it is a
    # pipe, it fills, and a server that logs is expected to use it.
    stderr_drain = _StderrDrain(proc.stderr)
    stderr_drain.start()

    try:
        try:
            _send(proc, {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": CLIENT_INFO,
                },
            })
            handshake = _await_id(reader, 1, timeout_s)
            result = handshake.get("result")
            if not isinstance(result, dict):
                raise McpStdioError("the initialize reply had no result object")
            _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            listing = _await_id(reader, 2, timeout_s)
        except McpStdioError as exc:
            # Whatever the server was saying while it failed is usually the
            # reason, and it is already in hand.
            detail = stderr_drain.detail()
            if detail:
                raise McpStdioError(f"{exc} (last server stderr: {detail})") from None
            raise
    finally:
        _terminate(proc)

    result = listing.get("result")
    if not isinstance(result, dict):
        raise McpStdioError("the tools/list reply had no result object")
    # A missing `tools` key is a malformed reply, not an empty server. Treating
    # it as empty would report "no collisions" for a server we never actually
    # read, which is the one failure mode a checker must not have.
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise McpStdioError("the tools/list result did not contain a tool array")

    names: list[str] = []
    for entry in tools:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
        else:
            raise McpStdioError(f"a tool entry had no string name: {entry!r}")
    return names


def _terminate(proc: subprocess.Popen) -> None:
    """Close stdin and make sure the child is gone."""
    if proc.poll() is None:
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
