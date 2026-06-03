"""
MCP server for Packet Tracer.

Entry point: creates the server, registers tools/resources, and starts
in streamable-http (:39000) or stdio depending on the --stdio flag.
"""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from .adapters.mcp.resource_registry import register_resources
from .adapters.mcp.tool_registry import register_tools
from .settings import SERVER_NAME, SERVER_INSTRUCTIONS

TRANSPORT_PORT = 39000

mcp = FastMCP(
    SERVER_NAME,
    instructions=SERVER_INSTRUCTIONS,
    host="127.0.0.1",
    port=TRANSPORT_PORT,
    stateless_http=True,
)

register_tools(mcp)
register_resources(mcp)


def main():
    """Start the MCP server.

    By default uses streamable-http on :39000.
    With --stdio uses stdio transport (for debugging or legacy clients).
    """
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
