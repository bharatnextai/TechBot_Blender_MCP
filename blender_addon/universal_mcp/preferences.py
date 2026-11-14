"""
Add-on preferences for Universal MCP.
Pure standard library + bpy.
"""

try:
    import bpy
    from bpy.types import AddonPreferences
    from bpy.props import IntProperty, BoolProperty, StringProperty

    import os
    default_port_val = int(os.environ.get("UMCP_BRIDGE_PORT", "9877"))

    def _pref_update_require_approval(self, context):
        val = bool(self.require_scene_mutation_approval)
        try:
            from .bridge.approval_registry import get_approval_registry
            get_approval_registry().require_scene_mutation_approval = val
        except Exception:
            pass
        if context and hasattr(context, "scene") and context.scene:
            if hasattr(context.scene, "umcp_require_scene_mutation_approval"):
                if context.scene.umcp_require_scene_mutation_approval != val:
                    context.scene.umcp_require_scene_mutation_approval = val

    class UniversalMCPPreferences(AddonPreferences):
        bl_idname = __package__ if __package__ else "universal_mcp"

        default_port: IntProperty(
            name="Default Port",
            description="Default loopback bridge TCP port",
            default=default_port_val,
            min=1024,
            max=65535,
        )

        auto_start: BoolProperty(
            name="Auto-start Bridge on Load",
            description="Automatically start the bridge when Blender initializes",
            default=True,
        )

        require_scene_mutation_approval: BoolProperty(
            name="Require Scene Mutation Approval",
            description="Require explicit user approval dialog for scene mutations (uncheck to auto-approve)",
            default=True,
            update=_pref_update_require_approval,
        )

        def draw(self, context):
            layout = self.layout
            layout.prop(self, "default_port")
            layout.prop(self, "auto_start")
            layout.prop(self, "require_scene_mutation_approval")


    def get_preferences(context=None):
        """Retrieves UniversalMCPPreferences from active Blender context."""
        if context is None:
            try:
                import bpy
                context = bpy.context
            except ImportError:
                return None
        pref_mgr = getattr(context, "preferences", None)
        if not pref_mgr:
            return None
        addons = getattr(pref_mgr, "addons", {})
        if __package__ in addons and hasattr(addons[__package__], "preferences"):
            return addons[__package__].preferences
        if "universal_mcp" in addons and hasattr(addons["universal_mcp"], "preferences"):
            return addons["universal_mcp"].preferences
        for name, addon in addons.items():
            if name.endswith("universal_mcp") and hasattr(addon, "preferences"):
                return addon.preferences
        return None

except ImportError:
    class UniversalMCPPreferences:
        bl_idname = "universal_mcp"
        require_scene_mutation_approval = True

    def get_preferences(context=None):
        if context is None:
            return None
        pref_mgr = getattr(context, "preferences", None)
        if not pref_mgr:
            return None
        addons = getattr(pref_mgr, "addons", {})
        if __package__ in addons and hasattr(addons[__package__], "preferences"):
            return addons[__package__].preferences
        if "universal_mcp" in addons and hasattr(addons["universal_mcp"], "preferences"):
            return addons["universal_mcp"].preferences
        for name, addon in addons.items():
            if name.endswith("universal_mcp") and hasattr(addon, "preferences"):
                return addon.preferences
        return None

