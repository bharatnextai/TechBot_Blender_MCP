# Security

## Authorization

Tool arguments are validated against typed schemas. When scene-mutation approval is enabled, a mutation must be associated with a human decision recorded by Blender and a valid request-bound credential. Credentials are checked for request/parameter binding, expiry and single use. Caller-supplied `approved=True` or similar flags are not proof of human approval.

## Blender execution

Blender API work must run on Blender's main thread through the extension queue. The local bridge is intended for loopback communication. Do not expose it on a public interface or place authentication material in source, logs, screenshots or client configuration committed to the repository.

## Test policy

Local test-only policy is isolated to disposable fixtures and does not represent human approval or change production defaults. See the source tests and policy review records for the exact test scopes. Do not enable test policy in a production Blender session.

Report suspected vulnerabilities through a maintainer-controlled private channel; do not include credentials in issue reports.
