"""Private target-only evaluation for the three bounded silhouette optimizers."""
import threading


def evaluate_target_silhouette(bpy, params, target):
    """Isolate visible geometry for both render and GUI capture; restore on every exit.

    Modifier/constraint operands remain in the scene for dependency evaluation.
    They are excluded from direct capture, not removed from the target's geometry.
    Public whole-scene comparison/capture behavior is intentionally unchanged.
    """
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Target silhouette evaluation requires Blender main thread')
    scene = bpy.context.scene
    layer = bpy.context.view_layer
    if scene.objects.get(target.name) != target or target.type != 'MESH':
        raise ValueError('Target silhouette requires an active-scene mesh')
    if target.hide_render:
        raise ValueError('TARGET_NOT_VISIBLE: target is hidden from rendering')
    camera = scene.objects.get(params['camera_name']) if params.get('camera_name') else scene.camera
    if camera is None or camera.type != 'CAMERA':
        raise ValueError('Target silhouette requires an active-scene camera')
    original_camera = scene.camera
    camera_state = (camera.location.copy(), camera.rotation_euler.copy(), camera.data.type, camera.data.ortho_scale)
    render = scene.render
    render_state = (render.resolution_x, render.resolution_y, render.resolution_percentage,
                    render.filepath, render.image_settings.file_format, render.film_transparent)
    hidden = []
    try:
        scene.camera = camera
        for obj in scene.objects:
            # Keep lights and the chosen camera; neither contributes a surface mask.
            if obj == target or obj == camera or obj.type == 'LIGHT':
                continue
            hidden.append((obj, obj.hide_render, obj.hide_get(view_layer=layer),
                           obj.select_get(view_layer=layer)))
            obj.hide_render = True
            obj.hide_set(True, view_layer=layer)
        layer.update()
        from .handlers import handle_compare_silhouette_alignment
        comparison = dict(params)
        # Camera captures have a transparent film. Even a frame-filling target
        # (all alpha=1) is foreground; corner RGB must not erase its silhouette.
        comparison['_target_only_alpha'] = True
        return handle_compare_silhouette_alignment(bpy_module=bpy, params=comparison)
    finally:
        failures = []
        for obj, render_hidden, viewport_hidden, selected in reversed(hidden):
            try:
                obj.hide_render = render_hidden
                obj.hide_set(viewport_hidden, view_layer=layer)
            except Exception as error:
                failures.append(str(error))
            try:
                # Hiding deselects objects; restore selection after visibility,
                # even when another cleanup write failed.
                obj.select_set(selected, view_layer=layer)
            except Exception as error:
                failures.append(str(error))
        try:
            scene.camera = original_camera
            camera.location, camera.rotation_euler, camera.data.type, camera.data.ortho_scale = camera_state
            (render.resolution_x, render.resolution_y, render.resolution_percentage,
             render.filepath, render.image_settings.file_format, render.film_transparent) = render_state
            layer.update()
        except Exception as error:
            failures.append(str(error))
        if failures:
            raise RuntimeError('SILHOUETTE_RESTORE_FAILED: ' + '; '.join(failures))
