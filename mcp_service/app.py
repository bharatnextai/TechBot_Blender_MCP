"""
Universal MCP Service Entrypoint for Blender.
Provides CLI command parsing and starts either the stdio or Streamable HTTP transport.
"""

import argparse
import asyncio
import logging
import sys
import os
from typing import List, Optional

from .configuration.settings import Settings
from .execution.blender_executor import BlenderExecutor
from .server.mcp_server import create_mcp_server
from .transports.stdio_transport import run_stdio_transport
from .transports.streamable_http_transport import run_http_transport
from blender_addon.universal_mcp.bridge.bridge_client import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
)

logger = logging.getLogger("UniversalMCP")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Universal MCP Plugin Service for Blender",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=os.environ.get("UMCP_TRANSPORT", "stdio"),
        help="MCP transport protocol",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("UMCP_HOST", "127.0.0.1"),
        help="Host address for HTTP transport",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("UMCP_PORT", "8000")),
        help="Port for HTTP transport",
    )
    parser.add_argument(
        "--bridge-host",
        default=os.environ.get("UMCP_BRIDGE_HOST", DEFAULT_BRIDGE_HOST),
        help="Blender loopback bridge host",
    )
    parser.add_argument(
        "--bridge-port",
        type=int,
        default=int(os.environ.get("UMCP_BRIDGE_PORT", str(DEFAULT_BRIDGE_PORT))),
        help="Blender loopback bridge port",
    )
    parser.add_argument(
        "--bridge-timeout",
        type=float,
        default=float(os.environ.get("UMCP_BRIDGE_TIMEOUT", "30.0")),
        help="Timeout in seconds for bridge requests",
    )
    parser.add_argument(
        "--auth-token",
        default=os.environ.get("UMCP_AUTH_TOKEN"),
        help="Bearer authentication token for HTTP transport",
    )
    parser.add_argument(
        "--approval-mode",
        choices=["blender", "mcp"],
        default=os.environ.get("UMCP_APPROVAL_MODE", "blender"),
        help="Approval mechanism: 'blender' (human Blender UI approval) or 'mcp' (pause only; resolver credentials cannot approve)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("UMCP_DEBUG", "false").lower() in ("1", "true", "yes"),
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None):
    args = parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    # Stdio transport requires stderr logging so stdout is exclusively for JSON-RPC
    logging.basicConfig(
        stream=sys.stderr,
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = Settings(
        transport=args.transport,
        host=args.host,
        port=args.port,
        bridge_host=args.bridge_host,
        bridge_port=args.bridge_port,
        bridge_timeout=args.bridge_timeout,
        auth_token=args.auth_token,
        approval_mode=args.approval_mode,
        debug=args.debug,
    )

    executor = BlenderExecutor(
        host=settings.bridge_host,
        port=settings.bridge_port,
        timeout=settings.bridge_timeout,
    )
    if settings.approval_mode == "blender":
        executor.enable_blender_approval(timeout=settings.bridge_timeout)

    server = create_mcp_server(executor=executor)

    if settings.transport == "stdio":
        try:
            asyncio.run(run_stdio_transport(server))
        except (KeyboardInterrupt, SystemExit):
            logger.info("Universal MCP stdio service stopped.")
    elif settings.transport == "streamable-http":
        try:
            run_http_transport(server, settings)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Universal MCP HTTP service stopped.")


if __name__ == "__main__":
    main()
