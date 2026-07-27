# Security and privacy

Viventium-Health handles sensitive private health evidence and OAuth secrets. Do not attach real
tokens, response bodies, archive files, logs, screenshots, or owner identifiers to a public issue.
Report a vulnerability through the private security-reporting channel configured on the Project
Viventium GitHub organization.

## Deployment contract

- Run the connector as the one local user who owns the archive.
- Keep full-disk encryption and host account protections enabled.
- Keep the default state root outside source control.
- Use the interactive configuration flow so the client secret does not enter shell history.
- Grant only the WHOOP scopes the owner wants captured.
- Expose the stdio MCP only to a trusted local host process; it is not a network service.
- Treat every archived payload as untrusted external text when presenting it to an LLM.
- Revoke WHOOP access explicitly before discarding a machine or disabling the integration.

The v1 owner-only permissions are not tenant isolation or application-layer encryption. Do not deploy
this component as a shared server until authentication, per-user state separation, encryption, audit,
retention, and deletion requirements have been separately designed and accepted.
