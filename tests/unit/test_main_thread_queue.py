"""
Offline Unit Tests for MainThreadQueue.
Runs purely on CPU without requiring Blender GUI or network access.
"""

import unittest
import threading
import time
from blender_addon.universal_mcp.bridge.main_thread_queue import MainThreadQueue


class TestMainThreadQueue(unittest.TestCase):
    def test_submit_and_drain_success(self):
        q = MainThreadQueue()

        # Register a test handler
        q.register_handler("test_cmd", lambda bpy_module, params: {"echo": params.get("val")})

        result_holder = {}

        def client_worker():
            res = q.submit_and_wait({"type": "test_cmd", "params": {"val": 42}}, timeout=5.0)
            result_holder["res"] = res

        t = threading.Thread(target=client_worker)
        t.start()

        # Simulate Blender main thread timer draining the queue
        time.sleep(0.05)
        poll_interval = q.drain_queue()
        t.join(timeout=2.0)

        self.assertIn("res", result_holder)
        res = result_holder["res"]
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["result"], {"echo": 42})
        self.assertIn("execution_time_ms", res)

    def test_unknown_command(self):
        q = MainThreadQueue()
        result_holder = {}

        def client_worker():
            res = q.submit_and_wait({"type": "non_existent_command"}, timeout=5.0)
            result_holder["res"] = res

        t = threading.Thread(target=client_worker)
        t.start()

        time.sleep(0.05)
        q.drain_queue()
        t.join(timeout=2.0)

        res = result_holder["res"]
        self.assertEqual(res["status"], "error")
        self.assertIn("Unknown command", res["message"])

    def test_handler_exception_capture(self):
        q = MainThreadQueue()

        def failing_handler(bpy_module, params):
            raise KeyError("Simulated missing key in scene")

        q.register_handler("failing_cmd", failing_handler)
        result_holder = {}

        def client_worker():
            res = q.submit_and_wait({"type": "failing_cmd"}, timeout=5.0)
            result_holder["res"] = res

        t = threading.Thread(target=client_worker)
        t.start()

        time.sleep(0.05)
        q.drain_queue()
        t.join(timeout=2.0)

        res = result_holder["res"]
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["exception_type"], "KeyError")
        self.assertIn("traceback", res)

    def test_timeout_when_queue_not_drained(self):
        q = MainThreadQueue()
        # Submit with very short timeout and do not drain
        res = q.submit_and_wait({"type": "ping"}, timeout=0.1)
        self.assertEqual(res["status"], "error")
        self.assertIn("timed out", res["message"])

    def test_timeout_cancels_orphaned_task_on_subsequent_drain(self):
        q = MainThreadQueue()
        executed = []

        def tracking_handler(bpy_module=None, params=None):
            executed.append("executed")
            return {"ran": True}

        q.register_handler("tracked_cmd", tracking_handler)

        # Submit with very short timeout so it expires before draining
        res = q.submit_and_wait({"type": "tracked_cmd"}, timeout=0.05)
        self.assertEqual(res["status"], "error")
        self.assertIn("timed out", res["message"])

        # Main thread drains queue later: task should be safely discarded without running handler
        q.drain_queue()
        self.assertEqual(len(executed), 0, "Orphaned timed-out task should not execute after timeout!")

    def test_create_primitive_dispatch_via_queue(self):
        class MockObj:
            def __init__(self, name):
                self.name = name
                self.type = "MESH"
                self.location = [0.0, 0.0, 0.0]
                self.dimensions = [1.0, 1.0, 1.0]
                self.users_collection = []

        class MockContext:
            def __init__(self):
                self.active_object = None
                class MockScene:
                    objects = []
                self.scene = MockScene()

        class MockOpsMesh:
            def __init__(self, ctx):
                self.ctx = ctx
            def primitive_cube_add(self, size, location):
                obj = MockObj("Cube_Temp")
                obj.location = list(location)
                self.ctx.active_object = obj

        class MockBpy:
            def __init__(self):
                self.context = MockContext()
                class MockData:
                    objects = {}
                self.data = MockData()
                class MockOpsObj:
                    def select_all(self, action):
                        pass
                class MockOps:
                    def __init__(self, ctx):
                        self.object = MockOpsObj()
                        self.mesh = MockOpsMesh(ctx)
                self.ops = MockOps(self.context)

        mock_bpy = MockBpy()
        q = MainThreadQueue(bpy_module=mock_bpy)
        result_holder = {}

        def worker():
            res = q.submit_and_wait({
                "type": "create_primitive",
                "params": _queue_approved({
                    "primitive_type": "cube",
                    "name": "MyBox",
                    "location": [1.0, 2.0, 3.0],
                    "dimensions": [2.0, 2.0, 2.0],
                    "trusted_approval": True,
                    "_trusted_test_override": True,
                })
            }, timeout=5.0)
            result_holder["res"] = res

        t = threading.Thread(target=worker)
        t.start()
        time.sleep(0.05)
        q.drain_queue()
        t.join(timeout=2.0)

        self.assertIn("res", result_holder)
        res = result_holder["res"]
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["result"]["name"], "MyBox")
        self.assertEqual(res["result"]["dimensions"], [2.0, 2.0, 2.0])

    def test_create_primitive_queue_approval_denied(self):
        q = MainThreadQueue()
        result_holder = {}

        def worker():
            res = q.submit_and_wait({
                "type": "create_primitive",
                "params": {
                    "primitive_type": "cube",
                    "name": "MyBox",
                    # Model supplying approved=True without trusted_approval is rejected
                    "approved": True
                }
            }, timeout=5.0)
            result_holder["res"] = res

        t = threading.Thread(target=worker)
        t.start()
        time.sleep(0.05)
        q.drain_queue()
        t.join(timeout=2.0)

        res = result_holder["res"]
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["exception_type"], "PermissionError")
        self.assertIn("Missing trusted human approval credentials", res["message"])

    def test_create_primitive_queue_name_collision(self):
        class MockBpy:
            class data:
                objects = {"ExistingBox": object()}
            class context:
                class scene:
                    objects = []

        q = MainThreadQueue(bpy_module=MockBpy)
        result_holder = {}

        def worker():
            res = q.submit_and_wait({
                "type": "create_primitive",
                "params": _queue_approved({
                    "primitive_type": "cube",
                    "name": "ExistingBox",
                    "trusted_approval": True,
                    "_trusted_test_override": True,
                })
            }, timeout=5.0)
            result_holder["res"] = res

        t = threading.Thread(target=worker)
        t.start()
        time.sleep(0.05)
        q.drain_queue()
        t.join(timeout=2.0)

        res = result_holder["res"]
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["exception_type"], "ValueError")
        self.assertIn("Collision detected", res["message"])

    def test_in_flight_timeout_reports_active_and_blocks_blind_mutation_retry(self):
        """
        When a mutation command times out while actively executing:
        1. Returns error_code='IN_FLIGHT_TIMEOUT' and execution_state='ACTIVE_IN_FLIGHT'.
        2. Sets requires_reconciliation=True.
        3. Blocks subsequent blind mutation retries with BLIND_RETRY_BLOCKED.
        4. Clears reconciliation requirement after a read-only command succeeds.
        """
        q = MainThreadQueue()
        started_event = threading.Event()
        finish_event = threading.Event()

        def slow_mutation_handler(bpy_module=None, params=None):
            started_event.set()
            finish_event.wait(timeout=1.0)
            return {"mutated": True}

        q.register_handler("slow_mutation", slow_mutation_handler)

        drain_thread = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread.start()

        # Submit slow mutation with very short timeout
        res1 = q.submit_and_wait({"type": "slow_mutation"}, timeout=0.04)

        self.assertEqual(res1["status"], "error")
        self.assertEqual(res1["error_code"], "IN_FLIGHT_TIMEOUT")
        self.assertEqual(res1["execution_state"], "ACTIVE_IN_FLIGHT")
        self.assertTrue(res1["requires_reconciliation"])
        self.assertIn("Blind automatic retries are blocked", res1["message"])

        # Attempting a blind retry or any mutation must be blocked immediately
        res_retry = q.submit_and_wait({"type": "slow_mutation"}, timeout=1.0)
        self.assertEqual(res_retry["status"], "error")
        self.assertEqual(res_retry["error_code"], "BLIND_RETRY_BLOCKED")
        self.assertEqual(res_retry["execution_state"], "REQUIRES_RECONCILIATION")
        self.assertIn("Blocked mutation attempt", res_retry["message"])

        # Allow the slow handler to finish
        finish_event.set()
        drain_thread.join(timeout=1.0)
        self.assertTrue(q._timed_out_mutation_finished)

        # Performing ping does NOT clear reconciliation barrier (ping does not inspect the scene)
        drain_thread_ping = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread_ping.start()
        res_ping = q.submit_and_wait({"type": "ping"}, timeout=1.0)
        drain_thread_ping.join(timeout=1.0)
        self.assertEqual(res_ping["status"], "success")
        self.assertTrue(q._in_flight_timeout_unreconciled)

        # Blind mutation retry is STILL blocked after ping
        res_retry2 = q.submit_and_wait({"type": "slow_mutation"}, timeout=1.0)
        self.assertEqual(res_retry2["error_code"], "BLIND_RETRY_BLOCKED")

        # Performing genuine scene inspection (e.g. get_scene_summary) reconciles the state
        q.register_handler("get_scene_summary", lambda bpy_module, params: {"objects": ["Cube"]})
        drain_thread_read = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread_read.start()
        res_inspect = q.submit_and_wait({"type": "get_scene_summary"}, timeout=1.0)
        drain_thread_read.join(timeout=1.0)
        self.assertEqual(res_inspect["status"], "success")
        self.assertFalse(q._in_flight_timeout_unreconciled)

        # Now mutation commands are permitted
        finish_event.clear()
        drain_thread2 = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread2.start()
        finish_event.set()
        res_after = q.submit_and_wait({"type": "slow_mutation"}, timeout=1.0)
        drain_thread2.join(timeout=1.0)
        self.assertEqual(res_after["status"], "success")

    def test_queue_timeout_cancelled_when_pending(self):
        """
        When a command times out while still waiting in queue (before starting):
        1. Returns error_code='QUEUE_TIMEOUT_CANCELLED' and execution_state='DISCARDED_FROM_QUEUE'.
        2. Sets requires_reconciliation=False.
        3. Subsequent mutations are NOT blocked because the command never started.
        """
        q = MainThreadQueue()
        res = q.submit_and_wait({"type": "create_primitive"}, timeout=0.02)
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_code"], "QUEUE_TIMEOUT_CANCELLED")
        self.assertEqual(res["execution_state"], "DISCARDED_FROM_QUEUE")
        self.assertFalse(res["requires_reconciliation"])

    def test_read_only_request_cannot_clear_barrier_while_mutation_executing(self):
        """
        TASK-UMCP-0054 (Requirement B.2):
        A read-only request cannot clear the in-flight mutation barrier while the
        original timed-out mutation task is still actively executing.
        """
        q = MainThreadQueue()
        started_event = threading.Event()
        finish_event = threading.Event()

        def slow_mutation(bpy_module=None, params=None):
            started_event.set()
            finish_event.wait(timeout=2.0)
            return {"mutated": True}

        q.register_handler("slow_mutation", slow_mutation)

        drain_thread = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread.start()

        # Submit slow mutation with very short timeout
        res = q.submit_and_wait({"type": "slow_mutation"}, timeout=0.04)
        self.assertEqual(res["error_code"], "IN_FLIGHT_TIMEOUT")
        self.assertTrue(q._in_flight_timeout_unreconciled)
        self.assertFalse(q._timed_out_mutation_finished)

        # Attempt read-only reconciliation while the mutation is STILL running
        # Since drain_queue is blocked in slow_mutation, this read-only request cannot complete
        res_read_timeout = q.submit_and_wait({"type": "ping"}, timeout=0.04)
        # The read-only request timed out while the mutation was still running
        self.assertEqual(res_read_timeout["status"], "error")

        # Barrier must REMAIN active
        self.assertTrue(q._in_flight_timeout_unreconciled)
        self.assertFalse(q._timed_out_mutation_finished)

        # Blind mutation retry must still be BLOCKED
        res_retry = q.submit_and_wait({"type": "slow_mutation"}, timeout=0.5)
        self.assertEqual(res_retry["error_code"], "BLIND_RETRY_BLOCKED")

        # Now let the slow mutation finish
        finish_event.set()
        drain_thread.join(timeout=1.0)
        self.assertTrue(q._timed_out_mutation_finished)

    def test_failed_or_timed_out_reconciliation_leaves_barrier_active(self):
        """
        TASK-UMCP-0054 (Requirement B.3):
        Failed, timed-out, or incomplete reconciliation leaves the barrier active.
        """
        q = MainThreadQueue()
        started_event = threading.Event()
        finish_event = threading.Event()

        def slow_mutation(bpy_module=None, params=None):
            started_event.set()
            finish_event.wait(timeout=1.0)
            return {"mutated": True}

        def failing_read_only(bpy_module=None, params=None):
            raise RuntimeError("Database read failed or scene corrupt")

        q.register_handler("slow_mutation", slow_mutation)
        q.register_handler("failing_read_only", failing_read_only)

        drain_thread = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread.start()

        # 1. Mutation times out in flight
        res = q.submit_and_wait({"type": "slow_mutation"}, timeout=0.04)
        self.assertEqual(res["error_code"], "IN_FLIGHT_TIMEOUT")

        # Allow mutation to finish
        finish_event.set()
        drain_thread.join(timeout=1.0)
        self.assertTrue(q._timed_out_mutation_finished)
        self.assertTrue(q._in_flight_timeout_unreconciled)

        # 2. Reconciliation attempt A: handler fails with exception
        drain_thread_fail = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread_fail.start()
        res_fail = q.submit_and_wait({"type": "failing_read_only"}, timeout=1.0)
        drain_thread_fail.join(timeout=1.0)
        self.assertEqual(res_fail["status"], "error")

        # Barrier must remain active after failed reconciliation!
        self.assertTrue(q._in_flight_timeout_unreconciled)
        res_blocked1 = q.submit_and_wait({"type": "slow_mutation"}, timeout=0.5)
        self.assertEqual(res_blocked1["error_code"], "BLIND_RETRY_BLOCKED")

        # 3. Reconciliation attempt B: read-only request times out in queue
        res_timeout = q.submit_and_wait({"type": "ping"}, timeout=0.02)
        self.assertEqual(res_timeout["status"], "error")
        self.assertEqual(res_timeout["error_code"], "QUEUE_TIMEOUT_CANCELLED")

        # Barrier must still remain active after timed-out reconciliation!
        self.assertTrue(q._in_flight_timeout_unreconciled)
        res_blocked2 = q.submit_and_wait({"type": "slow_mutation"}, timeout=0.5)
        self.assertEqual(res_blocked2["error_code"], "BLIND_RETRY_BLOCKED")

    def test_successful_reconciliation_after_task_finishes_permits_mutations(self):
        """
        TASK-UMCP-0054 (Requirement B.4):
        Only a completed, successful reconciliation after the timed-out task finishes
        permits new mutations.
        """
        q = MainThreadQueue()
        started_event = threading.Event()
        finish_event = threading.Event()

        def slow_mutation(bpy_module=None, params=None):
            started_event.set()
            finish_event.wait(timeout=1.0)
            return {"mutated": True}

        q.register_handler("slow_mutation", slow_mutation)

        drain_thread = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread.start()

        # In-flight timeout
        res = q.submit_and_wait({"type": "slow_mutation"}, timeout=0.04)
        self.assertEqual(res["error_code"], "IN_FLIGHT_TIMEOUT")

        # Timed-out task finishes
        finish_event.set()
        drain_thread.join(timeout=1.0)
        self.assertTrue(q._timed_out_mutation_finished)
        self.assertTrue(q._in_flight_timeout_unreconciled)

        # Successful genuine scene inspection reconciles state
        q.register_handler("list_objects", lambda bpy_module, params: {"objects": []})
        drain_thread_insp = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread_insp.start()
        res_insp = q.submit_and_wait({"type": "list_objects"}, timeout=1.0)
        drain_thread_insp.join(timeout=1.0)
        self.assertEqual(res_insp["status"], "success")

        # Barrier must now be cleared
        self.assertFalse(q._in_flight_timeout_unreconciled)

        # New mutations are permitted
        finish_event.clear()
        drain_thread_mut = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread_mut.start()
        finish_event.set()
        res_new_mut = q.submit_and_wait({"type": "slow_mutation"}, timeout=1.0)
        drain_thread_mut.join(timeout=1.0)
        self.assertEqual(res_new_mut["status"], "success")

    def test_ping_and_non_inspection_commands_cannot_clear_barrier(self):
        """
        TASK-UMCP-0055 (Requirement 2):
        Verify that ping, get_approval_settings, and check_approval_status
        do NOT clear the in-flight mutation reconciliation barrier, even if
        they execute and return success. Only genuine scene inspection clears the barrier.
        """
        q = MainThreadQueue()
        started_event = threading.Event()
        finish_event = threading.Event()

        def slow_mutation(bpy_module=None, params=None):
            started_event.set()
            finish_event.wait(timeout=1.0)
            return {"mutated": True}

        q.register_handler("slow_mutation", slow_mutation)
        q.register_handler("get_approval_settings", lambda bpy_module, params: {"mode": "require_all"})
        q.register_handler("get_scene_summary", lambda bpy_module, params: {"total_objects": 1})

        drain_thread = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread.start()

        # In-flight timeout on mutation
        res = q.submit_and_wait({"type": "slow_mutation"}, timeout=0.04)
        self.assertEqual(res["error_code"], "IN_FLIGHT_TIMEOUT")

        # Timed-out task finishes
        finish_event.set()
        drain_thread.join(timeout=1.0)
        self.assertTrue(q._timed_out_mutation_finished)
        self.assertTrue(q._in_flight_timeout_unreconciled)

        # 1. ping executes with success, but leaves barrier ACTIVE
        drain_thread_ping = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread_ping.start()
        res_ping = q.submit_and_wait({"type": "ping"}, timeout=1.0)
        drain_thread_ping.join(timeout=1.0)
        self.assertEqual(res_ping["status"], "success")
        self.assertTrue(q._in_flight_timeout_unreconciled, "Ping must NOT clear the reconciliation barrier!")

        # 2. get_approval_settings executes with success, but leaves barrier ACTIVE
        drain_thread_appr = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread_appr.start()
        res_appr = q.submit_and_wait({"type": "get_approval_settings"}, timeout=1.0)
        drain_thread_appr.join(timeout=1.0)
        self.assertEqual(res_appr["status"], "success")
        self.assertTrue(q._in_flight_timeout_unreconciled, "Approval settings must NOT clear the barrier!")

        # Blind mutation retry is STILL BLOCKED
        res_blocked = q.submit_and_wait({"type": "slow_mutation"}, timeout=0.5)
        self.assertEqual(res_blocked["error_code"], "BLIND_RETRY_BLOCKED")

        # 3. get_scene_summary genuinely inspects the scene and CLEARS the barrier
        drain_thread_sum = threading.Thread(target=lambda: (time.sleep(0.01), q.drain_queue()))
        drain_thread_sum.start()
        res_sum = q.submit_and_wait({"type": "get_scene_summary"}, timeout=1.0)
        drain_thread_sum.join(timeout=1.0)
        self.assertEqual(res_sum["status"], "success")
        self.assertFalse(q._in_flight_timeout_unreconciled, "Genuine scene inspection MUST clear the barrier!")


class TestQueueShutdownFormats(unittest.TestCase):
    def test_lifecycle_mutations_require_bound_tokens_at_network_dispatch(self):
        from types import SimpleNamespace as NS
        bpy=NS(context=NS(scene=NS(umcp_require_scene_mutation_approval=True)))
        q=MainThreadQueue(bpy_module=bpy);calls=[]
        for tool in ('delete_object','save_blend_file'):
            q.register_handler(tool,lambda **kwargs:calls.append(kwargs))
            event=threading.Event();result={}
            q._queue.put(({'type':tool,'params':{'approved':True,'trusted_approval':True}},event,result))
            q.drain_queue()
            self.assertTrue(event.is_set())
            self.assertEqual(result['response']['status'],'error')
            self.assertIn('approval',result['response']['message'].lower())
        self.assertEqual(calls,[])


    def test_pending_waiters_released_without_execution_for_all_supported_formats(self):
        from types import SimpleNamespace as NS
        q=MainThreadQueue(bpy_module=NS())
        entries=[]
        for kind in ('dict','legacy4','legacy3'):
            event=threading.Event();cancel=threading.Event();result={};command={'type':'must_not_execute'}
            task={'command':command,'event':event,'result_container':result,'cancel_event':cancel} if kind=='dict' else (command,event,result,cancel) if kind=='legacy4' else (command,event,result)
            q._queue.put(task);entries.append((kind,event,cancel,result))
        q.stop_timer()
        self.assertTrue(q._queue.empty())
        for kind,event,cancel,result in entries:
            self.assertTrue(event.is_set())
            self.assertEqual(result['response']['error_code'],'QUEUE_STOPPED')
            self.assertEqual(result['response']['execution_state'],'NOT_EXECUTED')
            if kind!='legacy3':self.assertTrue(cancel.is_set())


def _queue_approved(params):
    from blender_addon.universal_mcp.bridge.approval_registry import get_approval_registry
    params={k:v for k,v in params.items() if k not in ("trusted_approval","_trusted_test_override")}
    registry=get_approval_registry();request=registry.create_request("create_primitive",params)
    ok,token=registry.resolve_request(request.request_id,"approved")
    assert ok
    return {**params,"request_id":request.request_id,"approval_token":token}


if __name__ == "__main__":
    unittest.main()



