"""
Blender property definitions for the Universal MCP Add-on.
Pure standard library + bpy.
"""

def _update_require_approval(self, context):
    try:
        val = bool(self.umcp_require_scene_mutation_approval)
        try:
            from .bridge.approval_registry import get_approval_registry
            get_approval_registry().require_scene_mutation_approval = val
        except Exception:
            pass

        try:
            from .preferences import get_preferences
            prefs = get_preferences(context)
            if prefs is not None and hasattr(prefs, "require_scene_mutation_approval"):
                if prefs.require_scene_mutation_approval != val:
                    prefs.require_scene_mutation_approval = val
                    try:
                        import bpy
                        bpy.ops.wm.save_userpref()
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception:
        pass


def register_properties():
    try:
        import bpy
        from bpy.props import IntProperty, BoolProperty, StringProperty, EnumProperty

        import os
        default_port = int(os.environ.get("UMCP_BRIDGE_PORT", "9877"))

        initial_approval_pref = True
        try:
            from .preferences import get_preferences
            prefs = get_preferences()
            if prefs is not None and hasattr(prefs, "require_scene_mutation_approval"):
                initial_approval_pref = bool(prefs.require_scene_mutation_approval)
        except Exception:
            pass

        try:
            from .bridge.approval_registry import get_approval_registry
            get_approval_registry().require_scene_mutation_approval = initial_approval_pref
        except Exception:
            pass

        bpy.types.Scene.umcp_bridge_port = IntProperty(
            name="Bridge Port",
            description="Loopback TCP port for Universal MCP communication",
            default=default_port,
            min=1024,
            max=65535,
        )

        bpy.types.Scene.umcp_bridge_running = BoolProperty(
            name="Bridge Running",
            description="Whether the local bridge is currently active",
            default=False,
        )

        bpy.types.Scene.umcp_auto_start = BoolProperty(
            name="Auto-start Bridge",
            description="Automatically start the bridge when Blender opens",
            default=True,
        )

        bpy.types.Scene.umcp_status_message = StringProperty(
            name="Status",
            description="Status message from the Universal MCP subsystem",
            default="Bridge ready",
        )

        bpy.types.Scene.umcp_require_scene_mutation_approval = BoolProperty(
            name="Require Scene Mutation Approval",
            description="Require explicit user approval dialog for scene mutations (uncheck to auto-approve)",
            default=initial_approval_pref,
            update=_update_require_approval,
        )
    except ImportError:
        pass


def unregister_properties():
    try:
        import bpy
        if hasattr(bpy.types.Scene, "umcp_bridge_port"):
            del bpy.types.Scene.umcp_bridge_port
        if hasattr(bpy.types.Scene, "umcp_bridge_running"):
            del bpy.types.Scene.umcp_bridge_running
        if hasattr(bpy.types.Scene, "umcp_auto_start"):
            del bpy.types.Scene.umcp_auto_start
        if hasattr(bpy.types.Scene, "umcp_status_message"):
            del bpy.types.Scene.umcp_status_message
        if hasattr(bpy.types.Scene, "umcp_require_scene_mutation_approval"):
            del bpy.types.Scene.umcp_require_scene_mutation_approval
    except Exception:
        pass
