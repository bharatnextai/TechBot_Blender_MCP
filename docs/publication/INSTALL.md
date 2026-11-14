# Installation

TechBot_Blender_MCP consists of a Blender extension and a separate external MCP service. Install and configure both components using their respective release instructions.

## Blender extension

1. Obtain the extension ZIP from a published release.
2. Verify the downloaded file against that release's published SHA-256.
3. In Blender, open **Edit → Preferences → Get Extensions → Install from Disk** and select the ZIP.
4. Enable **TechBot_Blender_MCP** in Preferences.
5. In the 3D Viewport sidebar, open the **Universal MCP** panel and start the bridge. Confirm the displayed status before connecting a client.

The release candidate ZIP (`TechBot_Blender_MCP-1.0.0-rc2.zip`) in this project is an evaluation candidate and is not a finalized public release. Do not treat candidate filenames or sidecar checksums as publication or deployment approval.

## External MCP service

Use Python 3.10 or later in a dedicated environment. From the project root, install the project according to its `pyproject.toml` and lock file, then configure the MCP client to launch the service using the transport documented for that client. Do not copy credentials into source files or commit local client configuration.

## Safety

Start with read-only inspection tools. Keep approval enforcement enabled for scene mutations unless a trusted human explicitly approves the specific request in Blender. Never treat client-supplied approval flags as authorization. See [Security](docs/publication/SECURITY.md).
