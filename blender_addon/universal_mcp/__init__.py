"""
Universal MCP for Blender Add-on.
Enables universal AI client integration (ChatGPT, Claude Desktop, Antigravity, Ollama)
via the Model Context Protocol (MCP) using a thread-safe loopback bridge.
"""

bl_info = {
    "name": "TechBot_Blender_MCP",
    "author": "Techbot81",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Universal MCP",
    "description": "Universal Model Context Protocol server/client integration for Blender",
    "category": "Generic",
}

from .properties import register_properties, unregister_properties
from .preferences import UniversalMCPPreferences
from .operators import (
    UMCP_OT_StartBridge,
    UMCP_OT_StopBridge,
    UMCP_OT_PingBridge,
    UMCP_OT_ApprovalDialog,
    UMCP_OT_ResolveApproval,
)
from .ui.panels import UMCP_PT_MainPanel
from .ui.panels import UMCP_PT_AboutPanel
from .branding import register_logo_preview, unregister_logo_preview

classes = (
    UniversalMCPPreferences,
    UMCP_OT_StartBridge,
    UMCP_OT_StopBridge,
    UMCP_OT_PingBridge,
    UMCP_OT_ApprovalDialog,
    UMCP_OT_ResolveApproval,
    UMCP_PT_MainPanel,
    UMCP_PT_AboutPanel,
)


def register():
    try:
        import bpy
        register_logo_preview()
        for cls in classes:
            bpy.utils.register_class(cls)
        register_properties()
    except ImportError:
        pass
    except Exception:
        unregister_logo_preview()
        raise


def unregister():
    try:
        import bpy
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
        unregister_properties()
    except Exception:
        pass
    finally:
        unregister_logo_preview()


if __name__ == "__main__":
    register()
