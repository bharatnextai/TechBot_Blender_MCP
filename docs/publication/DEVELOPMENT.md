# Development

## Requirements

- Python 3.10 or later for the external MCP service and tests.
- Blender 5.2.2 LTS for Blender-specific integration checks.
- Project dependencies and development tools are declared in `pyproject.toml` and `uv.lock`.

## Local checks

From the project root, install development dependencies in an isolated environment, then run targeted tests while changing a capability. A full suite and isolated Blender integration run should be recorded before preparing a release. Do not use production Blender sessions or scenes for mutation tests.

Example focused command:

```text
python -m pytest tests/unit/test_branding_assets.py tests/protocol/test_mcp_discovery_and_invocation.py -q
```

Keep generated scenes, renders, logs, caches, release ZIPs and local configuration out of the source selection.
