# Connect ChatGPT Desktop to TechBot_Blender_MCP

This guide documents the **local STDIO MCP server configuration** for ChatGPT Desktop / OpenAI Codex.

ChatGPT Desktop runs local MCP servers over standard STDIO pipes via its configuration file at:
- **Windows:** `%USERPROFILE%\.codex\config.toml` (e.g. `C:\Users\<YourUsername>\.codex\config.toml`)
- **macOS:** `~/.codex/config.toml`

> **Automatic Configuration:** The interactive installers (`Install-TechBot-Blender-MCP.ps1` on Windows and `Install-TechBot-Blender-MCP-macOS.sh` on macOS) configure this automatically! You only need to follow manual configuration below if you are setting up without the installer.

---

## Method 1: Automatic Setup via Interactive Installer (Recommended)

1. Run the interactive installer:
   - **Windows:** `powershell.exe -ExecutionPolicy Bypass -File .\Install-TechBot-Blender-MCP.ps1`
   - **macOS:** `./Install-TechBot-Blender-MCP-macOS.sh`
2. When prompted to select AI clients, select **ChatGPT Desktop**.
3. The installer automatically detects your environment, creates the isolated Python venv, and non-destructively merges the `[mcp_servers.techbot-blender-mcp]` block into your `.codex\config.toml` while preserving all other settings and MCP servers.
4. Open ChatGPT Desktop and verify under **Settings → MCP Servers**.

---

## Method 2: Direct Configuration via `config.toml`

Open your `config.toml` file (create it if it does not exist):
- **Windows:** `notepad "%USERPROFILE%\.codex\config.toml"`
- **macOS:** `nano ~/.codex/config.toml`

Add the following section:

### Windows:
```toml
[mcp_servers.techbot-blender-mcp]
enabled = true
command = 'C:\Users\<YourUsername>\AppData\Local\TechBot_Blender_MCP\venv\Scripts\python.exe'
args = ["-m", "mcp_service.app", "--transport", "stdio", "--bridge-port", "9877", "--bridge-timeout", "15.0"]
cwd = 'C:\Users\<YourUsername>\AppData\Local\TechBot_Blender_MCP\service'

[mcp_servers.techbot-blender-mcp.env]
PYTHONPATH = 'C:\Users\<YourUsername>\AppData\Local\TechBot_Blender_MCP\service'
PYTHONUNBUFFERED = "1"
UMCP_BRIDGE_PORT = "9877"
```

### macOS:
```toml
[mcp_servers.techbot-blender-mcp]
enabled = true
command = '/Users/<YourUsername>/Library/Application Support/TechBot_Blender_MCP/venv/bin/python'
args = ["-m", "mcp_service.app", "--transport", "stdio", "--bridge-port", "9877", "--bridge-timeout", "15.0"]
cwd = '/Users/<YourUsername>/Library/Application Support/TechBot_Blender_MCP/service'

[mcp_servers.techbot-blender-mcp.env]
PYTHONPATH = '/Users/<YourUsername>/Library/Application Support/TechBot_Blender_MCP/service'
PYTHONUNBUFFERED = "1"
UMCP_BRIDGE_PORT = "9877"
```

---

## Method 3: Manual In-App Settings (GUI)

If you prefer to configure manually within ChatGPT Desktop:

1. Open ChatGPT.
2. Open **Settings**.
3. Find **MCP server** (search Settings for “MCP” if needed).
4. Choose the option to add a local MCP server. If a server entry already exists for this project, open it to edit.
5. Give the server a recognizable name, such as `TechBot_Blender_MCP`.

The labels and placement of controls can vary between ChatGPT versions. The configuration fields required are **Command to launch**, **Arguments**, **Environment variables**, and **Working directory**.

## 3. Configure the launch command

### Command to launch

Enter the command `uv` if it is available in your Windows PATH. Otherwise, enter the full path to your actual `uv.exe` installation.

Example of a machine-specific path:

```text
C:\\Users\\YourWindowsUser\\AppData\\Local\\Microsoft\\WinGet\\Links\\uv.exe
```

Replace `YourWindowsUser` with your Windows account folder name, and adjust the path if `uv.exe` is installed elsewhere. You can check whether Windows can find `uv` by running `where.exe uv` in Command Prompt.

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

Add these three entries. For `PYTHONPATH`, enter the actual extracted project root from Step 1.

| Name | Value |
|---|---|
| `PYTHONPATH` | `D:\\Downloads\\TechBot_Blender_MCP-main` |
| `PYTHONUNBUFFERED` | `1` |
| `UMCP_BRIDGE_PORT` | `9877` |

**Important:** The `PYTHONPATH` example above is only an example. Replace it with the full path to your own extracted `TechBot_Blender_MCP-main` folder (or whatever the extracted folder is named). That folder must directly contain `mcp_service`. Do not point `PYTHONPATH` to the `mcp_service` or `blender_addon` subfolder.

### Working directory

Set the working directory to the **same extracted project root** used for `PYTHONPATH`.

Example:

```text
D:\\Downloads\\TechBot_Blender_MCP-main
```

Replace this example with your actual extracted folder path. The `PYTHONPATH` and **Working directory** values should point to the same project root.

## 4. Save and connect

1. Review the command, all 17 arguments, the three environment variables, and the working directory.
2. Confirm that `PYTHONPATH` and **Working directory** both point to the extracted project root containing `mcp_service`.
3. Click **Save**.
4. If the server entry was already configured, use the available reconnect/reload action or restart ChatGPT if necessary.
5. Keep Blender open with the TechBot_Blender_MCP extension enabled and its bridge running.

## 5. Verify the connection

In ChatGPT's MCP server settings, check that the server connects and exposes its tools. Then try a read-only request such as:

```text
Use TechBot_Blender_MCP to inspect the current Blender scene and report the object names. Do not modify the scene.
```

A successful connection should initialize the MCP server and allow a read-only tool call to reach Blender through the local bridge on port `9877`.

Do not begin with a scene-changing request. Test read-only inspection first.

## 6. Troubleshooting

- **The server does not start:** Confirm that the Command to launch resolves to an existing `uv.exe` and that the working directory exists.
- **The module cannot be found:** Confirm that `PYTHONPATH` points to the extracted project root and that the `mcp_service` directory exists directly inside it.
- **The server starts but cannot find the project:** Check that **Working directory** is set to the same extracted project root as `PYTHONPATH`.
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
| `PYTHONPATH` | Extracted project root containing `mcp_service` |
| Working directory | Same extracted project root |
| Human approval | Keep enabled in Blender |
