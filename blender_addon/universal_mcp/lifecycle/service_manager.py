"""
Service manager for controlling background bridge server lifecycle within Blender.
Pure standard library + bpy.
"""

from typing import Optional
from ..bridge.main_thread_queue import get_main_thread_queue, MainThreadQueue
from ..bridge.bridge_server import BridgeServer

_manager_instance = None


class ServiceManager:
    """Manages initialization and shutdown of bridge services within Blender."""

    def __init__(self, port: int = 9877):
        self.port = port
        self.queue: MainThreadQueue = get_main_thread_queue()
        self.server: Optional[BridgeServer] = None

    def start_service(self) -> bool:
        """Start the bridge server and main-thread timer."""
        if not self.server:
            self.server = BridgeServer(port=self.port, queue=self.queue)
        return self.server.start()

    def stop_service(self):
        """Stop the bridge server and unregister timers."""
        if self.server:
            self.server.stop()
            self.server = None

    def is_running(self) -> bool:
        return self.server is not None and self.server.running


def get_service_manager(port: int = 9877) -> ServiceManager:
    global _manager_instance
    if _manager_instance is None or _manager_instance.port != port:
        _manager_instance = ServiceManager(port=port)
    return _manager_instance
