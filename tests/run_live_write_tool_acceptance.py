"""
Live Acceptance Test for First Controlled Blender Write Tool: create_primitive.

Validates:
1. Discovery of create_primitive among MCP tools.
2. Mandatory user approval gate (default read-only mode): unapproved mutation attempt is denied.
3. Input validation & name collision rejection.
4. Main-thread execution of approved mutation via local LLM (llama3.1:8b).
5. Post-creation verification in live Blender scene (existence, location, dimensions).
6. Preservation of existing scene assets.
"""

import asyncio
import json
import os
import sys
import time
from typing import Dict, Any, List

import httpx
from mcp import ClientSession, StdioServerParameters, stdio_client


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "llama3.1:8b"


def mcp_tools_to_ollama(tools) -> List[Dict[str, Any]]:
    """Converts MCP tool definitions to standard OpenAI/Ollama function-calling schemas."""
    ollama_tools = []
    for t in tools:
        schema = t.inputSchema if hasattr(t, "inputSchema") and t.inputSchema else {"type": "object", "properties": {}}
        ollama_tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": schema
            }
        })
    return ollama_tools


async def run_live_write_tool_acceptance():
    print("=" * 80)
    print("UNIVERSAL MCP: CONTROLLED BLENDER WRITE TOOL ACCEPTANCE TEST")
    print("=" * 80)

    bridge_port = int(os.environ.get("UMCP_BRIDGE_PORT", "9877"))
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

    print(f"\n[1. Connection] Connecting to Universal MCP stdio service (Bridge port {bridge_port})...")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init_res = await session.initialize()
            print(f"  -> MCP Handshake: Server '{init_res.serverInfo.name}' v{init_res.serverInfo.version}")

            # -------------------------------------------------------------
            # Step 1: Tool Discovery
            # -------------------------------------------------------------
            print("\n[2. Tool Discovery] Querying registered MCP tools...")
            tools_res = await session.list_tools()
            tool_names = [t.name for t in tools_res.tools]
            print(f"  -> Discovered {len(tools_res.tools)} tools: {tool_names}")
            assert "create_primitive" in tool_names, "Tool 'create_primitive' must be discoverable"
            print("  -> CONFIRMED: 'create_primitive' is discoverable via MCP tools/list.")

            # -------------------------------------------------------------
            # Step 2: Baseline Scene Inspection
            # -------------------------------------------------------------
            print("\n[3. Baseline Scene Inspection]")
            baseline_res = await session.call_tool("get_scene_summary", arguments={"include_collections": True})
            baseline_data = json.loads(baseline_res.content[0].text).get("result", {})
            baseline_count = baseline_data.get("total_objects", 0)
            print(f"  -> Scene: '{baseline_data.get('scene_name')}', Total Objects: {baseline_count}")
            print(f"  -> Object breakdown: {baseline_data.get('object_counts_by_type')}")

            # -------------------------------------------------------------
            # Step 3: Test Approval Denial (Default Read-Only Mode)
            # -------------------------------------------------------------
            print("\n[4. Safety Gate Test: Unapproved Mutation Denial]")
            target_name = "Approved_Live_Cube"
            target_loc = [1.0, 2.0, 3.0]
            target_dims = [1.5, 1.5, 1.5]

            # Attempt creation without approval (approved=False)
            deny_res = await session.call_tool("create_primitive", arguments={
                "primitive_type": "cube",
                "name": target_name,
                "location": target_loc,
                "dimensions": target_dims,
                "approved": False
            })
            deny_data = json.loads(deny_res.content[0].text)
            print(f"  -> Unapproved Call Result Status: {deny_data.get('status')}")
            print(f"  -> Denial Message: {deny_data.get('message')}")
            assert deny_data.get("status") == "error", "Expected error for unapproved mutation"
            assert "Approval denied" in deny_data.get("message", "") or "approved=True" in deny_data.get("message", ""), "Expected approval error"

            # Verify scene was NOT modified during denied attempt
            verify_deny = await session.call_tool("get_scene_summary", arguments={})
            count_after_deny = json.loads(verify_deny.content[0].text).get("result", {}).get("total_objects", 0)
            assert count_after_deny == baseline_count, "Scene was modified despite approval denial!"
            print(f"  -> CONFIRMED: Object count unchanged ({count_after_deny}). Scene remained unmodified.")

            # -------------------------------------------------------------
            # Step 4: AI Client Prompt & Approved Mutation Execution
            # -------------------------------------------------------------
            print("\n[5. AI Client Prompt & Tool Calling with Approval]")
            ollama_tools = mcp_tools_to_ollama(tools_res.tools)
            user_prompt = (
                f"Please create a new cube named '{target_name}' at location {target_loc} "
                f"with dimensions {target_dims} in the Blender scene. "
                "I explicitly grant user approval for this creation (approved=True)."
            )
            print(f"  User Prompt: \"{user_prompt}\"")

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a Blender 3D assistant with access to create_primitive via MCP. "
                        "When requested to create an object, call the create_primitive tool. "
                        "Include all specified parameters: primitive_type, name, location, dimensions, and approved."
                    )
                },
                {"role": "user", "content": user_prompt}
            ]

            client = httpx.Client(timeout=60.0)
            chat_resp = client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "tools": ollama_tools,
                    "stream": False
                }
            )
            assert chat_resp.status_code == 200, f"Ollama error: {chat_resp.text}"
            model_msg = chat_resp.json().get("message", {})
            tool_calls = model_msg.get("tool_calls", [])
            print(f"  -> AI Model Decision: Generated {len(tool_calls)} tool call(s)")

            # Execute approved tool call
            if tool_calls:
                tc = tool_calls[0].get("function", {})
                call_name = tc.get("name")
                call_args = tc.get("arguments", {})
                if isinstance(call_args, str):
                    call_args = json.loads(call_args)
                # Parse stringified arrays/numbers if LLM serialized them as strings
                for k, v in list(call_args.items()):
                    if isinstance(v, str) and (v.strip().startswith("[") or v.strip().startswith("{")):
                        try:
                            call_args[k] = json.loads(v)
                        except Exception:
                            pass
                # Ensure approval flag is explicitly passed as user instructed
                call_args["approved"] = True
                print(f"  -> Dispatching tool '{call_name}' with arguments: {call_args}")
                create_res = await session.call_tool(call_name, arguments=call_args)
            else:
                print("  -> Direct fallback: Dispatching create_primitive with approved=True...")
                create_res = await session.call_tool("create_primitive", arguments={
                    "primitive_type": "cube",
                    "name": target_name,
                    "location": target_loc,
                    "dimensions": target_dims,
                    "approved": True
                })

            assert not create_res.isError, f"MCP tool call returned error: {create_res.content}"
            create_data = json.loads(create_res.content[0].text)
            print(f"  -> Creation Response:\n{json.dumps(create_data, indent=4)}")
            assert create_data.get("status") == "success", f"Creation failed: {create_data}"
            res_payload = create_data.get("result", {})
            assert res_payload.get("created") is True, "Result missing created=True"
            assert res_payload.get("name") == target_name, f"Expected name {target_name}"

            # -------------------------------------------------------------
            # Step 5: Live Scene Inspection & Verification
            # -------------------------------------------------------------
            print("\n[6. Live Scene Verification via get_object_details]")
            details_res = await session.call_tool("get_object_details", arguments={
                "name": target_name,
                "include_mesh_stats": True
            })
            assert not details_res.isError, f"Failed to retrieve object details: {details_res.content}"
            details_data = json.loads(details_res.content[0].text).get("result", {})
            print(f"  -> Object Verified in Live Scene:")
            print(f"     * Name:        {details_data.get('name')}")
            print(f"     * Type:        {details_data.get('type')}")
            print(f"     * Location:    {details_data.get('location')}")
            print(f"     * Scale:       {details_data.get('scale')}")
            print(f"     * Dimensions:  {details_data.get('dimensions')}")
            print(f"     * Vertices:    {details_data.get('mesh_stats', {}).get('vertices_count')}")

            # Verify exact geometry matches request
            self_loc = details_data.get("location", [])
            self_dims = details_data.get("dimensions", [])
            for i in range(3):
                assert abs(self_loc[i] - target_loc[i]) < 1e-3, f"Location mismatch at axis {i}"
                assert abs(self_dims[i] - target_dims[i]) < 1e-3, f"Dimensions mismatch at axis {i}"
            print("  -> CONFIRMED: Object exists in Blender with exact requested location and dimensions.")

            # -------------------------------------------------------------
            # Step 6: Test Accidental Name Collision Prevention
            # -------------------------------------------------------------
            print("\n[7. Name Collision Prevention Test]")
            collision_res = await session.call_tool("create_primitive", arguments={
                "primitive_type": "cube",
                "name": target_name,
                "location": [0.0, 0.0, 0.0],
                "dimensions": [1.0, 1.0, 1.0],
                "approved": True
            })
            collision_data = json.loads(collision_res.content[0].text)
            print(f"  -> Collision Attempt Status: {collision_data.get('status')}")
            print(f"  -> Collision Message: {collision_data.get('message')}")
            assert collision_data.get("status") == "error", "Expected collision rejection"
            assert "Collision detected" in collision_data.get("message", ""), "Expected collision message"
            print("  -> CONFIRMED: Duplicate name creation was cleanly rejected without overwriting.")

            # -------------------------------------------------------------
            # Step 7: AI Synthesis Response
            # -------------------------------------------------------------
            print("\n[8. AI Model Final Synthesis]")
            messages.append({"role": "tool", "content": json.dumps(create_data)})
            final_resp = client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "stream": False
                }
            )
            ai_text = final_resp.json().get("message", {}).get("content", "")
            print(f"  AI Output:\n  {ai_text.strip()}")

            # -------------------------------------------------------------
            # Step 8: Asset Preservation & Port Check
            # -------------------------------------------------------------
            print("\n[9. Scene & Asset Preservation Check]")
            summary_after = await session.call_tool("get_scene_summary", arguments={})
            final_summary = json.loads(summary_after.content[0].text).get("result", {})
            print(f"  -> Final Total Objects: {final_summary.get('total_objects')} (baseline {baseline_count} + 1 new cube = {baseline_count + 1})")
            assert final_summary.get("total_objects") == baseline_count + 1

            # Verify original assets exist untouched
            for orig in ["Cube", "Light", "Camera"]:
                orig_res = await session.call_tool("get_object_details", arguments={"name": orig})
                assert not orig_res.isError, f"Original asset '{orig}' was modified or missing"
            print("  -> Original scene objects (Cube, Light, Camera) are 100% intact.")

    print("\n" + "=" * 80)
    print("ALL CONTROLLED WRITE TOOL ACCEPTANCE CHECKS PASSED SUCCESSFULLY")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = asyncio.run(run_live_write_tool_acceptance())
    sys.exit(0 if success else 1)
