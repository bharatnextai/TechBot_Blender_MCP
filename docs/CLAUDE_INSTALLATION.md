# Connect Claude Desktop to TechBot_Blender_MCP (Windows)


This guide configures Claude Desktop to launch the TechBot_Blender_MCP MCP service locally using **STDIO**. The service connects to the Blender extension's local bridge on port `9877`.

> This guide covers the MCP client connection. Install and enable the TechBot_Blender_MCP Blender extension separately, then start its bridge in Blender.

## 1. Prerequisites

- Blender with the TechBot_Blender_MCP extension installed and enabled.
- The Blender bridge started and listening on port `9877`.
- Windows with Python 3.10 or later.
- `uv` installed and available in PATH, or the full path to `uv.exe`.
- The TechBot_Blender_MCP source repository downloaded and extracted.

### Download the MCP service source

1. Open the [TechBot_Blender_MCP repository](https://github.com/bharatnextai/TechBot_Blender_MCP).
2. Select **Code → Download ZIP**.
3. Extract the ZIP to a folder of your choice.
4. The extracted folder will typically be named `TechBot_Blender_MCP-main`.
5. Confirm that this folder directly contains `mcp_service`, `blender_addon`, and `shared`.

Example project root:

```text
D:\\Downloads\\TechBot_Blender_MCP-main
```

Use your actual extracted folder path. Do not point the configuration at the `mcp_service` subfolder.

**There are two different ZIP packages:** the repository's **Code → Download ZIP** archive contains source code for the MCP service. The installable Blender extension is a separate ZIP under **Releases → Assets**. Do not install the source archive as the Blender extension.

## 2. Configure the MCP server

The following configuration launches the local service through `uv`. Replace both example paths with the actual locations on your computer:

- `C:\\Users\\YourWindowsUser\\AppData\\Local\\Microsoft\\WinGet\\Links\\uv.exe` — example only; use `uv` if it is available in PATH, or your actual `uv.exe` path.
- `D:\\Downloads\\TechBot_Blender_MCP-main` — replace with your extracted project root.

The `--directory` argument makes the extracted project root the service working directory. The `PYTHONPATH` variable points to the same root so Python can import `mcp_service` and the companion Blender package.

Use this server entry inside the client's existing `mcpServers` object:

```json
{
  "techbot-blender-mcp": {
    "command": "C:\\Users\\YourWindowsUser\\AppData\\Local\\Microsoft\\WinGet\\Links\\uv.exe",
    "args": [
      "run",
      "--directory",
      "D:\\Downloads\\TechBot_Blender_MCP-main",
      "--no-project",
      "--with",
      "mcp<2,>=1.25.0",
      "--with",
      "pydantic>=2.0.0",
      "--with",
      "httpx>=0.25.0",
      "python",
      "-m",
      "mcp_service.app",
      "--transport",
      "stdio",
      "--bridge-port",
      "9877",
      "--bridge-timeout",
      "15.0"
    ],
    "env": {
      "PYTHONPATH": "D:\\Downloads\\TechBot_Blender_MCP-main",
      "PYTHONUNBUFFERED": "1",
      "UMCP_BRIDGE_PORT": "9877"
    }
  }
}
```

If `uv` is available in PATH, you may use `"command": "uv"` instead of the full executable path. In JSON, Windows backslashes must be doubled as shown.

**Do not replace the complete configuration file blindly.** If it already contains other MCP servers or settings, add only the `techbot-blender-mcp` entry inside the existing `mcpServers` object and preserve the other entries.

## 3. Add it in Claude Desktop

1. Open the Claude Desktop configuration file. On Windows, the usual location is:

```text
%APPDATA%\\Claude\\claude_desktop_config.json
```

2. If the file does not exist, create it and add the top-level `mcpServers` object.
3. Add the `techbot-blender-mcp` entry from Step 2 inside `mcpServers`.
4. If the file already contains other MCP servers, preserve them. Do not replace the whole file with the example.
5. Save the file and completely quit and relaunch Claude Desktop.
6. Open Claude's MCP / connectors area and confirm that the server is available.

This guide is for **Claude Desktop**. Claude Code uses a separate MCP management workflow; do not paste this Desktop JSON into Claude Code settings.

Official references: [Anthropic MCP documentation](https://docs.anthropic.com/en/docs/mcp) and [MCP local server configuration example](https://modelcontextprotocol.io/docs/develop/connect-local-servers).

## 4. Verify the connection

1. Confirm `techbot-blender-mcp` is shown as connected/running and its tools are listed.
2. Keep Blender open with the extension enabled and the bridge listening on port `9877`.
3. Start with this read-only request:

```text
Use techbot-blender-mcp to inspect the current Blender scene. Call the read-only get_scene_summary tool and report the scene name, frame, active object, active camera, and object names. Do not modify the scene.
```

### Verified client result

**Claude Desktop — verified (November 2026):** the MCP server appeared in Desktop's Extensions view with status **Running**. A live read-only `get_scene_summary` request returned the default Blender scene: `Scene`, frame 1 (range 1–250 at 24 fps), Metric units, one collection (`Collection`), active object `Cube`, active camera `Camera`, and three objects (`Cube`, `Camera`, `Light`). No scene changes were made.

This records a successful read-only integration check; it does not certify scene-mutating workflows.

## 5. Troubleshooting

- **The MCP server does not start:** Confirm that the command points to an existing `uv.exe`, or that `uv` is available in PATH.
- **The module cannot be found:** Confirm that `--directory` and `PYTHONPATH` both point to the extracted project root containing `mcp_service`.
- **The client reports invalid JSON:** Validate the file's JSON syntax and ensure Windows path backslashes are doubled.
- **The service starts but Blender is unreachable:** Start the Blender extension bridge and confirm port `9877`.
- **The server is not listed after editing:** Save the file and use the client's refresh/reload action or restart the client.

## 6. Security

- Keep the Blender bridge bound to local loopback. Do not expose port `9877` to the public internet.
- Keep Blender-side human approval enabled for scene mutations.
- Test read-only inspection before requesting any scene changes.
- Do not enable unattended or auto-approval behavior for scene mutations.

## Configuration summary

| Setting | Value |
|---|---|
| Transport | STDIO |
| MCP server key | `techbot-blender-mcp` |
| MCP module | `mcp_service.app` |
| Bridge port | `9877` |
| Bridge timeout | `15.0` seconds |
| Project path | Extracted project root containing `mcp_service` |
| Approval | Keep Blender-side human approval enabled |
