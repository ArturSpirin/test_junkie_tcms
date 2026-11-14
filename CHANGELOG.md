# Changelog

## Unreleased
- Scaffold: orgs, users, roles, scoped API tokens, session login with CSRF, append-only audit log and outbox; Docker Compose and CI.
- Catalog: products, feature trees, releases and test plans over the API, with rich text read and written as Markdown.
- Test cases: every edit saves an immutable version; `If-Match` on case edits, optional `Idempotency-Key` on POSTs; plans name cases and resolve to them.
- `sweep-idempotency` command deletes expired `Idempotency-Key` records in batches; a reused expired key is claimed atomically.
