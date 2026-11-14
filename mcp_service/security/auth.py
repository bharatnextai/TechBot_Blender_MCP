"""
Authentication and security mechanisms for the Universal MCP external service.
Provides bearer token generation/verification and Starlette ASGI middleware.
"""

import secrets
import json
from typing import Optional, Set
from starlette.types import ASGIApp, Scope, Receive, Send
from starlette.responses import JSONResponse


def generate_auth_token(num_bytes: int = 32) -> str:
    """Generates a cryptographically secure random bearer token."""
    return secrets.token_urlsafe(num_bytes)


def verify_auth_token(provided_token: Optional[str], expected_token: Optional[str]) -> bool:
    """Timing-safe comparison between provided and expected tokens."""
    if not expected_token:
        return True
    if not provided_token:
        return False
    return secrets.compare_digest(provided_token, expected_token)


class TokenAuthMiddleware:
    """
    ASGI middleware that validates Bearer authentication tokens on inbound HTTP requests.
    Exempts health/readiness probes while protecting /mcp endpoints.
    """

    ALLOWED_HOSTS: Set[str] = {
        "127.0.0.1",
        "localhost",
        "localhost:8000",
        "127.0.0.1:8000",
        "testserver",
    }

    def __init__(self, app: ASGIApp, expected_token: Optional[str] = None):
        self.app = app
        self.expected_token = expected_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Allow unrestricted access to health status endpoint
        if path == "/health":
            await self.app(scope, receive, send)
            return

        # If no auth token is required, proceed
        if not self.expected_token:
            await self.app(scope, receive, send)
            return

        # Extract Authorization header
        headers = dict(scope.get("headers", []))
        auth_header_raw = headers.get(b"authorization", b"").decode("utf-8")

        token = None
        if auth_header_raw.lower().startswith("bearer "):
            token = auth_header_raw[7:].strip()

        if not verify_auth_token(token, self.expected_token):
            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32000,
                        "message": "Unauthorized: Invalid or missing Bearer token",
                    },
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
