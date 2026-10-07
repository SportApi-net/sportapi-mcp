"""MCP server for SportAPI: Live and Prematch sports odds, scores and statistics
for AI assistants (Claude Desktop, Claude Code, Cursor, VS Code and others).

Documentation: https://sportapi.net/docs/sport-line/getting-started/quick-start.html
"""

from ._version import __version__
from .server import create_server
from .service import SportAPIService

__all__ = ["SportAPIService", "__version__", "create_server"]
