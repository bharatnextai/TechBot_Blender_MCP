"""
Standard I/O (stdio) transport for the Universal MCP external service.
Runs the MCP server over standard input and standard output streams
using the official MCP SDK stdio_server context manager.
"""

import sys
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger("UniversalMCP_stdio")


async def run_stdio_transport(server: Server) -> None:
    """
    Executes the MCP server event loop over stdio.
    Directs server logs away from stdout so JSON-RPC framing remains pristine.
    """
    logger.info("Starting Universal MCP stdio transport...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
