"""
Configuration and settings management for the Universal MCP external service.
Pure Python dataclass with environment variable parsing and CLI argument overrides.
"""

from dataclasses import dataclass, field
import os
from typing import Optional, Literal

from blender_addon.universal_mcp.bridge.bridge_client import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
)


@dataclass
class Settings:
    """Runtime configuration settings for the MCP external service."""

    transport: Literal["stdio", "streamable-http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    bridge_host: str = DEFAULT_BRIDGE_HOST
    bridge_port: int = DEFAULT_BRIDGE_PORT
    bridge_timeout: float = 30.0
    auth_token: Optional[str] = None
    stateless_http: bool = True
    approval_mode: str = "blender"
    debug: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        """Instantiate Settings from environment variables with safe defaults."""
        raw_transport = os.environ.get("UMCP_TRANSPORT", "stdio").lower()
        transport: Literal["stdio", "streamable-http"] = (
            "streamable-http" if raw_transport in ("http", "streamable-http") else "stdio"
        )
        host = os.environ.get("UMCP_HOST", "127.0.0.1")
        port = int(os.environ.get("UMCP_PORT", "8000"))
        bridge_host = os.environ.get("UMCP_BRIDGE_HOST", DEFAULT_BRIDGE_HOST)
        bridge_port = int(os.environ.get("UMCP_BRIDGE_PORT", str(DEFAULT_BRIDGE_PORT)))
        bridge_timeout = float(os.environ.get("UMCP_BRIDGE_TIMEOUT", "30.0"))
        auth_token = os.environ.get("UMCP_AUTH_TOKEN")
        stateless_http = os.environ.get("UMCP_STATELESS_HTTP", "true").lower() in ("1", "true", "yes")
        approval_mode = os.environ.get("UMCP_APPROVAL_MODE", "blender").lower()
        debug = os.environ.get("UMCP_DEBUG", "false").lower() in ("1", "true", "yes")

        return cls(
            transport=transport,
            host=host,
            port=port,
            bridge_host=bridge_host,
            bridge_port=bridge_port,
            bridge_timeout=bridge_timeout,
            auth_token=auth_token,
            stateless_http=stateless_http,
            approval_mode=approval_mode,
            debug=debug,
        )
