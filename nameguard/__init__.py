"""mcp-nameguard - check an MCP server's tool names against framework-reserved names."""

from .frameworks import FRAMEWORKS, Framework, all_guarded, all_reserved, get
from .mcp_http import McpHttpError, list_tools_http
from .mcp_stdio import McpError, McpStdioError, list_tools_stdio
from .scan import Finding, load, names_from_payload, scan_names, scan_payload
from ._version import __version__

__all__ = [
    "FRAMEWORKS", "Framework", "Finding", "all_guarded", "all_reserved", "get",
    "load", "names_from_payload", "scan_names", "scan_payload", "__version__",
    "McpError", "McpStdioError", "McpHttpError",
    "list_tools_stdio", "list_tools_http",
]
