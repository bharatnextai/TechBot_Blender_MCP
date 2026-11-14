"""
Official MCP SDK Server implementation for the Universal MCP external service.
Handles tools/list discovery and tools/call dispatching to BlenderExecutor.
"""

from typing import Optional, List, Dict, Any
import json
import logging

from mcp.server import Server
import mcp.types as types

from ..registry.tool_registry import ToolRegistry
from ..execution.blender_executor import BlenderExecutor
from shared.models.protocol_models import BridgeResponse

logger = logging.getLogger("UniversalMCPServer")
DEFAULT_SERVER_INSTRUCTIONS = (
    "Blender Universal MCP was created by Techbot81. "
    "It exposes typed Blender tools through a local bridge; scene mutations "
    "remain subject to the configured human-approval and validation safeguards."
)


def create_mcp_server(
    executor: Optional[BlenderExecutor] = None,
    registry: Optional[ToolRegistry] = None,
    dispatcher: Optional[Any] = None,
    server_name: str = "blender-universal-mcp",
    server_version: str = "1.0.0",
    server_instructions: str = DEFAULT_SERVER_INSTRUCTIONS,
) -> Server:
    """
    Factory creating and configuring the official MCP Server instance.
    Wires up tool discovery and execution handlers against AgentDispatcher and BlenderExecutor.
    """
    server = Server(server_name, version=server_version, instructions=server_instructions)
    tool_registry = registry or ToolRegistry()
    blender_executor = executor or BlenderExecutor()

    if dispatcher is None:
        from ..agents.dispatcher import AgentDispatcher
        agent_dispatcher = AgentDispatcher(executor=blender_executor)
    else:
        agent_dispatcher = dispatcher

    # Store references on server instance for introspection/testing
    setattr(server, "_tool_registry", tool_registry)
    setattr(server, "_blender_executor", blender_executor)
    setattr(server, "_agent_dispatcher", agent_dispatcher)

    @server.list_tools()
    async def handle_list_tools() -> List[types.Tool]:
        """Exposes the read-only and mutation tools defined in ToolRegistry."""
        return tool_registry.get_mcp_tools()

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> List[types.TextContent]:
        """
        Validates arguments and executes the requested tool via AgentDispatcher and BlenderExecutor.
        Always returns a structured TextContent containing JSON results or error envelopes.
        """
        arguments = arguments or {}

        if not tool_registry.has_tool(name):
            err_dict = BridgeResponse.error(
                f"Unknown tool '{name}'. Available: {tool_registry.tool_names}"
            ).to_dict()
            return [types.TextContent(type="text", text=json.dumps(err_dict, indent=2))]

        try:
            resp = agent_dispatcher.dispatch_tool_call(name, arguments)
            return [types.TextContent(type="text", text=json.dumps(resp.to_dict(), indent=2))]
        except Exception as e:
            logger.exception(f"Unexpected error executing tool '{name}': {e}")
            err_dict = BridgeResponse.error(f"Internal execution error: {str(e)}").to_dict()
            return [types.TextContent(type="text", text=json.dumps(err_dict, indent=2))]

    return server
