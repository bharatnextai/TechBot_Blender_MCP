"""Techbot81 branding helpers for the Blender extension UI."""

import os


CREATOR_NAME = "Techbot81"
_preview_collection = None


def register_logo_preview():
    """Load the bundled small logo for UI panels; safe to call repeatedly."""
    global _preview_collection
    if _preview_collection is not None:
        return _preview_collection

    try:
        import bpy
        from bpy.utils import previews
    except ImportError:
        return None

    icon_path = os.path.join(os.path.dirname(__file__), "assets", "techbot81_icon.png")
    if not os.path.isfile(icon_path):
        return None

    collection = previews.new()
    try:
        collection.load("techbot81", icon_path, 'IMAGE')
    except Exception:
        previews.remove(collection)
        raise
    _preview_collection = collection
    return collection


def unregister_logo_preview():
    """Release preview image resources when the extension unregisters."""
    global _preview_collection
    if _preview_collection is None:
        return
    try:
        from bpy.utils import previews
        previews.remove(_preview_collection)
    finally:
        _preview_collection = None


def get_logo_icon_id():
    """Return the registered Blender icon ID, or zero if unavailable."""
    if _preview_collection is None:
        return 0
    preview = _preview_collection.get("techbot81")
    return int(preview.icon_id) if preview else 0
