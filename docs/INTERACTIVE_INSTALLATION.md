# TechBot_Blender_MCP: Interactive Installation Guide

> **Author:** Techbot81  
> **Repository:** [bharatnextai/TechBot_Blender_MCP](https://github.com/bharatnextai/TechBot_Blender_MCP)  
> **Target Version:** `1.0.0` (Release Candidate: `v1.0.0-rc2`)  
> **Target Engine:** Blender 5.2.2 LTS (Manifest Minimum: Blender 4.2.0)  

---

## 1. Overview

The **TechBot_Blender_MCP Windows Interactive Installer** provides a guided, console-based wizard for deploying the Blender extension, isolating the companion external MCP service in a dedicated virtual environment, and safely configuring one or more AI clients (Claude Desktop, Cursor IDE, Antigravity IDE, and ChatGPT Desktop).

To launch the interactive installer:

```powershell
.\Install-TechBot-Blender-MCP.ps1
```

For unattended or scripted automation, pass `-NonInteractive`:

```powershell
.\Install-TechBot-Blender-MCP.ps1 -NonInteractive -InstallMode new -Clients @("claude", "cursor", "antigravity")
```

---

## 2. Step-by-Step Wizard Stages

```
+---------------------------------------------------------------+
|  Stage A: Welcome & Installation Mode Selection               |
|  (New Install, Repair/Update, Reconfigure Clients, Exit)       |
+---------------------------------------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|  Stage B: AI Client Selection (Multi-select)                  |
|  (Claude, Cursor, ChatGPT, Antigravity IDE)                   |
+---------------------------------------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|  Stage C: Client Detection & Path Resolution                  |
|  (Registry 32/64-bit, Start Menu, PATH, Config locations)     |
+---------------------------------------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|  Stage D: Location Confirmation & Customization               |
|  (Service Directory, Download Cache, Global vs Workspace)     |
+---------------------------------------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|  Stage E: Release Download & SHA-256 Checksum Verification    |
|  (Cryptographic sidecar checks: extension + service ZIPs)     |
+---------------------------------------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|  Stage F: Component Installation                              |
|  (Blender native package_install_files + isolated venv)       |
+---------------------------------------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|  Stage G: Non-Destructive Client JSON Configuration           |
|  (Timestamped backups + safe merge into mcpServers)           |
+---------------------------------------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|  Stage H: Non-Destructive Smoke Verification                  |
|  (STDIO protocol handshake + tool listing + bridge ping)      |
+---------------------------------------------------------------+
                               |
                               v
+---------------------------------------------------------------+
|  Stage I: Installation Report Generation                      |
|  (Outputs TechBot-Installation-Report.md)                     |
+---------------------------------------------------------------+
```

---

### Stage A — Welcome and Installation Mode

The wizard detects whether TechBot is already present in the target environment:

- **New Installation:** Clean setup of the Blender extension, external Python virtual environment, dependencies, and selected AI clients.
- **Repair / Update Existing Installation:** Refreshes extension files, updates package dependencies in `%LOCALAPPDATA%\TechBot_Blender_MCP\venv`, preserves existing configuration, and creates a backup of the previous environment (`venv.bak_<timestamp>`).
- **Reconfigure AI Clients Only:** Leaves the Blender extension and external service untouched. Connects newly selected AI clients to the existing local bridge.
- **Exit:** Aborts execution without modifying the filesystem.

---

### Stage B & C — Client Selection and Deep Detection

The detection engine performs non-destructive system discovery across:

1. **Windows Uninstall Registry:** Inspects 64-bit (`HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall`), 32-bit WoW64 (`HKLM:\Software\WOW6432Node\...`), and user registry (`HKCU:\Software\...`) to obtain application display names, version numbers, and installation directories.
2. **Start Menu Shortcuts:** Scans user and system Start Menu program groups (`.lnk` targets).
3. **Standard Installation Directories:** Checks `%LOCALAPPDATA%\Programs`, `%ProgramFiles%`, and user profiles.
4. **Environment PATH:** Resolves registered command names (`Claude.exe`, `cursor.exe`, `antigravity.exe`, `ChatGPT.exe`).
5. **Configuration Discovery:** Locates existing MCP configuration profiles (e.g. `%APPDATA%\Claude\claude_desktop_config.json`, `%LOCALAPPDATA%\Claude-Data\*\claude_desktop_config.json`, `%USERPROFILE%\.cursor\mcp.json`, `%USERPROFILE%\.gemini\config\mcp_config.json`).

#### Detection Table Example

```text
=== AI Client Detection Summary ===
  [1] Claude Desktop:  INSTALLED (v0.8.1)
      Executable:  C:\Users\Administrator\AppData\Local\Programs\Claude\Claude.exe
      MCP Config:  C:\Users\Administrator\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\claude_desktop_config.json
  [2] Cursor IDE:      NOT DETECTED
      MCP Config:  C:\Users\Administrator\.cursor\mcp.json
  [3] ChatGPT Desktop: NOT DETECTED
      MCP Config:  Requires HTTPS / Secure MCP Tunnel (Manual/Custom Action)
  [4] Antigravity IDE: INSTALLED (v2.7.0)
      Executable:  C:\Users\Administrator\AppData\Local\Programs\Antigravity IDE\Antigravity IDE.exe
      MCP Config:  C:\Users\Administrator\.gemini\config\mcp_config.json
```

Users may input comma-separated numbers (e.g. `1,4`), `all`, or `none`.

#### Candidate Resolution & Manual Overrides
- **Multiple Candidates:** If multiple installations of an application or multiple configuration profiles are found, the wizard lists the candidates and prompts the user to select the active one.
- **Manual Path Overrides:** If an application was installed in a portable or custom folder, the user can supply the exact executable path manually.

---

### Stage D — Download & Installation Locations

Users can confirm or customize paths:
1. **MCP Service Installation Directory:** Default is `%LOCALAPPDATA%\TechBot_Blender_MCP`.
2. **Release Download & Cache Directory:** Default is `%LOCALAPPDATA%\TechBot_Blender_MCP\downloads`.
3. **Cursor Configuration Scope:**
   - Global User Profile (`%USERPROFILE%\.cursor\mcp.json`)
   - Specific Workspace (`<workspace>\.cursor\mcp.json`)
4. **Antigravity Configuration Scope:**
   - Global User Config (`%USERPROFILE%\.gemini\config\mcp_config.json`)
   - Specific Workspace (`<workspace>\.agents\mcp_config.json`)

A comprehensive **Pre-Installation Summary** is presented before any disk operations begin.

---

### Stage E — Integrity & Cryptographic Checksum Verification

The installer downloads or resolves:
- `TechBot_Blender_MCP-1.0.0-rc2.zip` (Blender Extension)
- `TechBot_Blender_MCP-1.0.0-rc2.zip.sha256`
- `TechBot_Blender_MCP_Service-1.0.0.zip` (MCP Service Package)
- `TechBot_Blender_MCP_Service-1.0.0.zip.sha256`

The SHA-256 digest of each archive is computed and matched against its official sidecar. If a hash mismatch is detected, execution halts immediately with a security failure to protect the system.

---

### Stage F — Component Deployment

1. **Blender Extension:**  
   Headlessly installed via Blender's official native operator:  
   `bpy.ops.extensions.package_install_files(filepath=..., enable_on_install=True, overwrite=True)`.  
   Persisted into Blender user preferences (`bpy.ops.wm.save_userpref()`).
2. **External MCP Service:**  
   Extracted into `%LOCALAPPDATA%\TechBot_Blender_MCP\service`.  
   Isolated virtual environment created at `%LOCALAPPDATA%\TechBot_Blender_MCP\venv` using `uv` (or `python -m venv` fallback).  
   Dependencies installed in editable mode (`pip install -e`).
3. **Port 9877 Bridge Preservation:**  
   The installer actively detects if Blender's background bridge server is already listening on port `9877`. Existing bridge listener processes are never killed or restarted.

---

### Stage G — AI Client Configuration Merging

The installer performs non-destructive JSON merges:
- Creates a timestamped backup before touching the file (`<file>.bak_yyyyMMdd_HHmmss`).
- Injects `"techbot-blender-mcp"` into `"mcpServers"`.
- Strictly preserves all sibling servers (e.g. `sqlite`, `filesystem`, `ollama`), top-level preferences, and Cowork configurations.
- Validates the resulting JSON using Python and PowerShell before committing.

---

### Stage H — Smoke Verification

The installer runs non-destructive checks:
1. Python dependencies import test (`mcp`, `pydantic`, `httpx`, `starlette`, `uvicorn`, `mcp_service`).
2. Live MCP STDIO protocol handshake (`{"method": "initialize"}`).
3. Live MCP tool listing (`{"method": "tools/list"}`), confirming typed tools are discoverable.
4. Bridge socket accessibility check (`127.0.0.1:9877`).

No GPU workloads or scene mutations are triggered.

---

### Stage I — Final Installation Report

Generates `TechBot-Installation-Report.md` in the current working directory and copies it to the service installation folder.

---

## 3. Uninstallation & Removal

To cleanly remove the components:

```powershell
# Interactive uninstaller
.\Uninstall-TechBot-Blender-MCP.ps1

# Non-interactive removal preserving debug logs
.\Uninstall-TechBot-Blender-MCP.ps1 -Force -KeepLogs
```
