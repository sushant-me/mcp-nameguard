"""A minimal MCP server over stdio, for testing the client without a network.

Modes (first argument):
  normal   answer initialize and tools/list   (default)
  banner   print a non-JSON banner first
  error    answer tools/list with a JSON-RPC error
  exit     say nothing and exit
  quiet    answer initialize, then never answer tools/list
  huge     answer tools/list with one line far over the client's size cap
  broken   answer with a reply whose result has no tool array
  chatty   answer normally while logging to stderr, past any pipe buffer size
  noisy-fail  refuse tools/list while logging the reason to stderr
"""

import json
import os
import sys

# Comfortably larger than a pipe buffer (64 KiB on Linux), so a client that
# pipes stderr without reading it will see this server block inside write().
CHATTY_LINES = int(os.environ.get("STUB_CHATTY_LINES", "4000"))


def log(text):
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


def reply(msg_id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
    sys.stdout.flush()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"

    if mode == "banner":
        sys.stdout.write("starting stub mcp server v1.0\n")
        sys.stdout.flush()

    if mode == "exit":
        return 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = message.get("method")
        msg_id = message.get("id")

        if mode == "chatty":
            # Logging to stderr is what the MCP spec designates stderr for.
            for i in range(CHATTY_LINES):
                log(f"[info] loading tool {i} of {CHATTY_LINES}")

        if method == "initialize":
            reply(msg_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "stub", "version": "0"},
            })
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            if mode == "quiet":
                continue
            if mode == "error":
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32601, "message": "tools/list not supported"},
                }) + "\n")
                sys.stdout.flush()
                continue
            if mode == "noisy-fail":
                log("[error] refusing tools/list: config file not found")
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32603, "message": "internal error"},
                }) + "\n")
                sys.stdout.flush()
                continue
            if mode == "huge":
                # One line far larger than the cap. The client must refuse it rather than grow
                # until the process dies, because that is the server it was asked to inspect.
                sys.stdout.write("x" * (256 * 1024) + "\n")
                sys.stdout.flush()
                continue
            if mode == "broken":
                reply(msg_id, {"not_tools": []})
                continue
            reply(msg_id, {"tools": [
                {"name": "get_weather", "description": "weather"},
                {"name": "transfer_to_agent", "description": "hand off"},
                {"name": "set_model_response", "description": "final answer"},
            ]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
