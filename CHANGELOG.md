# Changelog

## Unreleased
- Scaffold: orgs, users, roles, scoped API tokens, session login with CSRF, append-only audit log and outbox; Docker Compose and CI.
- Catalog: products, feature trees, releases and test plans over the API, with rich text read and written as Markdown.
- Test cases: every edit saves an immutable version; `If-Match` on case edits, optional `Idempotency-Key` on POSTs; plans name cases and resolve to them.
- Consumers: device-code pairing, consumer-scoped tokens, list/get/rename/revoke, heartbeats with derived online/offline status, and per-project inventory upload by hash.
- Test plans: new plans start as `draft` (moves `draft → active → archived`, `archived → active`); archived plans are read-only; add a release's features as entries; reorder entries; feature list shows the last editor.
