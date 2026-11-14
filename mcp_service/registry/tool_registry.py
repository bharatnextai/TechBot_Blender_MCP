"""
Tool registry for the Universal MCP external service.
Maps shared JSON schemas into MCP SDK Tool objects for client discovery.
"""

from typing import Dict, Any, List, Optional
import mcp.types as types

from shared.schemas.tool_schemas import (
    TOOL_DEFINITIONS,
    get_all_tool_definitions,
    TOOL_GET_SCENE_SUMMARY,
    TOOL_LIST_OBJECTS,
    TOOL_GET_OBJECT_DETAILS,
    TOOL_LIST_MATERIALS,
)


class ToolRegistry:
    """
    Central registry for all tools exposed over MCP.
    Converts domain schemas into standard MCP Tool descriptors.
    """

    def __init__(self):
        self._definitions: Dict[str, Dict[str, Any]] = dict(TOOL_DEFINITIONS)

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns the raw tool definition dictionaries."""
        return list(self._definitions.values())

    def get_mcp_tools(self) -> List[types.Tool]:
        """
        Converts registered definitions to official MCP Tool model instances
        for 'tools/list' discovery responses.
        """
        tools: List[types.Tool] = []
        for name, spec in self._definitions.items():
            tool_obj = types.Tool(
                name=spec["name"],
                description=spec.get("description", ""),
                inputSchema=spec.get("input_schema", {"type": "object"}),
            )
            tools.append(tool_obj)
        return tools

    def has_tool(self, tool_name: str) -> bool:
        """Checks if a tool is registered."""
        return tool_name in self._definitions

    def get_tool_definition(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves specific tool definition or None."""
        return self._definitions.get(tool_name)

    @property
    def tool_names(self) -> List[str]:
        """Returns list of registered tool names."""
        return list(self._definitions.keys())
