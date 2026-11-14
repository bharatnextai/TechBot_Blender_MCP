# Connect ChatGPT to TechBot_Blender_MCP (Windows)

This guide documents the **local MCP server configuration verified in ChatGPT Settings** for TechBot_Blender_MCP. It uses the MCP server's **STDIO** transport. ChatGPT launches the local process; no public HTTP endpoint or tunnel is needed for this configuration.

> This guide covers the ChatGPT connection only. Install and enable the TechBot_Blender_MCP Blender extension separately before connecting.

## 1. Prerequisites

Before configuring ChatGPT:

- Install Blender and install/enable the TechBot_Blender_MCP extension.
- Open Blender and start the extension's local bridge. The bridge port used by this configuration is `9877`.
- Install `uv` for Windows and know the full path to `uv.exe`.
- Have the TechBot_Blender_MCP project/service directory available locally. The example below uses `D:\\Blender-Ollama-Addon\\blender-universal-mcp`.

The MCP service entry point is `mcp_service.app`.

## 2. Open ChatGPT MCP settings

1. Open ChatGPT.
2. Open **Settings**.
3. Find **MCP server** (search Settings for “MCP” if needed).
4. Choose the option to add a local MCP server. If a server entry already exists for this project, open it to edit.
5. Give the server a recognizable name, such as `TechBot_Blender_MCP`.

The labels and placement of controls can vary between ChatGPT versions. The configuration fields required are **Command to launch**, **Arguments**, **Environment variables**, and **Working directory**.

## 3. Configure the launch command

### Command to launch

Enter the full path to your Windows `uv.exe`.

Example from the verified setup:

```text
C:\\Users\\Administrator\\AppData\\Local\\Microsoft\\WinGet\\Links\\uv.exe
```

This is a machine-specific example. If `uv.exe` is installed elsewhere on your computer, use its actual full path.

### Arguments

Add each item as a separate argument, in this exact order:

| Order | Argument |
|---:|---|
| 1 | `run` |
| 2 | `--no-project` |
| 3 | `--with` |
| 4 | `mcp<2,>=1.25.0` |
| 5 | `--with` |
| 6 | `pydantic>=2.0.0` |
| 7 | `--with` |
| 8 | `httpx>=0.25.0` |
| 9 | `python` |
| 10 | `-m` |
| 11 | `mcp_service.app` |
| 12 | `--transport` |
| 13 | `stdio` |
| 14 | `--bridge-port` |
| 15 | `9877` |
| 16 | `--bridge-timeout` |
| 17 | `15.0` |

Do not paste the whole argument list into one field when the ChatGPT UI provides one input per argument. Add the 17 entries separately and preserve their order.

### Environment variables

Add these three entries:

| Name | Value |
|---|---|
| `PYTHONPATH` | `D:\\Blender-Ollama-Addon\\blender-universal-mcp` |
| `PYTHONUNBUFFERED` | `1` |
| `UMCP_BRIDGE_PORT` | `9877` |

**Important:** Change `PYTHONPATH` to the actual folder containing the `mcp_service` package on your computer. Do not point it to the `blender_addon` subfolder.

### Working directory

Set the working directory to the project/service root:

```text
D:\\Blender-Ollama-Addon\\blender-universal-mcp
```

Use your actual project location if it is different.

## 4. Save and connect

1. Review the command, all 17 arguments, the three environment variables, and the working directory.
2. Click **Save**.
3. If the server entry was already configured, use the available reconnect/reload action or restart ChatGPT if necessary.
4. Keep Blender open with the TechBot_Blender_MCP extension enabled and its bridge running.

## 5. Verify the connection

In ChatGPT's MCP server settings, check that the server connects and exposes its tools. Then try a read-only request such as:

```text
Use TechBot_Blender_MCP to inspect the current Blender scene and report the object names. Do not modify the scene.
```

A successful connection should initialize the MCP server and allow a read-only tool call to reach Blender through the local bridge on port `9877`.

Do not begin with a scene-changing request. Test read-only inspection first.

## 6. Troubleshooting

- **The server does not start:** Confirm that the Command to launch points to an existing `uv.exe` and that the working directory exists.
- **The module cannot be found:** Confirm that `PYTHONPATH` points to the project root containing the `mcp_service` directory.
- **The MCP server connects but Blender is unreachable:** Open Blender, enable the extension, start its bridge, and confirm that the configured bridge port is `9877`.
- **The server reports a dependency error:** Check that `uv` can access the required Python packages and that the package constraints in the Arguments list have not been altered.
- **The configuration was edited but the old status remains:** Save the entry and reconnect/reload the MCP server, or restart ChatGPT.

## 7. Security and safe use

- Keep the Blender bridge bound to local loopback; do not expose port `9877` to the public internet.
- Keep Blender-side human approval enabled for scene mutations.
- Begin with read-only inspection and approve scene-changing operations explicitly in Blender.
- Do not share configuration screenshots or logs if they expose private local paths or other sensitive information.

## Configuration summary

| Setting | Value |
|---|---|
| Transport | STDIO |
| MCP module | `mcp_service.app` |
| Blender bridge port | `9877` |
| Bridge timeout | `15.0` seconds |
| Working directory | Project root containing `mcp_service` |
| Human approval | Keep enabled in Blender |
