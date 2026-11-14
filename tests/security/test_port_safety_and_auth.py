"""
Offline Security Tests for Port 9876 Ownership Safety, Conflict Prevention, and Token Auth.
Verifies that Universal MCP safely protects existing connections and enforces authorization.
"""

import unittest
import socket
import threading
import time
from starlette.testclient import TestClient

from blender_addon.universal_mcp.bridge.bridge_client import (
    probe_port,
    find_available_port,
    is_port_in_use,
    BridgeClient,
)
from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue
from mcp_service.configuration.settings import Settings
from mcp_service.security.auth import generate_auth_token, verify_auth_token
from mcp_service.server.mcp_server import create_mcp_server
from mcp_service.transports.streamable_http_transport import create_streamable_http_app
from tests.protocol.test_mcp_discovery_and_invocation import MockBlenderExecutor


class TestPortSafetyAndAuth(unittest.TestCase):
    def test_probe_port_unoccupied(self):
        free_port = find_available_port(start_port=21000, max_attempts=50)
        self.assertEqual(probe_port("127.0.0.1", free_port), "FREE")

    def test_probe_port_umcp_bridge(self):
        port = find_available_port(start_port=21100, max_attempts=50)
        q = MainThreadQueue()
        server = BridgeServer(host="127.0.0.1", port=port, queue=q)
        server.start()

        # Drainage thread for ping
        running = True

        def drain():
            while running:
                q.drain_queue()
                time.sleep(0.01)

        t = threading.Thread(target=drain, daemon=True)
        t.start()

        try:
            status = probe_port("127.0.0.1", port, timeout=1.0)
            self.assertEqual(status, "UMCP_BRIDGE")
        finally:
            running = False
            t.join(timeout=1.0)
            server.stop()

    def test_probe_port_external_foreign_service(self):
        # Simulate an external service (e.g. existing upstream Blender MCP connection)
        port = find_available_port(start_port=21200, max_attempts=50)
        foreign_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        foreign_sock.bind(("127.0.0.1", port))
        foreign_sock.listen(1)

        # Thread to accept and send non-UMCP data or close
        server_running = True

        def foreign_worker():
            foreign_sock.settimeout(0.5)
            while server_running:
                try:
                    conn, _ = foreign_sock.accept()
                    # Foreign service sends non-UMCP protocol or closes
                    conn.sendall(b"MCP-FOR-BLENDER-UPSTREAM-V14\n")
                    conn.close()
                except socket.timeout:
                    continue
                except Exception:
                    break

        t = threading.Thread(target=foreign_worker, daemon=True)
        t.start()

        try:
            status = probe_port("127.0.0.1", port, timeout=0.5)
            # Must detect that an external service owns this port
            self.assertEqual(status, "EXTERNAL_SERVICE")

            # Verify that BridgeServer refuses to start and raises an informative error
            q = MainThreadQueue()
            conflicting_server = BridgeServer(host="127.0.0.1", port=port, queue=q)
            with self.assertRaises(RuntimeError) as ctx:
                conflicting_server.start()
            self.assertIn("already in use by an external service", str(ctx.exception))
            self.assertIn("existing Blender MCP connection", str(ctx.exception))

        finally:
            server_running = False
            t.join(timeout=1.0)
            foreign_sock.close()

    def test_token_auth_generation_and_verification(self):
        token = generate_auth_token()
        self.assertTrue(len(token) > 20)
        self.assertTrue(verify_auth_token(token, token))
        self.assertFalse(verify_auth_token("invalid_token", token))
        self.assertFalse(verify_auth_token(None, token))
        # When no expected token is configured, verification is permissive
        self.assertTrue(verify_auth_token(None, None))

    def test_http_transport_auth_enforcement(self):
        mock_exec = MockBlenderExecutor()
        server = create_mcp_server(executor=mock_exec)
        secret_token = "test-secret-bearer-token-12345"

        settings = Settings(
            transport="streamable-http",
            auth_token=secret_token,
            stateless_http=True,
        )
        app = create_streamable_http_app(server, settings)

        with TestClient(app) as client:
            # 1. Health check is unauthenticated
            res_health = client.get("/health")
            self.assertEqual(res_health.status_code, 200)
            self.assertEqual(res_health.json()["status"], "healthy")
            self.assertTrue(res_health.json()["auth_required"])

            init_payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
                "id": 1,
            }

            # 2. Inbound request without token is rejected
            res_no_auth = client.post(
                "/mcp",
                json=init_payload,
                headers={"Accept": "application/json, text/event-stream"},
            )
            self.assertEqual(res_no_auth.status_code, 401)
            self.assertIn("Unauthorized", res_no_auth.json()["error"]["message"])

            # 3. Inbound request with bad token is rejected
            res_bad_auth = client.post(
                "/mcp",
                json=init_payload,
                headers={
                    "Authorization": "Bearer wrong-token",
                    "Accept": "application/json, text/event-stream",
                },
            )
            self.assertEqual(res_bad_auth.status_code, 401)

            # 4. Inbound request with valid token succeeds
            res_auth_ok = client.post(
                "/mcp",
                json=init_payload,
                headers={
                    "Authorization": f"Bearer {secret_token}",
                    "Accept": "application/json, text/event-stream",
                },
            )
            self.assertEqual(res_auth_ok.status_code, 200)
            self.assertIn("serverInfo", res_auth_ok.text)


if __name__ == "__main__":
    unittest.main()
