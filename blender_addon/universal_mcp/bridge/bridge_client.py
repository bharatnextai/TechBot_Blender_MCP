"""
Bridge Client and Socket Transport for the Universal MCP Blender Add-on.
Provides framed JSON-RPC communication over loopback TCP (127.0.0.1).
Pure Python standard library (zero external pip dependencies).
"""

import socket
import os
import json
import time
from typing import Dict, Any, Optional, Tuple

DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = int(os.environ.get("UMCP_BRIDGE_PORT", "9877"))
BUFFER_SIZE = 8192
DEFAULT_TIMEOUT = 30.0


def is_port_in_use(host: str = DEFAULT_BRIDGE_HOST, port: int = DEFAULT_BRIDGE_PORT) -> bool:
    """Checks whether a local port is currently occupied by a listening socket."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.5)
    try:
        res = probe.connect_ex((host, port))
        return res == 0
    except Exception:
        return False
    finally:
        probe.close()


def probe_port(host: str = DEFAULT_BRIDGE_HOST, port: int = DEFAULT_BRIDGE_PORT, timeout: float = 0.5) -> str:
    """
    Safely probes port status to resolve ownership without conflicting:
    - 'FREE': Port is unoccupied and available to bind.
    - 'UMCP_BRIDGE': Port is occupied by an active Universal MCP bridge (ping confirmed).
    - 'EXTERNAL_SERVICE': Port is occupied by an external service (e.g. existing Blender MCP connection).
    """
    if not is_port_in_use(host, port):
        return "FREE"

    # Port is open; verify if it speaks Universal MCP protocol
    probe_client = BridgeClient(host=host, port=port, timeout=timeout)
    try:
        if probe_client.ping():
            return "UMCP_BRIDGE"
    except Exception:
        pass
    finally:
        probe_client.close()

    return "EXTERNAL_SERVICE"


def find_available_port(start_port: int = DEFAULT_BRIDGE_PORT, max_attempts: int = 20, host: str = DEFAULT_BRIDGE_HOST) -> int:
    """Finds the first unoccupied port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        if not is_port_in_use(host, p):
            return p
    raise RuntimeError(f"No available port found in range {start_port} to {start_port + max_attempts - 1}")


class BridgeClient:
    """
    Client transport for communicating across the Blender bridge over TCP loopback.
    Handles connect, reconnect, line-delimited JSON framing, timeouts, and error decoding.
    """

    def __init__(self, host: str = DEFAULT_BRIDGE_HOST, port: int = DEFAULT_BRIDGE_PORT, timeout: float = DEFAULT_TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None

    def connect(self) -> bool:
        """Establish TCP connection to the bridge."""
        if self._sock:
            return True
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((self.host, self.port))
            self._sock = s
            return True
        except Exception:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
            self._sock = None
            return False

    def close(self):
        """Close connection cleanly."""
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def is_connected(self) -> bool:
        return self._sock is not None

    def send_command(self, cmd_type: str, params: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Sends a command dictionary and receives parsed response.
        Uses newline-delimited JSON framing for streaming robustness.
        Raises ConnectionError on disconnect, TimeoutError on socket timeout.
        """
        if not self._sock and not self.connect():
            raise ConnectionError(f"Could not connect to Blender bridge at {self.host}:{self.port}")

        active_timeout = timeout if timeout is not None else (
            1200.0 if cmd_type in ("render_scene", "bake_object_texture", "bake_physics_simulation") else self.timeout
        )
        if self._sock:
            self._sock.settimeout(active_timeout)

        payload = {
            "type": cmd_type,
            "params": params or {}
        }
        raw_req = json.dumps(payload).encode("utf-8") + b"\n"

        try:
            assert self._sock is not None
            self._sock.sendall(raw_req)

            buffer = b""
            while True:
                chunk = self._sock.recv(BUFFER_SIZE)
                if not chunk:
                    if not buffer:
                        raise ConnectionResetError("Bridge closed connection before response was received")
                    break
                buffer += chunk

                # Check for newline delimiter
                if b"\n" in buffer:
                    line, _ = buffer.split(b"\n", 1)
                    line_str = line.decode("utf-8").strip()
                    if line_str:
                        return json.loads(line_str)
                else:
                    # Attempt decode if non-delimited JSON was delivered
                    try:
                        return json.loads(buffer.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue

            if buffer:
                return json.loads(buffer.decode("utf-8").strip())
            raise ConnectionResetError("Empty response received from bridge")

        except socket.timeout as e:
            self.close()
            raise TimeoutError(f"Socket timed out waiting for response from {self.host}:{self.port}") from e
        except Exception:
            self.close()
            raise

    def ping(self) -> bool:
        """Performs a liveness check against the bridge."""
        try:
            res = self.send_command("ping")
            return res.get("status") == "success" and res.get("result", {}).get("pong") is True
        except Exception:
            return False
