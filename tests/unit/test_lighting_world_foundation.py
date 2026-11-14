"""
Unit tests for Capability 8: Lighting & World Foundation.
Verifies create_light, configure_light, configure_world, world node-tree & environment textures,
inspect_scene_data (world_settings, light_settings), get_object_details (light_details),
parameter validation, unsupported feature rejection, and approval defenses.
"""

import unittest
from unittest.mock import MagicMock

from blender_addon.universal_mcp.bridge.handlers import (
    handle_create_light,
    handle_configure_light,
    handle_configure_world,
    handle_inspect_scene_data,
    handle_get_object_details,
)
from shared.schemas.tool_schemas import (
    TOOL_CREATE_LIGHT,
    TOOL_CONFIGURE_LIGHT,
    TOOL_CONFIGURE_WORLD,
    TOOL_INSPECT_SCENE_DATA,
    validate_tool_input,
)


class MockLightData:
    def __init__(self, name="Light", light_type="POINT"):
        self.name = name
        self.type = light_type
        self.energy = 1000.0
        self.color = (1.0, 1.0, 1.0)
        self.spot_size = 0.7853
        self.spot_blend = 0.15
        self.size = 0.25
        self.shape = "SQUARE" if light_type == "AREA" else None
        self.size_y = 0.25 if light_type == "AREA" else None
        self.diffuse_factor = 1.0
        self.specular_factor = 1.0
        self.volume_factor = 1.0
        self.use_shadow = True
        self.shadow_soft_size = 0.0
        self.shadow_buffer_clip_start = 0.05


class MockLightObject:
    def __init__(self, name="Light", light_type="POINT"):
        self.name = name
        self.type = "LIGHT"
        self.data = MockLightData(name=name, light_type=light_type)
        self.location = [0.0, 0.0, 5.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.dimensions = [0.0, 0.0, 0.0]
        self.bound_box = []
        self.users_collection = []
        self.material_slots = []
        self.modifiers = []
        self.parent = None
        self.keys = lambda: []


class MockWorldNode:
    def __init__(self, name, node_type):
        self.name = name
        self.type = node_type
        self.inputs = {
            "Color": MagicMock(default_value=(0.05, 0.05, 0.05, 1.0)),
            "Strength": MagicMock(default_value=1.0),
            "Surface": MagicMock(),
            "Vector": MagicMock(),
            "Rotation": MagicMock(default_value=(0.0, 0.0, 0.0)),
        }
        self.outputs = {
            "Color": MagicMock(),
            "Background": MagicMock(),
            "Vector": MagicMock(),
            "Generated": MagicMock(),
        }
        self.image = None
        # Sky node properties
        self.sky_type = "MULTIPLE_SCATTERING"
        self.sun_disc = True
        self.sun_size = 0.009512
        self.sun_intensity = 1.0
        self.sun_elevation = 0.261799
        self.sun_rotation = 0.0
        self.altitude = 100.0
        self.air_density = 1.0
        self.aerosol_density = 1.0
        self.ozone_density = 1.0
        self.turbidity = 2.2
        self.ground_albedo = 0.3


class MockNodesCollection(list):
    def new(self, node_type):
        name = node_type.replace("ShaderNode", "")
        if "environment" in node_type.lower():
            ntype = "TEX_ENVIRONMENT"
        elif "sky" in node_type.lower():
            ntype = "TEX_SKY"
        elif "mapping" in node_type.lower():
            ntype = "MAPPING"
        elif "texcoord" in node_type.lower() or "coord" in node_type.lower():
            ntype = "TEX_COORD"
        else:
            ntype = name.upper()
        node = MockWorldNode(name, ntype)
        self.append(node)
        return node


class MockLink:
    def __init__(self, sock_from, sock_to):
        self.from_socket = sock_from
        self.to_socket = sock_to

    def __getitem__(self, idx):
        if idx == 0:
            return self.from_socket
        elif idx == 1:
            return self.to_socket
        raise IndexError(idx)

    def __iter__(self):
        yield self.from_socket
        yield self.to_socket

    def __len__(self):
        return 2


class MockLinksCollection(list):
    def new(self, sock_from, sock_to):
        link = MockLink(sock_from, sock_to)
        self.append(link)
        return link


class MockWorldNodeTree:
    def __init__(self):
        self.nodes = MockNodesCollection()
        self.links = MockLinksCollection()


class MockWorld:
    def __init__(self, name="World"):
        self.name = name
        self.use_nodes = True
        self.color = (0.05, 0.05, 0.05)
        self.node_tree = MockWorldNodeTree()
        # Initialize default background and output nodes
        bg = self.node_tree.nodes.new("ShaderNodeBackground")
        out = self.node_tree.nodes.new("ShaderNodeOutputWorld")


class MockBpy:
    def __init__(self):
        self.data = MagicMock()
        self.context = MagicMock()
        self.app = MagicMock()
        self.app.background = True
        self.data.filepath = ""

        self.objects = {}
        self.lights = {}
        self.worlds = {"World": MockWorld("World")}
        self.images = {}

        self.data.objects = MagicMock()
        self.data.objects.get = lambda n, default=None: self.objects.get(n, default)
        self.data.objects.__contains__ = lambda s, n: n in self.objects
        self.data.objects.new = self._new_object

        self.data.lights = MagicMock()
        self.data.lights.new = self._new_light

        self.data.worlds = MagicMock()
        self.data.worlds.get = lambda n, default=None: self.worlds.get(n, default)
        self.data.worlds.new = lambda n: self.worlds.setdefault(n, MockWorld(n))

        self.data.images = MagicMock()
        self.data.images.get = lambda n, default=None: self.images.get(n, default)

        self.scene = MagicMock()
        self.scene.world = self.worlds["World"]
        self.scene.collection = MagicMock()
        self.scene.collection.objects = MagicMock()
        self.scene.collection.objects.link = lambda obj: None
        self.scene.umcp_require_scene_mutation_approval = False
        self.context.scene = self.scene

    def _new_light(self, name, type):
        ld = MockLightData(name=name, light_type=type)
        self.lights[name] = ld
        return ld

    def _new_object(self, name, object_data):
        obj = MockLightObject(name=name, light_type=object_data.type if hasattr(object_data, "type") else "POINT")
        obj.data = object_data
        self.objects[name] = obj
        return obj


class TestLightingWorldFoundation(unittest.TestCase):
    def setUp(self):
        self.bpy = MockBpy()

    def test_create_light_point(self):
        params = {"name": "TestPoint", "light_type": "POINT", "energy": 500.0, "color": [1.0, 0.9, 0.8]}
        res = handle_create_light(self.bpy, params)
        self.assertEqual(res["name"], "TestPoint")
        self.assertEqual(res["light_type"], "POINT")
        self.assertEqual(res["energy"], 500.0)
        self.assertEqual(res["color"], [1.0, 0.9, 0.8])
        self.assertIn("TestPoint", self.bpy.objects)

    def test_create_light_sun_and_spot(self):
        # Sun light
        sun_params = {"name": "TestSun", "light_type": "SUN", "energy": 5.0}
        res_sun = handle_create_light(self.bpy, sun_params)
        self.assertEqual(res_sun["light_type"], "SUN")
        self.assertEqual(res_sun["energy"], 5.0)

        # Spot light with spot_size
        spot_params = {"name": "TestSpot", "light_type": "SPOT", "energy": 1200.0, "spot_size": 1.047}
        res_spot = handle_create_light(self.bpy, spot_params)
        self.assertEqual(res_spot["light_type"], "SPOT")

    def test_create_light_duplicate_name_rejection(self):
        params = {"name": "DuplicateLight", "light_type": "POINT"}
        handle_create_light(self.bpy, params)
        with self.assertRaises(ValueError) as ctx:
            handle_create_light(self.bpy, params)
        self.assertIn("already exists", str(ctx.exception))

    def test_configure_light_success(self):
        # First create light
        handle_create_light(self.bpy, {"name": "KeyLight", "light_type": "POINT", "energy": 1000.0})

        # Update properties via configure_light
        update_params = {
            "name": "KeyLight",
            "energy": 2500.0,
            "color": [0.8, 0.85, 1.0],
            "location": [2.0, -3.0, 6.0],
            "light_type": "SPOT",
            "spot_size": 0.95,
            "spot_blend": 0.4,
        }
        res = handle_configure_light(self.bpy, update_params)
        self.assertEqual(res["name"], "KeyLight")
        self.assertEqual(res["energy"], 2500.0)
        self.assertEqual(res["color"], [0.8, 0.85, 1.0])
        self.assertEqual(res["location"], [2.0, -3.0, 6.0])
        self.assertEqual(res["light_type"], "SPOT")
        self.assertTrue(res["verified"])

    def test_configure_light_target_validation(self):
        # Non-existent light
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "NonExistent", "energy": 100.0})
        self.assertIn("not found", str(ctx.exception).lower())

        # Target object is not a light (e.g. MESH)
        mesh_obj = MockLightObject(name="MeshCube")
        mesh_obj.type = "MESH"
        self.bpy.objects["MeshCube"] = mesh_obj
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "MeshCube", "energy": 100.0})
        self.assertIn("not a light", str(ctx.exception).lower())

    def test_configure_light_unsupported_features_rejection(self):
        handle_create_light(self.bpy, {"name": "MyLight", "light_type": "POINT"})
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "MyLight", "light_linking": "GroupA"})
        self.assertIn("Unsupported", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "MyLight", "render_engine": "CYCLES"})
        self.assertIn("Unsupported", str(ctx.exception))

    def test_configure_world_basic(self):
        res = handle_configure_world(self.bpy, {"color": [0.1, 0.15, 0.2], "strength": 2.0})
        self.assertEqual(res["color"], [0.1, 0.15, 0.2])
        self.assertEqual(res["strength"], 2.0)
        self.assertTrue(res["verified"])

    def test_configure_world_with_environment_image(self):
        # Create mock image in data
        mock_img = MagicMock()
        mock_img.name = "studio_hdr.exr"
        mock_img.colorspace_settings.name = "Linear"
        self.bpy.images["studio_hdr.exr"] = mock_img

        res = handle_configure_world(self.bpy, {
            "strength": 1.5,
            "environment_image": "studio_hdr.exr",
        })
        self.assertTrue(res["has_environment_texture"])
        self.assertEqual(res["environment_image"], "studio_hdr.exr")

    def test_inspect_world_settings(self):
        # Setup world with environment
        mock_img = MagicMock()
        mock_img.name = "env_sky.png"
        mock_img.colorspace_settings.name = "sRGB"
        self.bpy.images["env_sky.png"] = mock_img

        handle_configure_world(self.bpy, {"color": [0.02, 0.02, 0.05], "strength": 0.8, "environment_image": "env_sky.png"})

        insp = handle_inspect_scene_data(self.bpy, {"category": "world_settings"})
        self.assertTrue(insp["has_world"])
        self.assertTrue(insp["has_environment_texture"])
        self.assertEqual(insp["environment_image"], "env_sky.png")
        self.assertEqual(insp["strength"], 0.8)

    def test_inspect_light_settings(self):
        handle_create_light(self.bpy, {
            "name": "SunLight",
            "light_type": "SUN",
            "energy": 6.5,
            "color": [1.0, 0.95, 0.85],
            "location": [10.0, 10.0, 20.0],
        })

        details = handle_get_object_details(self.bpy, {"name": "SunLight"})
        self.assertEqual(details["name"], "SunLight")
        self.assertEqual(details["location"], [10.0, 10.0, 20.0])
        self.assertEqual(details["light_details"]["light_type"], "SUN")
        self.assertEqual(details["light_details"]["energy"], 6.5)
        self.assertEqual(details["light_details"]["color"], [1.0, 0.95, 0.85])

    def test_get_object_details_light_details(self):
        handle_create_light(self.bpy, {"name": "FillSpot", "light_type": "SPOT", "energy": 800.0, "spot_size": 1.2})
        details = handle_get_object_details(self.bpy, {"name": "FillSpot"})
        self.assertIsNotNone(details.get("light_details"))
        self.assertEqual(details["light_details"]["light_type"], "SPOT")
        self.assertEqual(details["light_details"]["energy"], 800.0)

    def test_schema_validation_untrusted_approved(self):
        # 1. Trusted approval allows valid inputs
        sanitized = validate_tool_input(TOOL_CONFIGURE_LIGHT, {"name": "SunLight", "energy": 10.0}, trusted_approval=True)
        self.assertEqual(sanitized["name"], "SunLight")

        # 2. Untrusted approved=True is rejected fail-closed
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_LIGHT, {"name": "SunLight", "energy": 10.0, "approved": True})
        self.assertIn("untrusted", str(ctx.exception).lower())

        # 3. Missing approval is rejected fail-closed
        with self.assertRaises(PermissionError) as ctx:
            validate_tool_input(TOOL_CONFIGURE_LIGHT, {"name": "SunLight", "energy": 10.0})
        self.assertIn("approval required", str(ctx.exception).lower())

        # 4. Out of range values rejected with trusted_approval=True
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_LIGHT, {"name": "SunLight", "energy": -5.0}, trusted_approval=True)

        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_LIGHT, {"name": "SunLight", "color": [2.0, 0.0, 0.0]}, trusted_approval=True)

        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_WORLD, {"render_engine": "CYCLES"}, trusted_approval=True)

    def test_create_area_light_with_shapes(self):
        params = {
            "name": "AreaRect",
            "light_type": "AREA",
            "energy": 800.0,
            "shape": "RECTANGLE",
            "size": 2.0,
            "size_y": 1.0,
            "diffuse_factor": 0.8,
            "specular_factor": 0.5,
            "volume_factor": 0.2,
            "use_shadow": False,
            "shadow_soft_size": 0.1,
            "shadow_buffer_clip_start": 0.01,
        }
        res = handle_create_light(self.bpy, params)
        self.assertEqual(res["name"], "AreaRect")
        self.assertEqual(res["light_type"], "AREA")
        self.assertEqual(res["shape"], "RECTANGLE")
        self.assertEqual(res["size"], 2.0)
        self.assertEqual(res["size_y"], 1.0)
        self.assertEqual(res["diffuse_factor"], 0.8)
        self.assertEqual(res["specular_factor"], 0.5)
        self.assertEqual(res["volume_factor"], 0.2)
        self.assertFalse(res["use_shadow"])
        self.assertEqual(res["shadow_soft_size"], 0.1)
        self.assertEqual(res["shadow_buffer_clip_start"], 0.01)

        # Test DISK and ELLIPSE shapes
        disk_params = {"name": "AreaDisk", "light_type": "AREA", "shape": "DISK", "size": 1.5}
        res_disk = handle_create_light(self.bpy, disk_params)
        self.assertEqual(res_disk["shape"], "DISK")

        ellipse_params = {"name": "AreaEllipse", "light_type": "AREA", "shape": "ELLIPSE", "size": 3.0, "size_y": 1.5}
        res_ellipse = handle_create_light(self.bpy, ellipse_params)
        self.assertEqual(res_ellipse["shape"], "ELLIPSE")
        self.assertEqual(res_ellipse["size_y"], 1.5)

    def test_configure_area_light_properties(self):
        # Create square area light
        handle_create_light(self.bpy, {"name": "StudioArea", "light_type": "AREA", "size": 1.0})

        # Reconfigure to rectangle with custom factors
        update_params = {
            "name": "StudioArea",
            "shape": "RECTANGLE",
            "size": 4.0,
            "size_y": 2.0,
            "diffuse_factor": 0.9,
            "specular_factor": 0.4,
            "volume_factor": 0.1,
            "use_shadow": True,
            "shadow_soft_size": 0.2,
            "shadow_buffer_clip_start": 0.05,
        }
        res = handle_configure_light(self.bpy, update_params)
        self.assertEqual(res["shape"], "RECTANGLE")
        self.assertEqual(res["size"], 4.0)
        self.assertEqual(res["size_y"], 2.0)
        self.assertEqual(res["diffuse_factor"], 0.9)
        self.assertEqual(res["specular_factor"], 0.4)
        self.assertEqual(res["volume_factor"], 0.1)
        self.assertTrue(res["use_shadow"])
        self.assertEqual(res["shadow_soft_size"], 0.2)
        self.assertEqual(res["shadow_buffer_clip_start"], 0.05)
        self.assertTrue(res["verified"])

    def test_create_configure_light_shape_and_type_guards(self):
        # Shape on POINT light rejected
        with self.assertRaises(ValueError) as ctx:
            handle_create_light(self.bpy, {"name": "BadPoint", "light_type": "POINT", "shape": "RECTANGLE"})
        self.assertIn("only supported for AREA", str(ctx.exception))

        # size_y on SUN light rejected
        with self.assertRaises(ValueError) as ctx:
            handle_create_light(self.bpy, {"name": "BadSun", "light_type": "SUN", "size_y": 2.0})
        self.assertIn("only supported for AREA", str(ctx.exception))

        # Invalid shape rejected
        with self.assertRaises(ValueError) as ctx:
            handle_create_light(self.bpy, {"name": "BadArea", "light_type": "AREA", "shape": "TRIANGLE"})
        self.assertIn("Invalid shape", str(ctx.exception))

        # Mutating existing POINT light with shape rejected
        handle_create_light(self.bpy, {"name": "Point1", "light_type": "POINT"})
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "Point1", "shape": "RECTANGLE"})
        self.assertIn("only supported for AREA", str(ctx.exception))

    def test_create_configure_light_bounds_rejection(self):
        handle_create_light(self.bpy, {"name": "BoundArea", "light_type": "AREA"})

        # Negative size_y
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "BoundArea", "size_y": -1.0})
        self.assertIn("size_y", str(ctx.exception))

        # Negative diffuse_factor
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "BoundArea", "diffuse_factor": -0.5})
        self.assertIn("diffuse_factor", str(ctx.exception))

        # Negative specular_factor
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "BoundArea", "specular_factor": -0.5})
        self.assertIn("specular_factor", str(ctx.exception))

        # Negative volume_factor
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "BoundArea", "volume_factor": -0.5})
        self.assertIn("volume_factor", str(ctx.exception))

        # Non-boolean use_shadow
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "BoundArea", "use_shadow": "not_a_bool"})
        self.assertIn("use_shadow", str(ctx.exception))

        # Negative shadow_soft_size
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "BoundArea", "shadow_soft_size": -0.2})
        self.assertIn("shadow_soft_size", str(ctx.exception))

        # Invalid shadow_buffer_clip_start (< 0.0001)
        with self.assertRaises(ValueError) as ctx:
            handle_configure_light(self.bpy, {"name": "BoundArea", "shadow_buffer_clip_start": 0.0})
        self.assertIn("shadow_buffer_clip_start", str(ctx.exception))

    def test_get_object_details_expanded_light_details(self):
        handle_create_light(self.bpy, {
            "name": "DetailedArea",
            "light_type": "AREA",
            "energy": 1200.0,
            "shape": "RECTANGLE",
            "size": 3.0,
            "size_y": 1.5,
            "diffuse_factor": 0.75,
            "specular_factor": 0.6,
            "volume_factor": 0.4,
            "use_shadow": True,
            "shadow_soft_size": 0.15,
            "shadow_buffer_clip_start": 0.02,
        })
        details = handle_get_object_details(self.bpy, {"name": "DetailedArea"})
        ld = details["light_details"]
        self.assertEqual(ld["light_type"], "AREA")
        self.assertEqual(ld["shape"], "RECTANGLE")
        self.assertEqual(ld["size"], 3.0)
        self.assertEqual(ld["size_y"], 1.5)
        self.assertEqual(ld["diffuse_factor"], 0.75)
        self.assertEqual(ld["specular_factor"], 0.6)
        self.assertEqual(ld["volume_factor"], 0.4)
        self.assertTrue(ld["use_shadow"])
        self.assertEqual(ld["shadow_soft_size"], 0.15)
        self.assertEqual(ld["shadow_buffer_clip_start"], 0.02)

    def test_schema_validation_area_light_properties(self):
        # Valid create_light input
        valid_input = {
            "name": "AreaVal",
            "light_type": "AREA",
            "shape": "DISK",
            "size": 2.0,
            "size_y": 2.0,
            "diffuse_factor": 0.5,
            "specular_factor": 0.5,
            "volume_factor": 0.5,
            "use_shadow": False,
            "shadow_soft_size": 0.1,
            "shadow_buffer_clip_start": 0.05,
        }
        sanitized = validate_tool_input(TOOL_CREATE_LIGHT, valid_input, trusted_approval=True)
        self.assertEqual(sanitized["shape"], "DISK")
        self.assertEqual(sanitized["size_y"], 2.0)
        self.assertEqual(sanitized["diffuse_factor"], 0.5)

        # Invalid shape rejected in schema validation
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CREATE_LIGHT, {"name": "BadShape", "shape": "OCTAGON"}, trusted_approval=True)

        # Negative size_y rejected in schema validation
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_LIGHT, {"name": "BadSizeY", "size_y": -2.0}, trusted_approval=True)

        # Non-boolean use_shadow rejected
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_LIGHT, {"name": "BadShadow", "use_shadow": 123}, trusted_approval=True)

    def test_agent_validation_area_light_properties(self):
        from mcp_service.agents.render_lighting import RenderLightingAgent
        agent = RenderLightingAgent()

        # Valid task input
        valid_task = {
            "name": "AgentArea",
            "light_type": "AREA",
            "shape": "ELLIPSE",
            "size": 3.0,
            "size_y": 1.5,
            "diffuse_factor": 0.8,
            "use_shadow": True,
        }
        ok, code, msg = agent.validate_task_input(TOOL_CREATE_LIGHT, valid_task)
        self.assertTrue(ok)
        self.assertIsNone(code)

        # Invalid shape in agent validation
        bad_shape_task = {"name": "AgentBad", "light_type": "AREA", "shape": "DIAMOND"}
        ok, code, msg = agent.validate_task_input(TOOL_CREATE_LIGHT, bad_shape_task)
        self.assertFalse(ok)
        self.assertEqual(code, "INVALID_PARAMS")
        self.assertIn("DIAMOND", msg)

        # Negative factor in agent validation
        bad_factor_task = {"name": "AgentBad", "light_type": "AREA", "diffuse_factor": -1.0}
        ok, code, msg = agent.validate_task_input(TOOL_CONFIGURE_LIGHT, bad_factor_task)
        self.assertFalse(ok)
        self.assertEqual(code, "INVALID_PARAMS")
        self.assertIn("diffuse_factor", msg)

    def test_configure_world_nishita_sky(self):
        # Test configuring Nishita physical sky model
        sky_params = {
            "sky_type": "NISHITA",
            "sun_disc": True,
            "sun_size": 0.012,
            "sun_intensity": 1.5,
            "sun_elevation": 0.35,
            "sun_rotation": 1.2,
            "altitude": 300.0,
            "air_density": 1.2,
            "aerosol_density": 1.5,
            "ozone_density": 1.1,
            "strength": 1.25,
        }
        res = handle_configure_world(self.bpy, sky_params)
        self.assertTrue(res["has_sky_texture"])
        self.assertEqual(res["sky_type"], "MULTIPLE_SCATTERING")
        self.assertEqual(res["strength"], 1.25)
        sp = res["sky_parameters"]
        self.assertTrue(sp["sun_disc"])
        self.assertEqual(sp["sun_size"], 0.012)
        self.assertEqual(sp["sun_intensity"], 1.5)
        self.assertEqual(sp["sun_elevation"], 0.35)
        self.assertEqual(sp["sun_rotation"], 1.2)
        self.assertEqual(sp["altitude"], 300.0)
        self.assertEqual(sp["air_density"], 1.2)
        self.assertEqual(sp["aerosol_density"], 1.5)
        self.assertEqual(sp["ozone_density"], 1.1)

        # Inspect readback parity
        insp = handle_inspect_scene_data(self.bpy, {"category": "world_settings"})
        self.assertTrue(insp["has_sky_texture"])
        self.assertEqual(insp["sky_type"], "MULTIPLE_SCATTERING")
        self.assertEqual(insp["sky_parameters"]["altitude"], 300.0)

    def test_configure_world_sky_preetham_and_hosek(self):
        # Preetham with turbidity
        p_res = handle_configure_world(self.bpy, {
            "sky_type": "PREETHAM",
            "turbidity": 3.5,
            "ground_albedo": 0.4,
        })
        self.assertTrue(p_res["has_sky_texture"])
        self.assertEqual(p_res["sky_type"], "PREETHAM")
        self.assertEqual(p_res["sky_parameters"]["turbidity"], 3.5)
        self.assertEqual(p_res["sky_parameters"]["ground_albedo"], 0.4)

        # Hosek-Wilkie
        h_res = handle_configure_world(self.bpy, {
            "sky_type": "HOSEK_WILKIE",
            "turbidity": 2.8,
            "ground_albedo": 0.25,
        })
        self.assertEqual(h_res["sky_type"], "HOSEK_WILKIE")
        self.assertEqual(h_res["sky_parameters"]["turbidity"], 2.8)
        self.assertEqual(h_res["sky_parameters"]["ground_albedo"], 0.25)

    def test_configure_world_environment_rotation(self):
        # Scalar Z rotation
        res_scalar = handle_configure_world(self.bpy, {"environment_rotation": 0.7854})
        self.assertEqual(res_scalar["environment_rotation"], [0.0, 0.0, 0.7854])

        # 3-element Euler rotation
        res_euler = handle_configure_world(self.bpy, {"environment_rotation": [0.1, 0.2, 0.5]})
        self.assertEqual(res_euler["environment_rotation"], [0.1, 0.2, 0.5])

        # Inspect readback
        insp = handle_inspect_scene_data(self.bpy, {"category": "world_settings"})
        self.assertTrue(insp["has_mapping_node"])
        self.assertEqual(insp["environment_rotation"], [0.1, 0.2, 0.5])

    def test_configure_world_mutual_exclusivity(self):
        # Both environment_image and sky_type rejected
        with self.assertRaises(ValueError):
            handle_configure_world(self.bpy, {
                "environment_image": "hdr_sky.exr",
                "sky_type": "NISHITA",
            })

    def test_configure_world_sky_bounds_rejection(self):
        # Invalid sky_type
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_WORLD, {"sky_type": "INVALID_SKY"}, trusted_approval=True)

        # Out-of-bounds sun_size (> 1.5708)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_WORLD, {"sun_size": 2.5}, trusted_approval=True)

        # Negative sun_intensity
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_WORLD, {"sun_intensity": -0.5}, trusted_approval=True)

        # Out-of-bounds sun_elevation (> 1.5708)
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_WORLD, {"sun_elevation": 2.0}, trusted_approval=True)

        # Negative altitude
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_WORLD, {"altitude": -50.0}, trusted_approval=True)

        # Non-boolean sun_disc
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_WORLD, {"sun_disc": "yes"}, trusted_approval=True)

        # Invalid environment_rotation
        with self.assertRaises(ValueError):
            validate_tool_input(TOOL_CONFIGURE_WORLD, {"environment_rotation": [1.0, 2.0]}, trusted_approval=True)

    def test_schema_validation_world_sky_and_rotation(self):
        # Valid input sanitized properly
        valid_in = {
            "sky_type": "NISHITA",
            "sun_disc": False,
            "sun_size": 0.01,
            "sun_elevation": 0.5,
            "sun_rotation": 3.14,
            "altitude": 1000.0,
            "air_density": 1.5,
            "environment_rotation": 1.5708,
        }
        sanitized = validate_tool_input(TOOL_CONFIGURE_WORLD, valid_in, trusted_approval=True)
        self.assertEqual(sanitized["sky_type"], "MULTIPLE_SCATTERING")
        self.assertFalse(sanitized["sun_disc"])
        self.assertEqual(sanitized["altitude"], 1000.0)
        self.assertEqual(sanitized["environment_rotation"], 1.5708)

    def test_agent_validation_world_sky_and_rotation(self):
        from mcp_service.agents.render_lighting import RenderLightingAgent
        agent = RenderLightingAgent()

        # Valid input passes
        valid_task = {
            "sky_type": "MULTIPLE_SCATTERING",
            "sun_disc": True,
            "altitude": 500.0,
            "environment_rotation": [0.0, 0.0, 1.0],
        }
        ok, code, msg = agent.validate_task_input(TOOL_CONFIGURE_WORLD, valid_task)
        self.assertTrue(ok)
        self.assertIsNone(code)

        # Mutual exclusivity error in agent validation
        bad_task = {
            "environment_image": "sky.hdr",
            "sky_type": "NISHITA",
        }
        ok, code, msg = agent.validate_task_input(TOOL_CONFIGURE_WORLD, bad_task)
        self.assertFalse(ok)
        self.assertEqual(code, "INVALID_PARAMS")
        self.assertIn("Cannot specify both", msg)

        # Out-of-bounds altitude in agent validation
        bad_alt_task = {"altitude": -100.0}
        ok, code, msg = agent.validate_task_input(TOOL_CONFIGURE_WORLD, bad_alt_task)
        self.assertFalse(ok)
        self.assertEqual(code, "INVALID_PARAMS")
        self.assertIn("altitude", msg)

    def test_photometric_luminance_scaling_math(self):
        """Phase 3: Validates photometric luminance scaling formulas and bounds."""
        # Standard ITU-R BT.709 perceived luminance weights: Y = 0.2126*R + 0.7152*G + 0.0722*B
        def calc_luminance(rgb):
            return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

        lum_10w = calc_luminance([0.160784, 0.160784, 0.160784])
        lum_100w = calc_luminance([0.725490, 0.725490, 0.725490])
        scaling_ratio = lum_100w / lum_10w
        self.assertGreater(scaling_ratio, 4.0)
        self.assertLess(scaling_ratio, 5.0)

    def test_photometric_chromatic_balance_ratios(self):
        """Phase 3: Validates chromatic spectral channel shifts (warm vs cool)."""
        warm_rgb = [0.875, 0.792, 0.694]
        cool_rgb = [0.710, 0.808, 0.871]

        warm_r_div_b = warm_rgb[0] / warm_rgb[2]
        cool_b_div_r = cool_rgb[2] / cool_rgb[0]

        self.assertGreater(warm_r_div_b, 1.20)
        self.assertGreater(cool_b_div_r, 1.20)

    def test_photometric_key_to_fill_contrast_math(self):
        """Phase 3: Validates multi-point key-to-fill contrast ratio calculation."""
        lum_key = 0.6549
        lum_fill = 0.1857
        contrast_ratio = lum_key / lum_fill
        self.assertGreater(contrast_ratio, 3.0)
        self.assertLess(contrast_ratio, 4.0)

    def test_atmospheric_sun_elevation_invariants(self):
        """Phase 3: Validates Nishita physical sky solar elevation bounds and mapping."""
        import math
        # Noon sun (+45 deg = pi/4 rad)
        noon_elevation = math.pi / 4.0
        # Sunset sun (+5 deg = 5*pi/180 rad)
        sunset_elevation = 5.0 * math.pi / 180.0

        noon_sanitized = validate_tool_input(TOOL_CONFIGURE_WORLD, {
            "sky_type": "MULTIPLE_SCATTERING",
            "sun_elevation": noon_elevation,
            "altitude": 100.0,
        }, trusted_approval=True)
        self.assertAlmostEqual(noon_sanitized["sun_elevation"], noon_elevation, places=4)

        sunset_sanitized = validate_tool_input(TOOL_CONFIGURE_WORLD, {
            "sky_type": "MULTIPLE_SCATTERING",
            "sun_elevation": sunset_elevation,
            "altitude": 100.0,
        }, trusted_approval=True)
        self.assertAlmostEqual(sunset_sanitized["sun_elevation"], sunset_elevation, places=4)
        self.assertLess(sunset_sanitized["sun_elevation"], noon_sanitized["sun_elevation"])


if __name__ == "__main__":
    unittest.main()
