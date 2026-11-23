# Changelog

## Unreleased
- MCP `tools/call` on a tool the caller can't use now says why: 403 `Needs scope <scope>`, or 403 naming its toolset and `?toolsets=`; only a name that isn't a tool is 404 `Unknown tool`.
- Quick start works on Windows: `requirements.lock` is now made by `scripts/lock.py` (uv, universal, with platform markers, checked in CI), and `create-admin` and `sweep-idempotency` apply migrations first.
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
- Automated runs: cycles in `automated` or `both` mode send automated cases to chosen online consumers as jobs; consumers long-poll, claim and report; jobs can be cancelled or reassigned, and a stalled job is requeued once, then its cases cancel. New MCP tools `jobs_list`, `jobs_cancel` and `jobs_reassign` (`execution` toolset; the default toolsets now list 24 tools).
- MCP page stats: each `/mcp` call adds to an hourly `mcp_tool_stat` row (calls, errors, response sizes); `mcp_tools_list`, `mcp_usage` and `mcp_server_get` give per-tool definition and response cost in ≈ tokens, usage by hour or day, and the server version and tool-list hash (scope `admin` or `audit:read`). An `admin` token can now also read the audit log.
- Reports (org, product, release readiness, feature), case search by text and tag, and all-or-nothing CSV import/export of cases with a `version` column. Their 8 operations are MCP tools (90 in all; the default toolsets now list 27).
- Tests run on Test Junkie (`test-junkie==0.9a8`), not pytest, locally and in CI: one suite per file, on SQLite and, with `TJ_TCMS_TEST_POSTGRES_URL` set, Postgres.
- Case import takes an optional `mapping` from your CSV's column names to ours, and `format: "md-bundle"` exports and re-imports cases as a zip of Markdown files, one per case; over MCP a zip arrives as `{content_type, base64}`.
