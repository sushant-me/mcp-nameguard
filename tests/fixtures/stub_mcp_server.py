"""A minimal MCP server over stdio, for testing the client without a network.

Modes (first argument):
  normal   answer initialize and tools/list   (default)
  banner   print a non-JSON banner first
  error    answer tools/list with a JSON-RPC error
  exit     say nothing and exit
  quiet    answer initialize, then never answer tools/list
  broken   answer with a reply whose result has no tool array
"""

import json
import sys


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
