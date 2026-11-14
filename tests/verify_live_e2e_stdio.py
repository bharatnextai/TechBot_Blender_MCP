"""
Live End-to-End Verification Test for Universal MCP over stdio transport.

Tests against a live Blender 5.2.2 LTS instance:
1. Spawns the MCP service as a subprocess using stdio transport targeting bridge port 9877.
2. Initializes the MCP protocol session.
3. Verifies supported read-only tools are discoverable.
4. Invokes get_scene_summary and list_objects against live Blender scene.
5. Compares scene object count and type counts before and after inspection.
"""

import asyncio
import json
import os
import sys
from typing import Dict, Any

from mcp import ClientSession, StdioServerParameters, stdio_client


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


async def run_live_verification():
    print("=" * 80)
    print("UNIVERSAL MCP: LIVE END-TO-END STDIO VERIFICATION")
    print("=" * 80)

    bridge_port = int(os.environ.get("UMCP_BRIDGE_PORT", "9877"))
    print(f"\n[Step 1] Target Loopback Bridge: 127.0.0.1:{bridge_port}")
    
    server_env = dict(os.environ)
    server_env["PYTHONPATH"] = PROJECT_ROOT
    server_env["PYTHONUNBUFFERED"] = "1"

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m", "mcp_service.app",
            "--transport", "stdio",
            "--bridge-port", str(bridge_port),
            "--bridge-timeout", "15.0"
        ],
        env=server_env
    )

    print(f"[Step 2] Spawning MCP stdio server: {sys.executable} -m mcp_service.app ...")
    
    async with stdio_client(server_params) as (read_stream, write_stream):
        print("  -> stdio pipe connected successfully.")
        
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Initialize MCP Protocol
            print("\n[Step 3] Initializing MCP Session...")
            init_result = await session.initialize()
            print(f"  -> Protocol Version: {init_result.protocolVersion}")
            print(f"  -> Server Name:     {init_result.serverInfo.name} v{init_result.serverInfo.version}")
            print(f"  -> Capabilities:    {list(init_result.capabilities.model_dump().keys())}")

            # 2. Tool Discovery
            print("\n[Step 4] Tool Discovery:")
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"  -> Discovered {len(tools_result.tools)} tools: {tool_names}")
            
            expected_tools = [
                "get_scene_summary",
                "list_objects",
                "get_object_details",
                "list_materials"
            ]
            for exp in expected_tools:
                assert exp in tool_names, f"Expected tool '{exp}' not found in discovery list"
            print("  -> All 4 expected tools verified.")

            for t in tools_result.tools:
                print(f"     * {t.name}: {t.description[:60]}... (Schema: {list(t.inputSchema.get('properties', {}).keys())})")

            # 3. Invoke Tool 1: get_scene_summary
            print("\n[Step 5] Invoking 'get_scene_summary' on Live Scene...")
            summary_res = await session.call_tool(
                "get_scene_summary",
                arguments={"include_collections": True}
            )
            assert not summary_res.isError, f"Tool get_scene_summary returned error: {summary_res.content}"
            raw_text = summary_res.content[0].text
            summary_outer = json.loads(raw_text)
            print("  -> Execution Succeeded! Response:")
            print(json.dumps(summary_outer, indent=4))
            
            summary_data = summary_outer.get("result", summary_outer)
            assert "scene_name" in summary_data, "Response missing scene_name"
            assert "total_objects" in summary_data, "Response missing total_objects"
            assert summary_data["total_objects"] >= 1, "Expected at least 1 object in scene"
            initial_object_count = summary_data["total_objects"]

            # 4. Invoke Tool 2: list_objects
            print("\n[Step 6] Invoking 'list_objects' on Live Scene...")
            list_res = await session.call_tool(
                "list_objects",
                arguments={"limit": 50}
            )
            assert not list_res.isError, f"Tool list_objects returned error: {list_res.content}"
            objects_outer = json.loads(list_res.content[0].text)
            objects_data = objects_outer.get("result", objects_outer)
            print(f"  -> Execution Succeeded! Found {objects_data.get('total_matching')} objects:")
            for o in objects_data.get("objects", []):
                print(f"     * {o['name']} (Type: {o['type']}, Collections: {o.get('collections')})")

            assert objects_data.get("total_matching") == initial_object_count, "Object count mismatch"

            # 5. Invoke Tool 3: get_object_details for "Cube"
            if any(o["name"] == "Cube" for o in objects_data.get("objects", [])):
                print("\n[Step 7] Invoking 'get_object_details' for 'Cube'...")
                details_res = await session.call_tool(
                    "get_object_details",
                    arguments={"name": "Cube", "include_mesh_stats": True}
                )
                assert not details_res.isError, f"Tool get_object_details returned error: {details_res.content}"
                details_outer = json.loads(details_res.content[0].text)
                details_data = details_outer.get("result", details_outer)
                print(f"  -> Cube Details: type={details_data.get('type')}, loc={details_data.get('location')}, mesh_stats={details_data.get('mesh_stats')}")

            # 6. Invoke Tool 4: list_materials
            print("\n[Step 8] Invoking 'list_materials' on Live Scene...")
            mats_res = await session.call_tool(
                "list_materials",
                arguments={}
            )
            assert not mats_res.isError, f"Tool list_materials returned error: {mats_res.content}"
            mats_outer = json.loads(mats_res.content[0].text)
            mats_data = mats_outer.get("result", mats_outer)
            print(f"  -> Materials Count: {mats_data.get('total_materials')}, Materials: {[m['name'] for m in mats_data.get('materials', [])]}")

            # 7. Scene Immutability Check
            print("\n[Step 9] Verifying Scene Immutability (Post-Invocation Summary Check)...")
            summary_res_2 = await session.call_tool(
                "get_scene_summary",
                arguments={"include_collections": True}
            )
            summary_outer_2 = json.loads(summary_res_2.content[0].text)
            summary_data_2 = summary_outer_2.get("result", summary_outer_2)
            assert summary_data_2["total_objects"] == initial_object_count, "Scene was mutated! Object count changed."
            assert summary_data_2["object_counts_by_type"] == summary_data["object_counts_by_type"], "Object types changed."
            print("  -> CONFIRMED: Object count and type counts are unchanged. This check does not prove full scene or material invariance.")

    print("\n" + "=" * 80)
    print("ALL LIVE END-TO-END VERIFICATION CHECKS PASSED SUCCESSFULLY")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = asyncio.run(run_live_verification())
    sys.exit(0 if success else 1)
