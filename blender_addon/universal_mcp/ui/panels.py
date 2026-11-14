"""
UI panels for Universal MCP add-on.
Pure standard library + bpy.
"""

import logging

_logger = logging.getLogger(__name__)

try:
    import bpy
    from bpy.types import Panel

    class UMCP_PT_MainPanel(Panel):
        bl_label = ""
        bl_idname = "UMCP_PT_MainPanel"
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = "Universal MCP"

        def draw_header(self, context):
            layout = self.layout
            try:
                from ..branding import get_logo_icon_id
                logo_icon_id = get_logo_icon_id()
                if logo_icon_id:
                    layout.label(text="", icon_value=logo_icon_id)
            except Exception:
                _logger.exception("Could not draw header Techbot81 branding icon")

        def draw(self, context):
            layout = self.layout
            scene = context.scene

            # Status Box
            box = layout.box()
            box.label(text="Bridge Status", icon='WORLD')
            row = box.row()
            if getattr(scene, "umcp_bridge_running", False):
                row.label(text="Status: Active", icon='CHECKMARK')
            else:
                row.label(text="Status: Stopped", icon='CANCEL')

            msg = getattr(scene, "umcp_status_message", "")
            if msg:
                box.label(text=msg, icon='INFO')

            # Configuration
            col = layout.column(align=True)
            col.prop(scene, "umcp_bridge_port", text="Port")
            if hasattr(scene, "umcp_require_scene_mutation_approval"):
                col.prop(scene, "umcp_require_scene_mutation_approval", text="Require Approval")

            # Control buttons
            row = layout.row(align=True)
            if not getattr(scene, "umcp_bridge_running", False):
                row.operator("umcp.start_bridge", text="Start Bridge", icon='PLAY')
            else:
                row.operator("umcp.stop_bridge", text="Stop Bridge", icon='PAUSE')
            row.operator("umcp.ping_bridge", text="Ping", icon='RADIOBUT_ON')

            # Approval Requests Section. Include recent terminal states so an
            # expired request is visible rather than disappearing silently.
            # Isolate registry and row
            # errors so one malformed request cannot hide the other actions.
            try:
                from ..bridge.approval_registry import get_approval_registry
                registry = get_approval_registry()
                requests = registry.get_recent_requests()
            except Exception:
                _logger.exception("Could not read pending Blender approval requests")
                layout.label(text="Approval requests are temporarily unavailable; see Blender log.", icon='ERROR')
                return

            if not requests:
                layout.label(text="No recent approval requests in this Blender registry.", icon='INFO')
                return

            layout.separator()
            p_box = layout.box()
            p_box.label(text="Recent Approval Requests:", icon='QUESTION')
            for req in requests:
                try:
                    sub = p_box.box()
                except Exception:
                    _logger.exception("Could not create panel row for pending approval %s", getattr(req, "request_id", "<unknown>"))
                    continue
                try:
                    if req.task_id:
                        sub.label(text=f"Task: {req.task_id}", icon='GROUP')
                    sub.label(text=f"Request ID: {req.request_id}")
                    sub.label(text=f"Tool: {req.tool_name}", icon='TOOL_SETTINGS')
                    sub.label(text=f"Status: {req.status}", icon='INFO')
                    if req.decision_reason:
                        sub.label(text=f"Reason: {req.decision_reason}", icon='INFO')
                    if req.tool_name == "create_primitive":
                        sub.label(text=f"Primitive: {req.params.get('primitive_type', 'N/A')}")
                        sub.label(text=f"Object: {req.params.get('name', 'N/A')}", icon='OBJECT_DATA')
                        loc = req.params.get('location', [0.0, 0.0, 0.0])
                        sub.label(text=f"Loc: [{loc[0]:.1f}, {loc[1]:.1f}, {loc[2]:.1f}]")
                        dims = req.params.get('dimensions', [1.0, 1.0, 1.0])
                        sub.label(text=f"Dims: [{dims[0]:.1f}, {dims[1]:.1f}, {dims[2]:.1f}]")
                    elif req.tool_name == "transform_object":
                        rel = req.params.get("relative", False)
                        sub.label(text=f"Object: {req.params.get('name', 'N/A')} ({'Rel' if rel else 'Abs'})", icon='OBJECT_DATA')
                        if "location" in req.params:
                            loc = req.params["location"]
                            sub.label(text=f"Loc: [{loc[0]:.1f}, {loc[1]:.1f}, {loc[2]:.1f}]")
                        if "rotation_euler" in req.params:
                            rot = req.params["rotation_euler"]
                            sub.label(text=f"Rot: [{rot[0]:.2f}, {rot[1]:.2f}, {rot[2]:.2f}]")
                        if "scale" in req.params:
                            sc = req.params["scale"]
                            sub.label(text=f"Scale: [{sc[0]:.2f}, {sc[1]:.2f}, {sc[2]:.2f}]")
                    else:
                        sub.label(text=f"Object: {req.params.get('name', 'N/A')}", icon='OBJECT_DATA')
                    sub.label(text=f"Expires in: {int(req.remaining_seconds)}s", icon='TIME')
                except Exception:
                    _logger.exception("Could not draw details for pending approval %s", getattr(req, "request_id", "<unknown>"))
                    sub.label(text="Request details unavailable; review carefully before resolving.", icon='ERROR')

                if req.status != "pending" or req.is_expired:
                    continue

                try:
                    btn_row = sub.row(align=True)
                    op_app = btn_row.operator("umcp.resolve_approval", text="Approve", icon='CHECKMARK')
                    op_app.request_id = req.request_id
                    op_app.action = "approve"

                    op_den = btn_row.operator("umcp.resolve_approval", text="Deny", icon='CANCEL')
                    op_den.request_id = req.request_id
                    op_den.action = "deny"

                    diag_row = sub.row()
                    op_diag = diag_row.operator("umcp.approval_dialog", text="Open Dialog", icon='WINDOW')
                    op_diag.request_id = req.request_id
                except Exception:
                    _logger.exception("Could not draw actions for pending approval %s", getattr(req, "request_id", "<unknown>"))


    class UMCP_PT_AboutPanel(Panel):
        bl_label = "About"
        bl_idname = "UMCP_PT_AboutPanel"
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = "Universal MCP"
        bl_parent_id = "UMCP_PT_MainPanel"
        bl_options = {'DEFAULT_CLOSED'}

        def draw(self, context):
            # Retrieve metadata safely across both legacy add-on and native extension modes
            bl_info = {}
            try:
                from .. import bl_info as _legacy_bl_info
                if isinstance(_legacy_bl_info, dict):
                    bl_info = _legacy_bl_info
            except (ImportError, AttributeError):
                pass

            if not bl_info:
                try:
                    import sys
                    import addon_utils
                    parent_pkg = __package__.rpartition('.')[0] if __package__ else "universal_mcp"
                    mod = sys.modules.get(parent_pkg)
                    if mod is not None:
                        bl_info = addon_utils.module_bl_info(mod)
                except Exception:
                    pass

            layout = self.layout

            # Text-only product identity and informational content
            col = layout.column(align=True)
            col.label(text=bl_info.get("name", "TechBot_Blender_MCP"))
            raw_ver = bl_info.get("version", (1, 0, 0))
            if isinstance(raw_ver, (tuple, list)):
                version_str = ".".join(str(part) for part in raw_ver)
            else:
                version_str = str(raw_ver)
            col.label(text=f"Version: {version_str}")

            desc = bl_info.get("description", "")
            if desc:
                layout.separator()
                box = layout.box()
                box.label(text="Description:", icon='INFO')
                words = desc.split()
                line = []
                for w in words:
                    line.append(w)
                    if len(" ".join(line)) > 30:
                        box.label(text=" ".join(line))
                        line = []
                if line:
                    box.label(text=" ".join(line))

            layout.separator()
            col_info = layout.column(align=True)
            author = bl_info.get("author") or bl_info.get("maintainer") or "Techbot81"
            col_info.label(text=f"Author: {author}")
            col_info.label(text=f"Created by {author}")

            b_ver = bl_info.get("blender", (4, 2, 0))
            if isinstance(b_ver, (tuple, list)) and len(b_ver) >= 3:
                blender_ver_str = f"{b_ver[0]}.{b_ver[1]}.{b_ver[2]}+ (Verified 5.2.2 LTS)"
            elif isinstance(b_ver, (tuple, list)):
                blender_ver_str = ".".join(str(x) for x in b_ver) + "+ (Verified 5.2.2 LTS)"
            else:
                blender_ver_str = f"{b_ver}+ (Verified 5.2.2 LTS)"
            col_info.label(text=f"Blender: {blender_ver_str}")

            doc_url = bl_info.get("doc_url")
            tracker_url = bl_info.get("tracker_url")
            if doc_url or tracker_url:
                layout.separator()
                row_links = layout.row(align=True)
                if doc_url:
                    op = row_links.operator("wm.url_open", text="Docs", icon='HELP')
                    op.url = doc_url
                if tracker_url:
                    op = row_links.operator("wm.url_open", text="Support", icon='URL')
                    op.url = tracker_url

except ImportError:
    class UMCP_PT_MainPanel:
        bl_idname = "UMCP_PT_MainPanel"

    class UMCP_PT_AboutPanel:
        bl_idname = "UMCP_PT_AboutPanel"
