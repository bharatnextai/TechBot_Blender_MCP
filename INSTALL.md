# Install TechBot_Blender_MCP

This guide is for Blender users installing the add-on. You do **not** need to download the source-code folders, install Python, or use a terminal to install the Blender extension.

## 1. Download the latest release

1. Open the official [TechBot_Blender_MCP Releases page](https://github.com/bharatnextai/TechBot_Blender_MCP/releases/latest).
2. Open the release marked **Latest**.
3. Scroll down to the **Assets** section.
4. Download the file named `TechBot_Blender_MCP-<version>.zip` (for example, `TechBot_Blender_MCP-1.0.0-rc2.zip`).
5. If a `.sha256` checksum file is listed beside the ZIP, download that too if you want to verify the download.

**Important:** Download the ZIP from **Releases → Assets**. Do not use the green **Code → Download ZIP** button on the repository page. That button downloads the source repository, not the ready-to-install Blender extension. Do not extract the release ZIP.

If the Releases page has no ZIP under **Assets**, the installable package has not been attached to that release yet.



## 1A. Windows interactive installer (recommended for MCP clients)

For Windows users who want the MCP service and supported local client configurations set up together, use the repository's interactive PowerShell installer. It is separate from Blender's built-in **Install from Disk** flow above.

### Download the installer

Download these two scripts from the repository:

- [Install-TechBot-Blender-MCP.ps1](https://raw.githubusercontent.com/bharatnextai/TechBot_Blender_MCP/main/Install-TechBot-Blender-MCP.ps1)
- [Uninstall-TechBot-Blender-MCP.ps1](https://raw.githubusercontent.com/bharatnextai/TechBot_Blender_MCP/main/Uninstall-TechBot-Blender-MCP.ps1)

Save them in the same folder. The installer downloads the release packages itself; do not use GitHub's **Code → Download ZIP** archive as an installer package.

### Run the interactive installer

1. Open PowerShell.
2. Change directory to the folder where you saved the installer.
3. Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-TechBot-Blender-MCP.ps1
```

The wizard guides you through installation mode, client selection/detection, install and download locations, package verification, Blender extension deployment, service environment setup, client configuration, and a Markdown installation report.

The default service install directory is:

```text
%LOCALAPPDATA%\TechBot_Blender_MCP
```

You can review the script's parameters with:

```powershell
Get-Help .\Install-TechBot-Blender-MCP.ps1 -Full
```

For unattended use, the script supports `-NonInteractive`, `-InstallMode`, `-Clients`, `-InstallDir`, `-BlenderPath`, `-PythonPath`, and other documented parameters. Use `-SkipBlender`, `-SkipService`, or `-SkipClients` only when you intentionally want to omit that part of setup.

### Client support and ChatGPT note

The installer can configure local MCP client entries for Claude Desktop, Cursor IDE, and Antigravity IDE. ChatGPT Desktop is detected separately, but the script does **not** write a local STDIO configuration for it; its report marks it unconfigured and explains that a remote Streamable HTTP endpoint with a secure HTTPS tunnel is required. See the [ChatGPT connection guide](docs/CHATGPT_INSTALLATION.md) for the documented manual connection details.

The installer backs up existing client configuration files before modifying them. Review the generated installation report and verify that existing unrelated MCP server entries remain present.

### Required release assets

The installer expects a published GitHub Release containing both:
- An installable Blender extension ZIP named `TechBot_Blender_MCP-*.zip` and its SHA-256 sidecar.
- An external service distribution ZIP named `TechBot_Blender_MCP_Service-*.zip` and its SHA-256 sidecar.

It deliberately does not substitute GitHub's automatically generated source-code ZIP for the external service distribution. If the selected release does not contain these assets and checksum files, the installer stops with an error. The default release tag in the script is `v1.0.0-rc2`; use `-ReleaseTag` to select another published release.

### Uninstall

To remove the Blender extension, local service files, and selected local client configuration entries, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Uninstall-TechBot-Blender-MCP.ps1
```

The uninstaller prompts before proceeding. It creates timestamped backups before editing client JSON and preserves unrelated MCP server entries. By default it targets Claude Desktop, Antigravity, and Cursor configurations; ChatGPT is not removed because this installer does not create a local ChatGPT STDIO entry. Use `-SkipBlender` to leave the Blender extension installed, `-KeepLogs` to preserve logs, or `-WorkspacePaths` to include workspace-level client configurations.

## 1B. macOS native installer (Apple Silicon & Intel)

For macOS users on Apple Silicon (M1/M2/M3/M4) or Intel Macs who want the Blender extension, external MCP service, and client configurations set up together without requiring PowerShell, use the native macOS shell installer.

### Download the macOS installer

Download both scripts from the repository:

- [Install-TechBot-Blender-MCP-macOS.sh](https://raw.githubusercontent.com/bharatnextai/TechBot_Blender_MCP/main/Install-TechBot-Blender-MCP-macOS.sh)
- [Uninstall-TechBot-Blender-MCP-macOS.sh](https://raw.githubusercontent.com/bharatnextai/TechBot_Blender_MCP/main/Uninstall-TechBot-Blender-MCP-macOS.sh)

Save them in the same folder and make them executable:

```bash
chmod +x Install-TechBot-Blender-MCP-macOS.sh Uninstall-TechBot-Blender-MCP-macOS.sh
```

### Run the interactive installer

```bash
./Install-TechBot-Blender-MCP-macOS.sh
```

The wizard guides you through:
1. Detecting Apple Silicon / Intel architecture and macOS version.
2. Locating `/Applications/Blender.app`, Python 3.10+, and `uv`.
3. Selecting AI clients (Claude Desktop, Cursor IDE, Antigravity IDE, ChatGPT).
4. Verifying SHA-256 sidecars before installation.
5. Deploying the extension via native CLI: `blender --command extension install-file -r user_default -e <zip>`.
6. Creating an isolated virtual environment at `~/Library/Application Support/TechBot_Blender_MCP/venv`.
7. Non-destructively merging client configurations with timestamped backups.
8. Non-destructive smoke verification (bridge socket check, dependencies, tool count) and generating `TechBot-Installation-Report.md`.

For full details, see the [macOS Installation Guide](docs/MACOS_INSTALLATION.md), [macOS Client Configuration Reference](docs/MACOS_CLIENT_CONFIGURATION.md), and [macOS Troubleshooting Guide](docs/MACOS_TROUBLESHOOTING.md).

### Uninstall on macOS

To remove the Blender extension, virtual environment, and client MCP server entries on macOS:

```bash
./Uninstall-TechBot-Blender-MCP-macOS.sh
```

Use `--keep-logs` to preserve `install.log` and `uninstall.log` while cleaning components.

## 2. Install the ZIP in Blender

1. Start Blender (the tested release target is Blender **5.2.2 LTS**).
2. Open **Edit → Preferences**.
3. Select **Get Extensions**.
4. Open the small dropdown menu in the Extensions area and choose **Install from Disk**.
5. Browse to the ZIP you downloaded and select it. Keep the ZIP compressed; do not extract it.
6. Confirm the installation. If Blender asks you to enable the extension, enable **TechBot_Blender_MCP**.

## 3. Open the extension

1. Return to the **3D Viewport**.
2. Press **N** to open the right-hand sidebar.
3. Open the **Universal MCP** panel/tab.
4. Follow the panel's instructions to start the Blender bridge when you are ready to connect an AI client.

The extension can be installed before you configure an AI client. Installing the Blender extension and connecting an AI client are separate steps.

## Troubleshooting

- **I cannot find the ZIP:** Return to the [latest Releases page](https://github.com/bharatnextai/TechBot_Blender_MCP/releases/latest), expand **Assets**, and look for the versioned `.zip` file. If it is missing, the release maintainer needs to upload it.
- **I only see source-code ZIP files:** Those are GitHub-generated source archives. They are not the installable release asset. Do not use them.
- **Install from Disk is not visible:** Make sure you are in **Edit → Preferences → Get Extensions**, then open the Extensions dropdown menu.
- **The panel is not visible:** Confirm the extension is enabled in Preferences, return to the 3D Viewport, and press **N**.
- **Blender rejects the ZIP:** Check that you downloaded the versioned ZIP under the release's **Assets**, not a source archive, and that the download completed.

## 4. Connect an AI client (optional; separate setup)

The Blender extension is installed in the steps above. To use it with an AI client, you must also run the external MCP service and configure that client. This is an additional setup and may require Python 3.10 or later, `uv`, and editing the AI client's MCP configuration.

See the client-specific setup guides:

- [ChatGPT](docs/CHATGPT_INSTALLATION.md)
- [Antigravity IDE](docs/ANTIGRAVITY_INSTALLATION.md)
- [Claude Desktop](docs/CLAUDE_INSTALLATION.md)
- [Cursor IDE](docs/CURSOR_INSTALLATION.md)
- [macOS Installation & Service Guide](docs/MACOS_INSTALLATION.md)
- [macOS Client Configuration Reference](docs/MACOS_CLIENT_CONFIGURATION.md)
- [macOS Troubleshooting Guide](docs/MACOS_TROUBLESHOOTING.md)

Also review the [Security guide](https://github.com/bharatnextai/TechBot_Blender_MCP/blob/main/docs/publication/SECURITY.md).

Start with read-only inspection tools. Keep approval enforcement enabled for scene mutations unless a trusted human explicitly approves the specific request in Blender. Never treat client-supplied approval flags as authorization.
