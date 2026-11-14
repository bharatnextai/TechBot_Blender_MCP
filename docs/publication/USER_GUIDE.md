# User Guide

## Start a session

1. Install and enable the Blender extension from a verified published release.
2. Start the bridge from Blender's Universal MCP sidebar and confirm its status.
3. Start the external MCP service using the selected client's documented configuration.
4. Confirm the client discovers the expected read-only tools before requesting changes.

## Make scene changes

Use inspection results to identify the target and validate the requested state. When approval is required, review the exact request in Blender and make a human decision there. Confirm the resulting task status and inspect Blender state independently; a successful tool response alone is not proof that the requested result exists.

## Troubleshooting

If the bridge is unavailable, check the Blender panel status and the service's connection error. If an approval request expires, is denied, or cannot be found, submit no automatic substitute approval. Query its documented status and follow the task's fail-closed result.
