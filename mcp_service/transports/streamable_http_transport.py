"""
Streamable HTTP transport for the Universal MCP external service.
Hosts the MCP server over HTTP using StreamableHTTPSessionManager, Starlette, and Uvicorn.
Supports Bearer token authentication and /health status probes.
"""

import contextlib
from typing import AsyncIterator
import logging
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
from starlette.requests import Request
import uvicorn

from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from ..configuration.settings import Settings
from ..security.auth import TokenAuthMiddleware

logger = logging.getLogger("UniversalMCP_HTTP")


def create_streamable_http_app(server: Server, settings: Settings) -> Starlette:
    """
    Constructs the Starlette ASGI application with Streamable HTTP session manager,
    token authentication middleware, and health checking endpoint.
    """
    session_manager = StreamableHTTPSessionManager(
        app=server,
        stateless=settings.stateless_http,
    )

    @contextlib.asynccontextmanager
    async def app_lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    async def health_check(request: Request) -> JSONResponse:
        executor = getattr(server, "_blender_executor", None)
        bridge_alive = executor.is_connected() if executor else False

        return JSONResponse(
            {
                "status": "healthy" if bridge_alive else "degraded",
                "service": "blender-universal-mcp",
                "version": server.version or "0.1.13",
                "transport": "streamable-http",
                "bridge_connected": bridge_alive,
                "bridge_target": f"{settings.bridge_host}:{settings.bridge_port}",
                "auth_required": bool(settings.auth_token),
            }
        )

    routes = [
        Route("/health", endpoint=health_check, methods=["GET"]),
        Mount("/mcp", app=session_manager.handle_request),
    ]

    app = Starlette(lifespan=app_lifespan, routes=routes)

    # Attach authentication middleware if configured
    if settings.auth_token:
        app.add_middleware(TokenAuthMiddleware, expected_token=settings.auth_token)

    return app


def run_http_transport(server: Server, settings: Settings) -> None:
    """
    Runs the HTTP server synchronously using Uvicorn.
    """
    app = create_streamable_http_app(server, settings)
    log_level = "debug" if settings.debug else "info"

    logger.info(
        f"Starting Universal MCP Streamable HTTP transport on http://{settings.host}:{settings.port}/mcp"
    )
    if settings.auth_token:
        logger.info("Bearer token authentication is ENABLED.")
    else:
        logger.info("Bearer token authentication is disabled (localhost default).")

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=log_level,
    )
