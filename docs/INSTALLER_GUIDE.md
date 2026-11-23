# TechBot_Blender_MCP: Windows Installer & Service Guide

> **Author:** Techbot81  
> **Repository:** [bharatnextai/TechBot_Blender_MCP](https://github.com/bharatnextai/TechBot_Blender_MCP)  
> **Target Version:** `1.0.0` (Release Candidate: `v1.0.0-rc2`)  
> **Target Engine:** Blender 5.2.2 LTS (Manifest Minimum: Blender 4.2.0)  

---

## 1. Overview & Architecture

**TechBot_Blender_MCP** bridges AI assistants to Blender through the **Model Context Protocol (MCP)**. The system consists of two primary components operating across a secure local socket:

```
+-----------------------------------------------------------+
|                      AI CLIENTS                           |
|  Claude Desktop / Cursor IDE / Antigravity / ChatGPT      |
+-----------------------------------------------------------+
                             |
                   STDIO JSON-RPC (or Streamable HTTP)
                             v
+-----------------------------------------------------------+
|               EXTERNAL MCP SERVICE (Python 3.10+)          |
|  Location: %LOCALAPPDATA%\TechBot_Blender_MCP\venv        |
|  Entry: python -m mcp_service.app --transport stdio       |
+-----------------------------------------------------------+
                             |
               Local TCP Bridge (127.0.0.1:9877)
                             v
+-----------------------------------------------------------+
|               BLENDER EXTENSION (universal_mcp)           |
|  Target: Blender 5.2.2 LTS / 4.2+ Native Extension        |
|  Engine: bpy.ops.extensions.package_install_files         |
+-----------------------------------------------------------+
```

1. **Blender Native Extension (`universal_mcp`):** Runs inside Blender's embedded Python runtime. Provides the 3D Viewport sidebar UI, scene inspection operators, execution engine, and the bridge socket listener on port `9877`.
2. **External MCP Service (`mcp_service`):** Runs in an isolated external Python 3.10+ virtual environment (`venv`). It communicates with AI clients over STDIO JSON-RPC or Streamable HTTP and forwards tool calls to the Blender bridge over TCP port `9877`.

---

## 2. Prerequisites

| Requirement | Supported Version | Notes |
| :--- | :--- | :--- |
| **Operating System** | Windows 10 / 11 (x64) or macOS (Apple Silicon / Intel) | Windows: PowerShell 5.1+; macOS: Native bash script |
| **Blender** | Blender 5.2.2 LTS (or 4.2+) | Must support native extension system (`bpy.ops.extensions`) |
| **Python** | Python 3.10, 3.11, 3.12, 3.13 | Required for the external MCP service |
| **Package Manager** | `uv` (Recommended) or `pip` | `uv` automatically accelerates venv creation and dependency installs |
| **AI Clients** | Claude Desktop, Cursor IDE, Antigravity IDE, ChatGPT Desktop | ChatGPT Desktop configured via in-app Settings (STDIO) |

> **macOS Users:** A native bash installer is provided for Apple Silicon and Intel Macs. See the [macOS Installation Guide](MACOS_INSTALLATION.md), [macOS Client Configuration](MACOS_CLIENT_CONFIGURATION.md), and [macOS Troubleshooting](MACOS_TROUBLESHOOTING.md).

---

## 3. Quick Start (Interactive Setup Wizard)

To start the interactive multi-client installer:

```powershell
.\Install-TechBot-Blender-MCP.ps1
```

The interactive wizard will guide you through:
1. **Mode Selection:** New install, repair/update, or reconfigure clients.
2. **AI Client Selection:** Select one or multiple clients (Claude, Cursor, ChatGPT, Antigravity).
3. **Deep Detection:** Automatically scans Windows Registry (32/64-bit), Microsoft Store Appx/MSIX packages (`chatgpt-desktop.exe`), Start Menu apps, and standard paths.
4. **Location Confirmation:** Prompts for custom MCP service and download cache directories with default fallbacks.
5. **Automatic Prerequisites:** Auto-installs Python 3.10+ (via winget or python.org), `uv`, and Blender if missing from PATH.
6. **Cryptographic Checksum Verification:** Validates SHA-256 against official sidecars prior to unpacking.
7. **Blender Native Installation:** Headless registration of extension (`--command extension install-file -r user_default -e`) without disrupting active bridge listeners.
8. **Safe Client Merging:** Timestamped backups and non-destructive JSON merges.
9. **Smoke Verification:** Automated STDIO handshake and tool listing test.
10. **Report Generation:** Generates `TechBot-Installation-Report.md`.

For detailed wizard stage descriptions, see [`docs/INTERACTIVE_INSTALLATION.md`](file:///D:/Blender-Ollama-Addon/blender-universal-mcp/docs/INTERACTIVE_INSTALLATION.md).

---

## 4. Parameter Reference (`Install-TechBot-Blender-MCP.ps1`)

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-ReleaseTag` | `string` | `"v1.0.0-rc2"` | GitHub release tag to download assets from. |
| `-GitHubRepo` | `string` | `"bharatnextai/TechBot_Blender_MCP"` | Repository path (`owner/repo`). |
| `-InstallDir` | `string` | `"$env:LOCALAPPDATA\TechBot_Blender_MCP"` | Directory for service & virtual environment. |
| `-DownloadCacheDir` | `string` | `"$InstallDir\downloads"` | Directory for caching downloaded release archives. |
| `-LocalSourceDir` | `string` | `""` | Local repository path (uses local `dist/` artifacts). |
| `-ExtensionZipPath`| `string` | `""` | Explicit path to a local extension ZIP. |
| `-ServiceZipPath`  | `string` | `""` | Explicit path to a local service ZIP. |
| `-InstallMode`     | `string` | `""` | `"new"`, `"repair"`, `"reconfigure"`, or `"exit"`. |
| `-Clients`        | `string[]`| `@()` | Pre-selected clients: `"claude"`, `"cursor"`, `"chatgpt"`, `"antigravity"`. |
| `-CursorScope`    | `string` | `"global"` | `"global"` (`%USERPROFILE%\.cursor`) or `"workspace"`. |
| `-CursorWorkspacePath`| `string` | `""` | Workspace root for Cursor workspace-scoped config. |
| `-AntigravityScope`| `string` | `"global"` | `"global"` (`%USERPROFILE%\.gemini`) or `"workspace"`. |
| `-AntigravityWorkspacePath`| `string` | `""` | Workspace root for Antigravity workspace-scoped config. |
| `-BridgePort`     | `int` | `9877` | Port for the Blender bridge socket listener. |
| `-BridgeTimeout`  | `double`| `15.0` | Socket timeout in seconds. |
| `-BlenderPath`    | `string` | `""` | Explicit path to `blender.exe`. |
| `-PythonPath`     | `string` | `""` | Explicit path to `python.exe` (must be 3.10+). |
| `-ReportPath`     | `string` | `"TechBot-Installation-Report.md"` | Path for the markdown installation report. |
| `-SkipBlender`    | `switch` | `false` | Skip installing the Blender extension. |
| `-SkipService`    | `switch` | `false` | Skip installing the service and venv. |
| `-SkipClients`    | `switch` | `false` | Skip modifying AI client configuration files. |
| `-Force`          | `switch` | `false` | Overwrite existing installations without prompting. |
| `-NonInteractive` | `switch` | `false` | Run in headless unattended mode. |

### Offline / Air-Gapped Installation Examples

If installing from a local cloned repository without internet access:

```powershell
.\Install-TechBot-Blender-MCP.ps1 -LocalSourceDir "D:\Blender-Ollama-Addon\blender-universal-mcp"
```

If supplying pre-downloaded ZIP packages directly:

```powershell
.\Install-TechBot-Blender-MCP.ps1 `
  -ExtensionZipPath "D:\dist\TechBot_Blender_MCP-1.0.0-rc2.zip" `
  -ServiceZipPath "D:\dist\TechBot_Blender_MCP_Service-1.0.0.zip"
```

---

## 5. MCP Service Packaging Specification

| Attribute | Specification |
| :--- | :--- |
| **Archive Name** | `TechBot_Blender_MCP_Service-<version>.zip` (e.g. `TechBot_Blender_MCP_Service-1.0.0.zip`) |
| **Sidecar Name** | `<archive-name>.sha256` (format: `<hash> *<filename>`) |
| **Packaging Tool** | `python scripts/package_mcp_service.py` |

The packaged archive contains the external service runtime (`mcp_service/`), shared schemas (`shared/`), minimal required bridge constants, `pyproject.toml`, and dependencies. Development tests, temporary outputs, cache directories, and Blender files are strictly excluded.

---

## 6. Client Configuration Details

For detailed configuration schemas, scope comparisons, and JSON examples for each supported client, consult:  
[`docs/CLIENT_CONFIGURATION_REFERENCE.md`](file:///D:/Blender-Ollama-Addon/blender-universal-mcp/docs/CLIENT_CONFIGURATION_REFERENCE.md).

---

## 7. Diagnostics & Troubleshooting

For solutions to common issues, socket ping instructions, and backup restorations, consult:  
[`docs/TROUBLESHOOTING.md`](file:///D:/Blender-Ollama-Addon/blender-universal-mcp/docs/TROUBLESHOOTING.md).
