# TechBot_Blender_MCP: Native macOS Installation Guide

> **Author:** Techbot81  
> **Repository:** [bharatnextai/TechBot_Blender_MCP](https://github.com/bharatnextai/TechBot_Blender_MCP)  
> **Target Version:** `1.0.0` (Release Candidate: `v1.0.0-rc2`)  
> **Target Engine:** Blender 5.2.2 LTS (Manifest Minimum: Blender 4.2.0)  
> **Architectures:** Apple Silicon (`arm64`: M1/M2/M3/M4) & Intel Core (`x86_64`)  

---

> [!IMPORTANT]
> **Compatibility Notice:** This native macOS installer matches the proven Windows multi-client setup workflow. Per safety policies, full live integration certification requires execution and verification on a physical macOS system. Always run initial verification with read-only inspection tools before requesting scene modifications.

---

## 1. System Requirements & Prerequisites

Before running the installer, ensure the following components are available on your Mac:

1. **macOS Version:** macOS 12 Monterey, macOS 13 Ventura, macOS 14 Sonoma, or macOS 15 Sequoia (Apple Silicon or Intel).
2. **Blender:** **Blender 5.2.2 LTS** (or 4.2.0+) installed in `/Applications/Blender.app`.
3. **Python Runtime:** **Python 3.10 or later**. macOS does not ship with a standalone Python 3.10+ interpreter by default. You can install Python via:
   - **Homebrew (Recommended):** `brew install python@3.12`
   - **Python.org Installer:** Download the macOS 64-bit universal2 installer.
   - **pyenv:** `pyenv install 3.11.9 && pyenv global 3.11.9`
4. **Package Manager (Optional):** [`uv`](https://github.com/astral-sh/uv) provides rapid dependency resolution:
   ```bash
   brew install uv
   # or: curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
5. **AI Client(s):** One or more supported MCP-compatible AI clients:
   - Claude Desktop for macOS
   - Cursor IDE for macOS
   - Antigravity IDE for macOS
   - ChatGPT Desktop for macOS (Requires remote HTTPS tunnel)

---

## 2. Interactive Installation Wizard

The script `Install-TechBot-Blender-MCP-macOS.sh` provides an interactive console wizard matching the Windows installer.

### Step 1: Download the installer scripts

Download both scripts from GitHub:

```bash
curl -fsSL -O https://raw.githubusercontent.com/bharatnextai/TechBot_Blender_MCP/main/Install-TechBot-Blender-MCP-macOS.sh
curl -fsSL -O https://raw.githubusercontent.com/bharatnextai/TechBot_Blender_MCP/main/Uninstall-TechBot-Blender-MCP-macOS.sh
chmod +x Install-TechBot-Blender-MCP-macOS.sh Uninstall-TechBot-Blender-MCP-macOS.sh
```

### Step 2: Run the installer

Launch the interactive wizard:

```bash
./Install-TechBot-Blender-MCP-macOS.sh
```

### Installation Stages Walkthrough

1. **Architecture & Preflight Detection:**
   The script inspects your Mac architecture (`arm64` Apple Silicon or `x86_64` Intel), locates `/Applications/Blender.app`, verifies Python 3.10+, and discovers `uv`.
2. **Stage A — Mode Selection:**
   - `[1] New Installation`: Deploys extension, service virtual environment, and client configurations.
   - `[2] Repair / Update`: Updates existing deployment while preserving user settings.
   - `[3] Reconfigure AI Clients only`: Re-links client MCP configurations to an existing bridge.
   - `[4] Exit`: Aborts without making changes.
3. **Stage B & C — AI Client Selection & Detection:**
   Scans for installed apps in `/Applications` and standard configuration paths. You can toggle Claude Desktop, Cursor IDE, Antigravity IDE, or ChatGPT.
4. **Stage D — Locations & Scope Confirmation:**
   - Default service directory: `~/Library/Application Support/TechBot_Blender_MCP`
   - Download cache: `~/Library/Application Support/TechBot_Blender_MCP/downloads`
   - Allows choosing **Global User Profile** vs **Project Workspace Scope** for Cursor and Antigravity.
5. **Stage E — Cryptographic Verification:**
   Downloads `TechBot_Blender_MCP-1.0.0-rc2.zip` and `TechBot_Blender_MCP_Service-1.0.0.zip` with their `.sha256` sidecars from GitHub Releases. Checks SHA-256 hashes before unzipping.
6. **Stage F — Extension Deployment & Service Setup:**
   - Installs the extension via Blender's native CLI:
     ```bash
     /Applications/Blender.app/Contents/MacOS/Blender --command extension install-file -r user_default -e "<ZIP_PATH>"
     ```
   - Creates an isolated Python virtual environment at:
     `~/Library/Application Support/TechBot_Blender_MCP/venv`
   - Installs the 32 pinned service dependencies into the isolated environment.
7. **Stage G — Safe Non-Destructive JSON Merging:**
   Creates a timestamped `.bak_<timestamp>` backup of each client configuration file. Merges the `techbot-blender-mcp` entry into `mcpServers` without altering other servers or preferences.
8. **Stage H — Non-Destructive Verification Checks:**
   - Passively checks if port `9877` has an active Blender bridge listener (never interrupts or restarts it).
   - Validates Python imports (`mcp`, `pydantic`, `httpx`).
   - Executes an MCP STDIO handshake and counts discovered typed tools (~171 tools).
9. **Stage I — Markdown Report:**
   Generates `TechBot-Installation-Report.md` summarizing the installation.

---

## 3. Unattended / Automated CLI Installation

For headless setups, CI environments, or script automation:

```bash
./Install-TechBot-Blender-MCP-macOS.sh \
  --non-interactive \
  --install-mode new \
  --clients claude,cursor,antigravity \
  --blender-path "/Applications/Blender.app" \
  --install-dir "${HOME}/Library/Application Support/TechBot_Blender_MCP"
```

### Supported Parameters

| Flag | Description | Default |
| :--- | :--- | :--- |
| `--release-tag <tag>` | GitHub release tag to download | `v1.0.0-rc2` |
| `--repo <owner/repo>` | GitHub repository | `bharatnextai/TechBot_Blender_MCP` |
| `--install-dir <path>` | Directory for MCP service & venv | `~/Library/Application Support/TechBot_Blender_MCP` |
| `--download-cache-dir <path>` | Directory for downloaded archives | `<install-dir>/downloads` |
| `--local-source-dir <path>` | Local folder containing `dist/` archives | *None (downloads from GitHub)* |
| `--extension-zip <path>` | Explicit local Blender extension ZIP | *None* |
| `--service-zip <path>` | Explicit local MCP service ZIP | *None* |
| `--install-mode <mode>` | `new`, `repair`, `reconfigure`, `exit` | Interactive prompt |
| `--clients <list>` | Comma-separated: `claude,cursor,antigravity,chatgpt` | Auto-detect |
| `--cursor-scope <scope>` | `global` or `workspace` | `global` |
| `--cursor-workspace <path>` | Workspace root if scope is `workspace` | *Current Directory* |
| `--antigravity-scope <scope>` | `global` or `workspace` | `global` |
| `--antigravity-workspace <path>` | Workspace root if scope is `workspace` | *Current Directory* |
| `--bridge-port <port>` | Blender bridge socket port | `9877` |
| `--bridge-timeout <sec>` | Socket communication timeout in seconds | `15.0` |
| `--blender-path <path>` | Explicit path to `Blender.app` or binary | Auto-detected |
| `--python-path <path>` | Explicit path to Python 3.10+ interpreter | Auto-detected |
| `--report-path <path>` | Output path for markdown installation report | `TechBot-Installation-Report.md` |
| `--skip-blender` | Skip Blender extension installation | `false` |
| `--skip-service` | Skip Python MCP service environment creation | `false` |
| `--skip-clients` | Skip modifying AI client configuration JSON files | `false` |
| `--force` | Force overwrite / reinstall without prompts | `false` |
| `--non-interactive` | Run non-interactively using defaults | `false` |

---

## 4. Uninstallation

To cleanly remove TechBot Blender MCP:

```bash
./Uninstall-TechBot-Blender-MCP-macOS.sh
```

### Uninstaller Operations

1. **Removes the Blender extension** natively:
   ```bash
   blender --command extension remove universal_mcp
   ```
2. **Cleans AI client configurations**: Removes `techbot-blender-mcp` from Claude Desktop, Cursor IDE, and Antigravity IDE configuration files while preserving all other servers and settings.
3. **Creates configuration backups**: Saves timestamped `.bak_uninstall_<timestamp>` files in each config folder.
4. **Removes application files**: Purges `~/Library/Application Support/TechBot_Blender_MCP` (`venv`, `service`, `downloads`).
5. **Preserves logs with `--keep-logs`**:
   ```bash
   ./Uninstall-TechBot-Blender-MCP-macOS.sh --keep-logs
   ```
