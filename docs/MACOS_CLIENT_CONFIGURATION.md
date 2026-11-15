# TechBot_Blender_MCP: macOS Client Configuration Reference

> **Author:** Techbot81  
> **Repository:** [bharatnextai/TechBot_Blender_MCP](https://github.com/bharatnextai/TechBot_Blender_MCP)  
> **Target Version:** `1.0.0` (Release Candidate: `v1.0.0-rc2`)  
> **Target OS:** macOS (Apple Silicon `arm64` & Intel `x86_64`)  

---

## 1. Supported Client Configuration Paths on macOS

| AI Client | Primary Transport | Configuration Path on macOS | Supported Scopes |
| :--- | :---: | :--- | :--- |
| **Claude Desktop** | Local STDIO | `~/Library/Application Support/Claude/claude_desktop_config.json` | Global User Profile |
| **Cursor IDE** | Local STDIO | Global: `~/.cursor/mcp.json`<br>Workspace: `<workspace>/.cursor/mcp.json` | Global & Workspace |
| **Antigravity IDE** | Local STDIO | Global: `~/.gemini/config/mcp_config.json`<br>*(or `~/Library/Application Support/Antigravity/mcp_config.json`)*<br>Workspace: `<workspace>/.agents/mcp_config.json` | Global & Workspace |
| **ChatGPT Desktop** | Streamable HTTP / Tunnel | HTTPS Remote MCP Endpoint (Custom Actions / Tunnel) | Remote HTTPS Endpoint |

---

## 2. Standard STDIO Server Definition (macOS)

When using the isolated Python virtual environment created by `Install-TechBot-Blender-MCP-macOS.sh`, the standard `techbot-blender-mcp` definition inside the client's `mcpServers` object is:

```json
{
  "mcpServers": {
    "techbot-blender-mcp": {
      "command": "/Users/<username>/Library/Application Support/TechBot_Blender_MCP/venv/bin/python",
      "args": [
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
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

> [!NOTE]
> Replace `<username>` with your macOS short username (e.g., `pradeep`, `admin`, etc.). Notice that macOS paths use forward slashes (`/`), unlike Windows paths.

---

### Alternative: Direct `uv` Execution (Development Mode)

If you are developing or running directly from a cloned repository with `uv` on macOS:

```json
{
  "mcpServers": {
    "techbot-blender-mcp": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/<username>/Projects/TechBot_Blender_MCP",
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
        "PYTHONPATH": "/Users/<username>/Projects/TechBot_Blender_MCP",
        "PYTHONUNBUFFERED": "1",
        "UMCP_BRIDGE_PORT": "9877"
      }
    }
  }
}
```

If `uv` was installed via Homebrew on Apple Silicon, you can specify `/opt/homebrew/bin/uv` as the absolute command path; on Intel Macs, `/usr/local/bin/uv`.

---

## 3. Client-Specific Configuration Examples

### 1. Claude Desktop for macOS

- **Configuration File:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Application:** `/Applications/Claude.app`

```json
{
  "mcpServers": {
    "techbot-blender-mcp": {
      "command": "/Users/<username>/Library/Application Support/TechBot_Blender_MCP/venv/bin/python",
      "args": [
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
        "PYTHONUNBUFFERED": "1"
      }
    }
  },
  "preferences": {
    "coworkWebSearchEnabled": true
  }
}
```

**Non-Destructive Merge:** Existing properties such as `preferences`, `coworkUserFilesPath`, and sibling MCP servers are strictly preserved.

---

### 2. Cursor IDE for macOS

- **Global File:** `~/.cursor/mcp.json` (available across all windows)
- **Workspace File:** `<project-root>/.cursor/mcp.json` (applied only to that project)
- **Application:** `/Applications/Cursor.app`

```json
{
  "mcpServers": {
    "techbot-blender-mcp": {
      "command": "/Users/<username>/Library/Application Support/TechBot_Blender_MCP/venv/bin/python",
      "args": [
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
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

---

### 3. Antigravity IDE for macOS

- **Global Configuration:** `~/.gemini/config/mcp_config.json`  
  *(fallback/legacy: `~/Library/Application Support/Antigravity/mcp_config.json`)*
- **Workspace Configuration:** `<workspace-root>/.agents/mcp_config.json`
- **Application:** `/Applications/Antigravity IDE.app` or `/Applications/Antigravity.app`

```json
{
  "mcpServers": {
    "techbot-blender-mcp": {
      "command": "/Users/<username>/Library/Application Support/TechBot_Blender_MCP/venv/bin/python",
      "args": [
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
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

---

### 4. ChatGPT Desktop for macOS

> [!WARNING]
> ChatGPT Desktop for macOS does **not** communicate over local STDIO child processes.

To connect ChatGPT:
1. Start the companion service in **Streamable HTTP** mode:
   ```bash
   "/Users/<username>/Library/Application Support/TechBot_Blender_MCP/venv/bin/python" \
     -m mcp_service.app \
     --transport streamable-http \
     --port 8000 \
     --bridge-port 9877 \
     --auth-token "YOUR_SECURE_TOKEN"
   ```
2. Establish a secure HTTPS tunnel via `cloudflared` or `ngrok`:
   ```bash
   cloudflared tunnel --url http://127.0.0.1:8000
   ```
3. In ChatGPT Desktop or the Custom GPT configuration interface, add the HTTPS tunnel endpoint.

---

## 4. Verification Check

Once configured:
1. Open **Blender 5.2.2 LTS**.
2. Press **N** in the 3D Viewport, navigate to the **Universal MCP** tab, and start the bridge server (listening on `127.0.0.1:9877`).
3. Open your configured AI client and execute a read-only query:
   ```text
   Use techbot-blender-mcp to call get_scene_summary and describe the active scene.
   ```
