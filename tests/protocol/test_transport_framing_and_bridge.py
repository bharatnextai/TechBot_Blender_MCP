"""
Offline Transport Framing and Bridge Protocol Compliance Tests.
Tests line-delimited TCP socket framing, chunked delivery, pipelining, and timeouts.
"""

import unittest
import socket
import threading
import time
import json

from blender_addon.universal_mcp.bridge.bridge_server import BridgeServer
from blender_addon.universal_mcp.bridge.bridge_client import BridgeClient, find_available_port
from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue


class TestTransportFramingAndBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Choose a dynamic test port to avoid conflicting with anything
        cls.test_port = find_available_port(start_port=19876, max_attempts=50)
        cls.queue = MainThreadQueue()
        cls.server = BridgeServer(host="127.0.0.1", port=cls.test_port, queue=cls.queue)

        # Register test echo handler
        def echo_handler(bpy_module, params):
            return {"echo": params.get("val")}

        def slow_handler(bpy_module, params):
            time.sleep(params.get("delay", 0.5))
            return {"waited": True}

        cls.queue.register_handler("test_echo", echo_handler)
        cls.queue.register_handler("test_slow", slow_handler)

        cls.server.start()

        # Background thread to simulate Blender main-thread timer draining the queue
        cls.drain_running = True

        def drain_loop():
            while cls.drain_running:
                cls.queue.drain_queue()
                time.sleep(0.01)

        cls.drain_thread = threading.Thread(target=drain_loop, daemon=True, name="TestDrainer")
        cls.drain_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.drain_running = False
        cls.drain_thread.join(timeout=1.0)
        cls.server.stop()

    def test_single_command_line_delimited_framing(self):
        client = BridgeClient(host="127.0.0.1", port=self.test_port, timeout=5.0)
        try:
            res = client.send_command("ping")
            self.assertEqual(res["status"], "success")
            self.assertTrue(res["result"]["pong"])
        finally:
            client.close()

    def test_sequential_pipelining_on_persistent_connection(self):
        client = BridgeClient(host="127.0.0.1", port=self.test_port, timeout=5.0)
        try:
            # Send 5 sequential requests over the exact same socket connection
            for i in range(5):
                res = client.send_command("test_echo", {"val": i * 10})
                self.assertEqual(res["status"], "success")
                self.assertEqual(res["result"]["echo"], i * 10)
        finally:
            client.close()

    def test_chunked_fragmented_delivery(self):
        # Connect raw socket and send payload in 4-byte pieces to simulate network fragmentation
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(5.0)
        raw_sock.connect(("127.0.0.1", self.test_port))

        payload = json.dumps({"type": "test_echo", "params": {"val": 999}}).encode("utf-8") + b"\n"
        chunk_size = 4
        for i in range(0, len(payload), chunk_size):
            raw_sock.sendall(payload[i:i + chunk_size])
            time.sleep(0.01)

        # Read response
        resp_data = b""
        while b"\n" not in resp_data:
            chunk = raw_sock.recv(1024)
            if not chunk:
                break
            resp_data += chunk

        raw_sock.close()
        parsed = json.loads(resp_data.decode("utf-8").strip())
        self.assertEqual(parsed["status"], "success")
        self.assertEqual(parsed["result"]["echo"], 999)

    def test_non_delimited_json_fallback(self):
        # Test sending complete JSON object without trailing newline
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(5.0)
        raw_sock.connect(("127.0.0.1", self.test_port))

        payload = json.dumps({"type": "test_echo", "params": {"val": 777}}).encode("utf-8")
        raw_sock.sendall(payload)

        # Read response
        resp_data = b""
        while b"\n" not in resp_data:
            chunk = raw_sock.recv(1024)
            if not chunk:
                break
            resp_data += chunk

        raw_sock.close()
        parsed = json.loads(resp_data.decode("utf-8").strip())
        self.assertEqual(parsed["status"], "success")
        self.assertEqual(parsed["result"]["echo"], 777)

    def test_malformed_json_returns_error(self):
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(5.0)
        raw_sock.connect(("127.0.0.1", self.test_port))

        # Send invalid JSON followed by newline
        raw_sock.sendall(b"{bad_json_string\n")

        resp_data = b""
        while b"\n" not in resp_data:
            chunk = raw_sock.recv(1024)
            if not chunk:
                break
            resp_data += chunk

        raw_sock.close()
        parsed = json.loads(resp_data.decode("utf-8").strip())
        self.assertEqual(parsed["status"], "error")
        self.assertIn("Malformed JSON", parsed["message"])

    def test_client_socket_timeout(self):
        # Set client timeout to 0.1s and invoke a handler taking 0.5s
        client = BridgeClient(host="127.0.0.1", port=self.test_port, timeout=0.1)
        try:
            with self.assertRaises(TimeoutError):
                client.send_command("test_slow", {"delay": 0.5})
        finally:
            client.close()

    def test_client_connection_error_on_unopened_port(self):
        unopened_port = find_available_port(start_port=29990, max_attempts=10)
        client = BridgeClient(host="127.0.0.1", port=unopened_port, timeout=0.5)
        with self.assertRaises(ConnectionError):
            client.send_command("ping")


if __name__ == "__main__":
    unittest.main()
