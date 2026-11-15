# TechBot_Blender_MCP: macOS Troubleshooting Guide

> **Author:** Techbot81  
> **Repository:** [bharatnextai/TechBot_Blender_MCP](https://github.com/bharatnextai/TechBot_Blender_MCP)  
> **Target Version:** `1.0.0` (Release Candidate: `v1.0.0-rc2`)  
> **Target OS:** macOS (Apple Silicon & Intel)  

---

## 1. macOS Gatekeeper & Quarantine Attributes

When downloading ZIP archives or script files directly via a browser on macOS, macOS may attach the `com.apple.quarantine` extended attribute, preventing execution or blocking the archive extraction.

### Diagnosis
```bash
xattr -l Install-TechBot-Blender-MCP-macOS.sh
# Output shows: com.apple.quarantine
```

### Resolution
Strip the quarantine attribute before running the installer:
```bash
xattr -d com.apple.quarantine Install-TechBot-Blender-MCP-macOS.sh Uninstall-TechBot-Blender-MCP-macOS.sh
chmod +x Install-TechBot-Blender-MCP-macOS.sh Uninstall-TechBot-Blender-MCP-macOS.sh
```

---

## 2. Architecture Mismatch (Apple Silicon vs Rosetta 2)

TechBot Blender MCP runs natively on Apple Silicon (`arm64`) and Intel (`x86_64`). If you run an x86_64 Python interpreter inside an arm64 Blender environment, native binary extensions or socket calls may fail.

### Diagnosis
Check your Python architecture:
```bash
python3 -c "import platform; print(platform.machine())"
```
Check your Blender architecture:
```bash
file /Applications/Blender.app/Contents/MacOS/Blender
# Expected on Apple Silicon: Mach-O 64-bit executable arm64
```

### Resolution
Ensure your Python runtime matches your Blender build:
- On Apple Silicon (M1/M2/M3/M4), use the native Homebrew Python:
  ```bash
  brew install python@3.12
  ```
- If your terminal is running under Rosetta, open Terminal without Rosetta (**Get Info → Uncheck "Open using Rosetta"**).

---

## 3. Blender.app Path Not Found

If Blender is installed in a non-standard location or named differently (e.g., `/Applications/Blender 5.2.app` or `~/Applications/Blender.app`), the auto-detector may not locate it.

### Diagnosis
```bash
./Install-TechBot-Blender-MCP-macOS.sh
# [WARN] Blender executable not found in standard /Applications paths.
```

### Resolution
Pass the explicit path to `Blender.app` or the internal binary:
```bash
./Install-TechBot-Blender-MCP-macOS.sh --blender-path "/Applications/Blender 5.2.app"
```

---

## 4. Extension Installation Failure via CLI

If `blender --command extension install-file` reports an error:

### Diagnosis
Run the command directly to inspect the detailed Blender traceback:
```bash
/Applications/Blender.app/Contents/MacOS/Blender --command extension repo-list
/Applications/Blender.app/Contents/MacOS/Blender --command extension install-file -r user_default -e "/path/to/TechBot_Blender_MCP-1.0.0-rc2.zip"
```

### Common Causes & Fixes
- **Incomplete or Corrupt ZIP:** Verify the SHA-256 sidecar hash against `TechBot_Blender_MCP-1.0.0-rc2.zip.sha256`.
- **Permissions Issue:** Ensure your user account owns `~/Library/Application Support/Blender`:
  ```bash
  sudo chown -R $(whoami) "${HOME}/Library/Application Support/Blender"
  ```
- **Manual GUI Installation Fallback:**
  1. Open Blender 5.2.2 LTS.
  2. Navigate to **Edit → Preferences → Get Extensions**.
  3. Click the dropdown menu in the upper-right corner and select **Install from Disk...**.
  4. Select `TechBot_Blender_MCP-1.0.0-rc2.zip`.
  5. Enable **TechBot_Blender_MCP**.
  6. Re-run the installer with `--skip-blender`:
     ```bash
     ./Install-TechBot-Blender-MCP-macOS.sh --skip-blender
     ```

---

## 5. Port 9877 Bridge Connection Issues

The external MCP service connects to Blender across loopback TCP port `9877`.

### Diagnosis
Check if port 9877 is listening:
```bash
lsof -nP -iTCP:9877 -sTCP:LISTEN
```
Or test via Python:
```bash
python3 -c "import socket; s = socket.socket(); print('OPEN' if s.connect_ex(('127.0.0.1', 9877)) == 0 else 'CLOSED')"
```

### Common Causes & Fixes
- **Bridge Not Started:** In Blender, press `N` in the 3D Viewport, select the **Universal MCP** tab, and verify that the bridge server is active.
- **Port Conflict:** If another process is listening on port 9877, pass a different port to the installer:
  ```bash
  ./Install-TechBot-Blender-MCP-macOS.sh --bridge-port 9878
  ```
  And adjust the port setting in the Blender sidebar panel.
- **Loopback Binding:** Ensure the bridge is bound to `127.0.0.1` and not blocked by local macOS firewall software (e.g., LuLu, Little Snitch).

---

## 6. Client Configuration File Issues

### Claude Desktop
- Standard path: `~/Library/Application Support/Claude/claude_desktop_config.json`
- If Claude was installed via Homebrew or a portable wrapper, verify the path:
  ```bash
  ls -la "${HOME}/Library/Application Support/Claude/claude_desktop_config.json"
  ```
- Check that the file contains valid JSON:
  ```bash
  python3 -m json.tool "${HOME}/Library/Application Support/Claude/claude_desktop_config.json" > /dev/null
  ```

### Antigravity IDE
- Standard documented path: `~/.gemini/config/mcp_config.json`
- If you use the workspace-level configuration, ensure the file is at:
  `<workspace-root>/.agents/mcp_config.json`
- Restart Antigravity or execute **Developer: Reload Window** from the Command Palette to reload MCP server registrations.

---

## 7. Rebuilding the Isolated Virtual Environment

If dependencies become corrupted or Python was upgraded to a new minor version:

```bash
# Rebuild the virtual environment cleanly:
./Install-TechBot-Blender-MCP-macOS.sh --install-mode repair --force
```
Or manually purge and recreate:
```bash
rm -rf "${HOME}/Library/Application Support/TechBot_Blender_MCP/venv"
./Install-TechBot-Blender-MCP-macOS.sh --install-mode new
```
