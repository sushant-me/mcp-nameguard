"""mcp-nameguard - check an MCP server's tool names against framework-reserved names."""

from .frameworks import FRAMEWORKS, Framework, all_reserved, get
from .scan import Finding, load, names_from_payload, scan_names, scan_payload

__version__ = "0.2.0"

__all__ = [
    "FRAMEWORKS", "Framework", "Finding", "all_reserved", "get",
    "load", "names_from_payload", "scan_names", "scan_payload", "__version__",
]
