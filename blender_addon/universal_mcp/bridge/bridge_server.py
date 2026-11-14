"""
Loopback Bridge Server running inside the Blender Add-on.
Accepts incoming TCP connections on 127.0.0.1, parses commands,
and hands them off to MainThreadQueue for main-thread execution.
Pure Python standard library + bpy only (zero external pip dependencies).
"""

import socket
import threading
import json
import time
from typing import Optional, Set, Dict, Any

from .main_thread_queue import get_main_thread_queue, MainThreadQueue
from .bridge_client import probe_port, DEFAULT_BRIDGE_PORT

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = DEFAULT_BRIDGE_PORT
BUFFER_SIZE = 8192


class BridgeServer:
    """
    Loopback TCP socket server running inside Blender.
    Dispatches incoming JSON commands onto Blender's main event thread via MainThreadQueue.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, queue: Optional[MainThreadQueue] = None):
        self.host = host
        self.port = port
        self.running: bool = False
        self._socket: Optional[socket.socket] = None
        self._server_thread: Optional[threading.Thread] = None
        self._queue: MainThreadQueue = queue or get_main_thread_queue()
        self._clients: Set[socket.socket] = set()
        self._clients_lock = threading.Lock()

    def start(self) -> bool:
        """Starts the server thread and main-thread timer."""
        if self.running:
            return True

        # Safety Check: Resolve port ownership before attempting to bind
        port_status = probe_port(self.host, self.port)
        if port_status == "EXTERNAL_SERVICE":
            raise RuntimeError(
                f"Cannot start bridge server: Port {self.port} is already in use by an external service "
                f"(such as an existing Blender MCP connection). Use a different port to prevent conflicts."
            )
        if port_status == "UMCP_BRIDGE":
            # Another Universal MCP bridge instance is already running on this port
            self.running = True
            return True

        # Ensure main-thread timer is running
        self._queue.start_timer()

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Use SO_EXCLUSIVEADDRUSE on Windows to protect against socket conflicts
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen(5)
            self._socket = s
            self.running = True

            self._server_thread = threading.Thread(target=self._accept_loop, daemon=True, name="UniversalMCP_BridgeServer")
            self._server_thread.start()
            return True
        except Exception as e:
            self.stop()
            raise RuntimeError(f"Failed to start bridge server on {self.host}:{self.port}: {e}") from e

    def stop(self):
        """Stops the bridge server, disconnects all clients, and unregisters timers."""
        self.running = False

        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        with self._clients_lock:
            clients = list(self._clients)
            self._clients.clear()

        for c in clients:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                c.close()
            except Exception:
                pass

        self._queue.stop_timer()

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=1.0)
            self._server_thread = None

    def _accept_loop(self):
        """Accept loop running in a background daemon thread."""
        if not self._socket:
            return
        self._socket.settimeout(1.0)

        while self.running:
            try:
                client_sock, client_addr = self._socket.accept()
                with self._clients_lock:
                    self._clients.add(client_sock)

                handler_t = threading.Thread(
                    target=self._client_handler,
                    args=(client_sock,),
                    daemon=True,
                    name=f"UniversalMCP_Client_{client_addr[1]}"
                )
                handler_t.start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _get_command_timeout(self, command: Dict[str, Any]) -> float:
        cmd_type = command.get("type") or command.get("command") or ""
        params = command.get("params") or {}
        if cmd_type in ("render_scene", "bake_object_texture", "bake_physics_simulation"):
            if isinstance(params, dict):
                return float(params.get("timeout", 1200.0))
            return 1200.0
        return 30.0

    def _client_handler(self, client_sock: socket.socket):
        """Handles framed JSON commands from a connected MCP client."""
        client_sock.settimeout(1.0)
        buffer = b""

        try:
            while self.running:
                try:
                    data = client_sock.recv(BUFFER_SIZE)
                    if not data:
                        # Client closed socket, process any trailing payload
                        if buffer.strip():
                            try:
                                command = json.loads(buffer.decode("utf-8").strip())
                                cmd_type = command.get("type") or command.get("command") or ""
                                if cmd_type == "ping":
                                    response = {"status": "success", "result": {"pong": True}}
                                else:
                                    response = self._queue.submit_and_wait(command, timeout=self._get_command_timeout(command))
                                raw_resp = json.dumps(response).encode("utf-8") + b"\n"
                                client_sock.sendall(raw_resp)
                            except Exception:
                                pass
                        break

                    buffer += data
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line_str = line.decode("utf-8").strip()
                        if not line_str:
                            continue
                        try:
                            command = json.loads(line_str)
                            cmd_type = command.get("type") or command.get("command") or ""
                            if cmd_type == "ping":
                                response = {"status": "success", "result": {"pong": True}}
                            else:
                                response = self._queue.submit_and_wait(command, timeout=self._get_command_timeout(command))
                            raw_resp = json.dumps(response).encode("utf-8") + b"\n"
                            client_sock.sendall(raw_resp)
                        except (json.JSONDecodeError, UnicodeDecodeError) as je:
                            err_resp = {"status": "error", "message": f"Malformed JSON: {je}"}
                            client_sock.sendall(json.dumps(err_resp).encode("utf-8") + b"\n")
                        except Exception as e:
                            err_resp = {"status": "error", "message": f"Server response serialization/transport error: {e}"}
                            client_sock.sendall(json.dumps(err_resp).encode("utf-8") + b"\n")

                    # Also check non-delimited JSON if valid complete object arrived without newline
                    if buffer.strip().startswith(b"{") and buffer.strip().endswith(b"}"):
                        try:
                            command = json.loads(buffer.decode("utf-8").strip())
                            buffer = b""
                            cmd_type = command.get("type") or command.get("command") or ""
                            if cmd_type == "ping":
                                response = {"status": "success", "result": {"pong": True}}
                            else:
                                response = self._queue.submit_and_wait(command, timeout=self._get_command_timeout(command))
                            raw_resp = json.dumps(response).encode("utf-8") + b"\n"
                            client_sock.sendall(raw_resp)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            # Incomplete chunk, wait for next recv
                            pass

                except socket.timeout:
                    continue
                except Exception:
                    break
        finally:
            with self._clients_lock:
                self._clients.discard(client_sock)
            try:
                client_sock.close()
            except Exception:
                pass
