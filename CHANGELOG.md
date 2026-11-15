# Changelog

## Unreleased
- Scaffold: orgs, users, roles, scoped API tokens, session login with CSRF, append-only audit log and outbox; Docker Compose and CI.
- Catalog: products, feature trees, releases and test plans over the API, with rich text read and written as Markdown.
- Test cases: every edit saves an immutable version; `If-Match` on case edits, optional `Idempotency-Key` on POSTs; plans name cases and resolve to them.
- Consumers: device-code pairing, consumer-scoped tokens, list/get/rename/revoke, heartbeats with derived online/offline status, and per-project inventory upload by hash.
- Member invites (7-day, single-use token shown once and stored hashed); audit log filters by `via`, `action` and `until`.
- Test plans: new plans start as `draft` (moves `draft → active → archived`, `archived → active`); archived plans are read-only; add a release's features as entries; reorder entries; feature list shows the last editor.
- Invitees with no account sign up on accept (`token`, `name`, `password`): user, membership and session in one transaction.
- `sweep-idempotency` command deletes expired `Idempotency-Key` records in batches; a reused expired key is claimed atomically.
- Execution: cycles pinned to the case version they run, bulk cycles by release in one batch, append-only results with per-step status, and attachments (raw or base64 upload, org-scoped content-addressed storage).
- MCP server at `/mcp` (and `test-junkie-tcms mcp` stdio bridge): tools generated from `@operation` routes, plugin routes included, default toolsets `core,cases,execution` (21 tools, setting `mcp_default_toolsets`), drift-guard test. New pins `mcp==2.3.0` and `httpx2==2.16.0`: `mcp` requires `httpx2`, which only the MCP dispatcher imports; the API and its tests keep `httpx`.
- MCP page stats: each `/mcp` call adds to an hourly `mcp_tool_stat` row (calls, errors, response sizes); `mcp_tools_list`, `mcp_usage` and `mcp_server_get` give per-tool definition and response cost in ≈ tokens, usage by hour or day, and the server version and tool-list hash (scope `admin` or `audit:read`). An `admin` token can now also read the audit log.
