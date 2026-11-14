# Architecture

The system has two cooperating components:

1. The external MCP service handles MCP discovery and calls, schema validation, and workflow orchestration.
2. The Blender extension hosts a loopback bridge. Incoming Blender work is placed on the main-thread queue and processed on Blender's main thread, where `bpy` is available.

The extension and service share protocol schemas. The extension package does not install the external MCP service or configure client processes. Read-only inspection and scene mutation have separate contracts; mutation approval and request/token validation remain enforced at the service and bridge boundaries.

See [Security](SECURITY.md) for the authorization boundary and [Development](DEVELOPMENT.md) for focused local checks.
