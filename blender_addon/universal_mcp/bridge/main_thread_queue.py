"""
Thread-safe Main Thread Queue and Timer Dispatcher for Blender Add-on.
Enforces the Blender threading invariant: all scene inspection and mutation
happens on Blender's main event loop via bpy.app.timers.
Pure Python standard library + bpy only (zero external pip dependencies).
"""

import queue
import threading
import time
import traceback
from typing import Dict, Any, Callable, Optional, Tuple

from .handlers import ALL_HANDLERS, READ_ONLY_HANDLERS, is_approval_required
from .approval_registry import get_approval_registry

# These legacy handlers lack their own token consumer. Guard their network
# dispatch here; other mutation handlers already consume their own credentials.
_QUEUE_TOKEN_GUARDS = frozenset({
    "assign_material", "create_light", "configure_light", "configure_world", "create_camera", "configure_camera", "edit_camera",
    "configure_render_settings", "delete_object",
})

GENUINE_SCENE_INSPECTION_HANDLERS = {
    "get_scene_summary",
    "list_objects",
    "get_object_details",
    "list_materials",
    "inspect_scene_data",
    "capture_viewport",
    "inspect_semantic_landmarks",
    "inspect_surface_detail",
    "inspect_anatomical_mask",
    "inspect_vse_timeline",
}


class MainThreadQueue:
    """
    Thread-safe command queue that buffers background requests and executes
    them sequentially on Blender's main thread via bpy.app.timers.
    """

    def __init__(self, bpy_module=None):
        self._bpy = bpy_module
        self._queue: queue.Queue = queue.Queue()
        self._handlers: Dict[str, Callable] = dict(ALL_HANDLERS)
        self._scene_inspection_handlers = set(GENUINE_SCENE_INSPECTION_HANDLERS)
        self._timer_registered: bool = False
        self._lock = threading.Lock()
        self._poll_interval: float = 0.02  # 20ms poll interval
        self._active_task: Optional[Dict[str, Any]] = None
        self._in_flight_timeout_unreconciled: bool = False
        self._in_flight_timeout_details: Optional[Dict[str, Any]] = None
        self._task_counter: int = 0
        self._timed_out_mutation_task_id: Optional[int] = None
        self._timed_out_mutation_finished: bool = False

    def register_handler(self, command: str, handler: Callable, is_scene_inspection: bool = False):
        """Register a custom handler for a command type."""
        with self._lock:
            self._handlers[command] = handler
            if is_scene_inspection:
                self._scene_inspection_handlers.add(command)

    def unregister_handler(self, command: str):
        """Unregister a handler for a command type."""
        with self._lock:
            self._handlers.pop(command, None)
            self._scene_inspection_handlers.discard(command)

    def reset_reconciliation_state(self, force: bool = False):
        """Manually clear any in-flight timeout reconciliation requirement."""
        with self._lock:
            if force or self._timed_out_mutation_finished:
                self._in_flight_timeout_unreconciled = False
                self._in_flight_timeout_details = None
                self._timed_out_mutation_task_id = None
                self._timed_out_mutation_finished = False

    def submit_and_wait(self, command: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """
        Called by background socket/network threads.
        Pushes command to the queue, blocks until main thread finishes execution or timeout expires.
        Distinguishes queue-level timeouts from active in-flight timeouts.
        Blocks automatic blind retries if an in-flight mutation previously timed out without reconciliation.
        """
        cmd_type = command.get("type") or command.get("command") or ""
        is_mutation = (cmd_type not in READ_ONLY_HANDLERS and cmd_type != "ping")

        with self._lock:
            self._task_counter += 1
            task_id = self._task_counter

            # Block blind automatic retries if an in-flight mutation previously timed out
            if is_mutation and self._in_flight_timeout_unreconciled:
                return {
                    "status": "error",
                    "error_code": "BLIND_RETRY_BLOCKED",
                    "execution_state": "REQUIRES_RECONCILIATION",
                    "message": (
                        f"Blocked mutation attempt ('{cmd_type}'): A previous in-flight execution timed out "
                        f"and may still be actively mutating the Blender scene. "
                        f"Automatic blind retries are blocked to prevent state divergence or duplicate object creation. "
                        f"You must perform read-only scene reconciliation (e.g., get_scene_summary or list_objects) "
                        f"after the in-flight task finishes before submitting new mutations."
                    ),
                    "unreconciled_task": self._in_flight_timeout_details,
                }

        event = threading.Event()
        cancel_event = threading.Event()
        active_event = threading.Event()
        result_container: Dict[str, Any] = {"response": None}

        task = {
            "task_id": task_id,
            "command": command,
            "cmd_type": cmd_type,
            "is_mutation": is_mutation,
            "event": event,
            "cancel_event": cancel_event,
            "active_event": active_event,
            "result_container": result_container,
        }

        # Put item into the queue
        self._queue.put(task)

        # Wait for the main-thread timer to process this task
        completed = event.wait(timeout=timeout)
        if not completed:
            if active_event.is_set():
                # Execution is already ACTIVE on Blender's main thread
                if is_mutation:
                    with self._lock:
                        self._in_flight_timeout_unreconciled = True
                        self._timed_out_mutation_task_id = task_id
                        self._timed_out_mutation_finished = False
                        self._in_flight_timeout_details = {
                            "type": cmd_type,
                            "task_id": task_id,
                            "timed_out_at": time.time(),
                            "timeout_seconds": timeout,
                        }
                return {
                    "status": "error",
                    "error_code": "IN_FLIGHT_TIMEOUT",
                    "execution_state": "ACTIVE_IN_FLIGHT",
                    "requires_reconciliation": is_mutation,
                    "message": (
                        f"Execution timed out on Blender main thread after {timeout}s while actively running ('{cmd_type}'). "
                        f"Running Blender Python/C operators cannot be safely interrupted asynchronously. "
                        f"The operation will run to completion or error in the background. "
                        f"Blind automatic retries are blocked; read-only scene reconciliation is required before retrying."
                    ),
                }
            else:
                # Execution has NOT started; still pending in queue
                cancel_event.set()
                return {
                    "status": "error",
                    "error_code": "QUEUE_TIMEOUT_CANCELLED",
                    "execution_state": "DISCARDED_FROM_QUEUE",
                    "requires_reconciliation": False,
                    "message": (
                        f"Execution timed out on Blender main thread after {timeout}s before execution began ('{cmd_type}'); "
                        f"task was cancelled and discarded from the queue without mutating the scene."
                    ),
                }

        return result_container["response"]

    def drain_queue(self) -> Optional[float]:
        """
        Drains all pending commands on Blender's main thread.
        This function is registered with bpy.app.timers.
        Returning self._poll_interval tells Blender to continue calling it.
        Returning None unregisters the timer.
        """
        start_time = time.time()

        while True:
            try:
                task = self._queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(task, dict):
                task_id = task.get("task_id", 0)
                command = task["command"]
                cmd_type = task["cmd_type"]
                event = task["event"]
                cancel_event = task["cancel_event"]
                active_event = task["active_event"]
                result_container = task["result_container"]
                is_mutation = task.get("is_mutation", False)
            elif len(task) == 4:
                command, event, result_container, cancel_event = task
                task_id = 0
                active_event = threading.Event()
                cmd_type = command.get("type") or command.get("command") or ""
                is_mutation = (cmd_type not in READ_ONLY_HANDLERS and cmd_type != "ping")
            else:
                command, event, result_container = task
                task_id = 0
                cancel_event = None
                active_event = threading.Event()
                cmd_type = command.get("type") or command.get("command") or ""
                is_mutation = (cmd_type not in READ_ONLY_HANDLERS and cmd_type != "ping")

            # If client timed out while command was waiting in queue, discard to avoid orphaned execution
            if cancel_event is not None and cancel_event.is_set():
                event.set()
                continue

            active_event.set()
            with self._lock:
                self._active_task = {"task_id": task_id, "command": command, "cmd_type": cmd_type, "started_at": time.time()}
            t0 = time.time()

            try:
                params = command.get("params") or {}

                # Trivial ping check
                if cmd_type == "ping":
                    res = {"status": "success", "result": {"pong": True}}
                elif cmd_type in self._handlers:
                    handler = self._handlers[cmd_type]
                    bpy_ref = self._get_bpy()
                    if cmd_type in {"execute_blender_code", "bake_object_texture", "configure_modifier", "configure_material_shader"}:
                        request = get_approval_registry().get_request(params.get("request_id"))
                        if request and request.decision_reason == "LOCAL TEST AUTO-APPROVAL: isolated background process":
                            from .handlers import _local_test_autoapproval
                            if not _local_test_autoapproval(bpy_ref, cmd_type, request.params):
                                raise PermissionError("Disposable fixture ownership or execution preconditions changed")
                    if cmd_type in _QUEUE_TOKEN_GUARDS and is_approval_required(bpy_ref):
                        from .handlers import _local_test_autoapproval
                        if not _local_test_autoapproval(bpy_ref, cmd_type, params):
                            ok, reason = get_approval_registry().consume_approval(
                                params.get("request_id"), params.get("approval_token"), cmd_type, params
                            )
                            if not ok:
                                raise PermissionError(f"Scene mutation denied: {reason}")
                    data = handler(bpy_module=bpy_ref, params=params)
                    duration_ms = round((time.time() - t0) * 1000, 2)
                    res = {
                        "status": "success",
                        "result": data,
                        "execution_time_ms": duration_ms,
                    }
                else:
                    res = {
                        "status": "error",
                        "message": f"Unknown command: '{cmd_type}'. Available handlers: {list(self._handlers.keys())}",
                    }

                result_container["response"] = res

                # Successful genuine scene inspection clears prior in-flight timeout reconciliation requirement ONLY IF:
                # 1. It is a genuine scene inspection command (cmd_type in self._scene_inspection_handlers)
                # 2. It completed with status == "success"
                # 3. The timed-out mutation task has ACTUALLY FINISHED executing
                # 4. This inspection task was enqueued/executed AFTER the timed-out task (task_id > timed_out_mutation_task_id)
                # Note: ping, get_approval_settings, check_approval_status etc. do NOT inspect the scene and CANNOT clear the barrier.
                is_genuine_inspection = (cmd_type in self._scene_inspection_handlers)
                if is_genuine_inspection and res.get("status") == "success":
                    with self._lock:
                        if self._timed_out_mutation_finished and self._timed_out_mutation_task_id is not None:
                            if task_id > self._timed_out_mutation_task_id:
                                self._in_flight_timeout_unreconciled = False
                                self._in_flight_timeout_details = None
                                self._timed_out_mutation_task_id = None
                                self._timed_out_mutation_finished = False

            except Exception as e:
                duration_ms = round((time.time() - t0) * 1000, 2)
                result_container["response"] = {
                    "status": "error",
                    "message": str(e),
                    "exception_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                    "execution_time_ms": duration_ms,
                }
            finally:
                with self._lock:
                    if task_id == self._timed_out_mutation_task_id:
                        self._timed_out_mutation_finished = True
                    self._active_task = None
                event.set()

        # If not stopped, keep timer alive
        if self._timer_registered:
            return self._poll_interval
        return None

    def start_timer(self, interval: float = 0.02) -> bool:
        """
        Registers the queue draining timer with bpy.app.timers.
        Must be called from Blender's main thread (e.g. during add-on registration or operator).
        """
        self._poll_interval = interval
        bpy_ref = self._get_bpy()
        if not bpy_ref or not hasattr(bpy_ref, "app") or not hasattr(bpy_ref.app, "timers"):
            # Offline / non-Blender environment
            self._timer_registered = True
            return True

        callback = _main_thread_queue_timer_callback
        if not bpy_ref.app.timers.is_registered(callback):
            bpy_ref.app.timers.register(callback, persistent=True)
            self._timer_registered = True
            return True
        return False

    def stop_timer(self):
        """Unregisters the queue draining timer."""
        self._timer_registered = False
        bpy_ref = self._get_bpy()
        if bpy_ref and hasattr(bpy_ref, "app") and hasattr(bpy_ref.app, "timers"):
            try:
                callback = _main_thread_queue_timer_callback
                if bpy_ref.app.timers.is_registered(callback):
                    bpy_ref.app.timers.unregister(callback)
            except Exception:
                pass

        # Drain and cancel any remaining commands
        while True:
            try:
                task = self._queue.get_nowait()
                if isinstance(task, dict):
                    event, result_container = task["event"], task["result_container"]
                    cancel_event = task.get("cancel_event")
                else:
                    _, event, result_container = task[:3]
                    cancel_event = task[3] if len(task) == 4 else None
                if cancel_event is not None:
                    cancel_event.set()
                result_container["response"] = {"status": "error", "error_code": "QUEUE_STOPPED",
                                                "execution_state": "NOT_EXECUTED", "message": "Queue stopped"}
                event.set()
            except queue.Empty:
                break

    def _get_bpy(self):
        if self._bpy:
            return self._bpy
        try:
            import bpy
            return bpy
        except ImportError:
            return None


# Global singleton instance for the add-on
_global_queue: Optional[MainThreadQueue] = None


def _main_thread_queue_timer_callback() -> Optional[float]:
    """Module-level callback for bpy.app.timers to guarantee persistence and identity across file loads."""
    global _global_queue
    if _global_queue and _global_queue._timer_registered:
        return _global_queue.drain_queue()
    return None


def get_main_thread_queue(bpy_module=None) -> MainThreadQueue:
    """Returns the process-wide MainThreadQueue singleton."""
    global _global_queue
    if _global_queue is None:
        _global_queue = MainThreadQueue(bpy_module=bpy_module)
    return _global_queue
