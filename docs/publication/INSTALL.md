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

Also review the [Security guide](https://github.com/bharatnextai/TechBot_Blender_MCP/blob/main/docs/publication/SECURITY.md).

Start with read-only inspection tools. Keep approval enforcement enabled for scene mutations unless a trusted human explicitly approves the specific request in Blender. Never treat client-supplied approval flags as authorization.
