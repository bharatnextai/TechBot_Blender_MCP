"""
Blender operators for Universal MCP service lifecycle control.
Pure standard library + bpy.
"""

from .bridge.main_thread_queue import get_main_thread_queue
from .bridge.bridge_server import BridgeServer
from .bridge.bridge_client import BridgeClient, is_port_in_use, probe_port
from .bridge.approval_registry import get_approval_registry

_server_instance = None


def get_server_instance(port: int = 9877) -> BridgeServer:
    global _server_instance
    if _server_instance is None or _server_instance.port != port:
        _server_instance = BridgeServer(port=port)
    return _server_instance


try:
    import bpy
    from bpy.types import Operator

    class UMCP_OT_StartBridge(Operator):
        """Start the Universal MCP Bridge Server"""
        bl_idname = "umcp.start_bridge"
        bl_label = "Start Bridge"
        bl_description = "Starts the local loopback bridge server for MCP clients"

        def execute(self, context):
            port = getattr(context.scene, "umcp_bridge_port", 9877)

            # Check port status safely to prevent conflict or disrupting external services
            port_status = probe_port("127.0.0.1", port)
            if port_status == "UMCP_BRIDGE":
                context.scene.umcp_bridge_running = True
                context.scene.umcp_status_message = f"Connected to active Universal MCP bridge on port {port}"
                self.report({'INFO'}, f"Connected to active Universal MCP bridge on port {port}")
                return {'FINISHED'}
            elif port_status == "EXTERNAL_SERVICE":
                context.scene.umcp_bridge_running = False
                context.scene.umcp_status_message = (
                    f"Port {port} is occupied by an external service (e.g. existing Blender MCP). "
                    "Universal MCP will not disrupt it. Please configure a different port."
                )
                self.report({'WARNING'}, f"Port {port} in use by external service. Refusing conflicting bind.")
                return {'CANCELLED'}

            try:
                server = get_server_instance(port=port)
                server.start()
                context.scene.umcp_bridge_running = True
                context.scene.umcp_status_message = f"Bridge running on port {port}"
                self.report({'INFO'}, f"Universal MCP Bridge started on port {port}")
                return {'FINISHED'}
            except Exception as e:
                context.scene.umcp_status_message = f"Error: {e}"
                self.report({'ERROR'}, f"Failed to start bridge: {e}")
                return {'CANCELLED'}

    class UMCP_OT_StopBridge(Operator):
        """Stop the Universal MCP Bridge Server"""
        bl_idname = "umcp.stop_bridge"
        bl_label = "Stop Bridge"
        bl_description = "Stops the local loopback bridge server"

        def execute(self, context):
            global _server_instance
            if _server_instance:
                _server_instance.stop()
                _server_instance = None
            context.scene.umcp_bridge_running = False
            context.scene.umcp_status_message = "Bridge stopped"
            self.report({'INFO'}, "Universal MCP Bridge stopped")
            return {'FINISHED'}

    class UMCP_OT_PingBridge(Operator):
        """Ping the Universal MCP Bridge to verify liveness"""
        bl_idname = "umcp.ping_bridge"
        bl_label = "Ping Bridge"
        bl_description = "Pings the bridge to verify connectivity"

        def execute(self, context):
            port = getattr(context.scene, "umcp_bridge_port", 9877)
            global _server_instance
            inst = _server_instance if _server_instance is not None else get_server_instance(port)
            if inst and getattr(inst, "running", False) and getattr(inst, "port", None) == port:
                context.scene.umcp_bridge_running = True
                context.scene.umcp_status_message = f"Pong received from port {port}"
                self.report({'INFO'}, f"Bridge liveness confirmed on port {port}")
                return {'FINISHED'}

            client = BridgeClient(port=port, timeout=3.0)
            try:
                ping_ok = False
                try:
                    ping_ok = client.ping()
                except Exception:
                    ping_ok = False

                if ping_ok:
                    context.scene.umcp_bridge_running = True
                    context.scene.umcp_status_message = f"Pong received from port {port}"
                    self.report({'INFO'}, f"Bridge liveness confirmed on port {port}")
                else:
                    context.scene.umcp_status_message = f"No response on port {port}"
                    self.report({'WARNING'}, f"Bridge not responding on port {port}")
            finally:
                client.close()
            return {'FINISHED'}

    class UMCP_OT_ApprovalDialog(Operator):
        """Review and Approve or Deny a proposed scene mutation from Universal MCP"""
        bl_idname = "umcp.approval_dialog"
        bl_label = "Universal MCP: Approve Scene Mutation"
        bl_description = "Blender-native approval dialog for incoming scene mutations"
        bl_options = {'REGISTER', 'INTERNAL'}

        request_id: bpy.props.StringProperty(name="Request ID")

        def invoke(self, context, event):
            wm = context.window_manager
            return wm.invoke_props_dialog(self, width=440)

        def draw(self, context):
            layout = self.layout
            registry = get_approval_registry()
            req = registry.get_request(self.request_id)

            if not req:
                layout.label(text="No pending request found or request expired.", icon='ERROR')
                return

            # Header Alert
            col = layout.column(align=True)
            col.label(text="Scene Mutation Approval Required", icon='QUESTION')
            col.label(text="An external AI assistant requests permission to modify the scene.", icon='INFO')
            layout.separator()

            # Parameter details box
            box = layout.box()
            box.label(text="Requested Mutation Details:", icon='PREFERENCES')
            row = box.row()
            row.label(text=f"Tool: {req.tool_name}")
            if req.tool_name == "create_primitive":
                row.label(text=f"Primitive: {req.params.get('primitive_type', 'N/A')}")
            elif req.tool_name == "transform_object":
                rel = req.params.get("relative", False)
                row.label(text=f"Mode: {'Relative' if rel else 'Absolute'}")

            name_label = "Material Name" if req.tool_name == "create_material" else "Object Name"
            box.label(text=f"{name_label}: {req.params.get('name', 'N/A')}", icon='OBJECT_DATA')

            if req.tool_name == "create_primitive":
                loc = req.params.get('location', [0.0, 0.0, 0.0])
                box.label(text=f"Target Location: [{loc[0]:.2f}, {loc[1]:.2f}, {loc[2]:.2f}]", icon='ORIENTATION_GLOBAL')

                dims = req.params.get('dimensions', [1.0, 1.0, 1.0])
                box.label(text=f"Dimensions: [{dims[0]:.2f}, {dims[1]:.2f}, {dims[2]:.2f}]", icon='CON_SIZELIMIT')

                change_box = layout.box()
                change_box.label(text="Proposed Scene Change:", icon='SCENE_DATA')
                change_box.label(
                    text=f"Adds a new MESH object '{req.params.get('name')}' to the active scene Collection."
                )
            elif req.tool_name == "transform_object":
                if "location" in req.params:
                    loc = req.params["location"]
                    box.label(text=f"Location: [{loc[0]:.2f}, {loc[1]:.2f}, {loc[2]:.2f}]", icon='ORIENTATION_GLOBAL')
                if "rotation_euler" in req.params:
                    rot = req.params["rotation_euler"]
                    box.label(text=f"Rotation (Euler rad): [{rot[0]:.2f}, {rot[1]:.2f}, {rot[2]:.2f}]", icon='DRIVER_ROTATIONAL_DIFFERENCE')
                if "scale" in req.params:
                    sc = req.params["scale"]
                    box.label(text=f"Scale: [{sc[0]:.2f}, {sc[1]:.2f}, {sc[2]:.2f}]", icon='CON_SIZELIMIT')

                change_box = layout.box()
                change_box.label(text="Proposed Scene Change:", icon='SCENE_DATA')
                rel = req.params.get("relative", False)
                mode_str = "relative offset" if rel else "absolute values"
                change_box.label(
                    text=f"Modifies transforms for '{req.params.get('name')}' ({mode_str})."
                )
            elif req.tool_name == "execute_blender_code":
                ops = req.params.get("operations", [])
                code = req.params.get("code")
                if ops:
                    box.label(text=f"Structured Modeling Plan: {len(ops)} operations", icon='MODIFIER')
                    for op in ops[:4]:
                        action = op.get("action", "op")
                        target = op.get("target", "scene")
                        box.label(text=f"  • {action} on '{target}'")
                    if len(ops) > 4:
                        box.label(text=f"  ... and {len(ops) - 4} more operations")
                if code:
                    box.label(text="Restricted Script (AST Validated):", icon='FILE_SCRIPT')
                    code_preview = code[:90].replace('\n', ' ')
                    box.label(text=f"  {code_preview}...")

                change_box = layout.box()
                change_box.label(text="Proposed Scene Change:", icon='SCENE_DATA')
                change_box.label(
                    text="Executes transactional modeling operations with automatic undo rollback on failure."
                )
            else:
                for k, v in req.params.items():
                    if k not in ("name", "approved", "trusted_approval", "request_id", "approval_token"):
                        box.label(text=f"{k}: {v}")


            # Task group info if available
            if req.task_id:
                task_reqs = registry.get_pending_requests_for_task(req.task_id)
                if len(task_reqs) > 1:
                    box.label(text=f"Task Group: {req.task_id} ({len(task_reqs)} operations pending)", icon='GROUP')
                    box.label(text="Clicking OK will approve all operations in this task group.", icon='INFO')
                else:
                    box.label(text=f"Task Group: {req.task_id}", icon='GROUP')

            # Countdown / Expiry
            rem = max(0, int(req.remaining_seconds))
            layout.label(text=f"Time Remaining: {rem}s (fails closed if unapproved)", icon='TIME')

            # Explicit action buttons
            row_actions = layout.row(align=True)
            row_actions.scale_y = 1.3
            op_approve = row_actions.operator("umcp.resolve_approval", text="Approve", icon='CHECKMARK')
            op_approve.request_id = self.request_id
            op_approve.action = "approve"

            op_deny = row_actions.operator("umcp.resolve_approval", text="Deny", icon='CANCEL')
            op_deny.request_id = self.request_id
            op_deny.action = "deny"

        def execute(self, context):
            registry = get_approval_registry()
            # Default OK button in props dialog approves all eligible requests in active task group
            ok, msg = registry.resolve_request(self.request_id, "approved", approve_task_group=True)
            if ok:
                req = registry.get_request(self.request_id)
                t_id = req.task_id if req else None
                if t_id:
                    self.report({'INFO'}, f"Mutation request '{self.request_id}' and active task group '{t_id}' approved.")
                else:
                    self.report({'INFO'}, f"Mutation request '{self.request_id}' approved.")
            else:
                self.report({'WARNING'}, f"Could not approve: {msg}")
            return {'FINISHED'}

        def cancel(self, context):
            registry = get_approval_registry()
            # Escaping or closing the dialog fails closed as cancelled (Deny/Cancel affects only this request)
            registry.resolve_request(self.request_id, "cancelled", reason="Dialog cancelled by user")
            self.report({'INFO'}, "Mutation request cancelled.")

    class UMCP_OT_ResolveApproval(Operator):
        """Approve or Deny a pending Universal MCP scene mutation request"""
        bl_idname = "umcp.resolve_approval"
        bl_label = "Resolve Approval"
        bl_description = "Explicitly approves or denies a pending mutation request"
        bl_options = {'REGISTER', 'INTERNAL'}

        request_id: bpy.props.StringProperty(name="Request ID")
        action: bpy.props.EnumProperty(
            name="Action",
            items=[
                ('approve', 'Approve', 'Approve the scene mutation and generate a single-use token'),
                ('deny', 'Deny', 'Deny the scene mutation and fail closed'),
            ],
            default='deny',
        )

        def execute(self, context):
            registry = get_approval_registry()
            decision = "approved" if self.action == 'approve' else "denied"
            # Approve resolves active task group if approved; deny resolves only the targeted request
            approve_group = (decision == "approved")
            ok, msg = registry.resolve_request(self.request_id, decision, approve_task_group=approve_group)
            if ok:
                status_str = "Approved" if decision == "approved" else "Denied"
                context.scene.umcp_status_message = f"Request {self.request_id}: {status_str}"
                diag_msg = "token generated (redacted)" if decision == "approved" else msg
                self.report({'INFO'}, f"Scene mutation {status_str.lower()}: request '{self.request_id}' {diag_msg}")
            else:
                self.report({'WARNING'}, f"Failed to resolve request '{self.request_id}': {msg}")
            return {'FINISHED'}

except ImportError:
    class UMCP_OT_StartBridge:
        bl_idname = "umcp.start_bridge"
    class UMCP_OT_StopBridge:
        bl_idname = "umcp.stop_bridge"
    class UMCP_OT_PingBridge:
        bl_idname = "umcp.ping_bridge"

        def report(self, level, msg):
            pass

        def execute(self, context):
            port = getattr(context.scene, "umcp_bridge_port", 9877)
            global _server_instance
            inst = _server_instance if _server_instance is not None else get_server_instance(port)
            if inst and getattr(inst, "running", False) and getattr(inst, "port", None) == port:
                context.scene.umcp_bridge_running = True
                context.scene.umcp_status_message = f"Pong received from port {port}"
                self.report({'INFO'}, f"Bridge liveness confirmed on port {port}")
                return {'FINISHED'}

            client = BridgeClient(port=port, timeout=3.0)
            try:
                ping_ok = False
                try:
                    ping_ok = client.ping()
                except Exception:
                    ping_ok = False

                if ping_ok:
                    context.scene.umcp_bridge_running = True
                    context.scene.umcp_status_message = f"Pong received from port {port}"
                    self.report({'INFO'}, f"Bridge liveness confirmed on port {port}")
                else:
                    context.scene.umcp_status_message = f"No response on port {port}"
                    self.report({'WARNING'}, f"Bridge not responding on port {port}")
            finally:
                client.close()
            return {'FINISHED'}

    class UMCP_OT_ApprovalDialog:
        bl_idname = "umcp.approval_dialog"
    class UMCP_OT_ResolveApproval:
        bl_idname = "umcp.resolve_approval"
