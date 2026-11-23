# App API contract

What the TCMS web app (`src/test_junkie_tcms/web/`) calls, view by view. The source of truth for every
payload is `/api/v1/openapi.json`; this doc says which operations each view uses, the shapes that matter, and
what the API does not serve yet. Rows marked **not yet (Fn)** are planned follow-ups: the app does not show
those items until they exist. Rows marked **out of scope (v1, owner decision)** are not built in v1, and the
app does not show them.

| Key | Follow-up |
|---|---|
| F1 | List totals, case counts, cases filters, sort, key search, case position within a feature |
| F2 | Actor directory, case version provenance, cycles of a case, member last active, agent enable, audit filters |
| F3 | Case Description field, per-case Markdown, plan entry resolution counts |
| F4 | Cycle and run extras: created/closed by, bulk naming, splits, retries, stop, step ignore, build under test |
| F5 | Report periods, trend, org KPIs, product-wide and feature-history reports |
| F6 | MCP tool descriptions and hints, recent calls, error-code breakdown |
| F7 | Consumer jobs per machine, rejected reason, pause, deny pairing, pending-pairing preview, roster |
| F8 | Name search (`q`) on lists, product owner, copy feature tree, ETA and manual case order on Start |

## Serving

- `web/` is served as static files at `/assets/` (`/assets/app.css`, `/assets/js/...`, `/assets/fonts/...`).
  `index.html` must use root-absolute refs, because the shell is also served at deep paths.
- `GET`/`HEAD` on `/`, `/app`, `/app/` and `/app/{path}` return `index.html` with `Cache-Control: no-cache`
  (History-API fallback). These routes are not in OpenAPI and are not MCP tools.
- Any other unknown path returns a problem+json 404. The fallback never shadows `/api`, `/mcp`, `/healthz`,
  `/docs`, `/redoc` or `/openapi.json`.
- Same origin, no build step, no dev proxy.

## Common rules

### Auth

- `POST /api/v1/auth/login` sets `tj_session` (HttpOnly) and `tj_csrf` (readable by the page).
- Every write (`POST`, `PUT`, `PATCH`, `DELETE`) sends the `tj_csrf` value as `X-CSRF-Token`.
- `GET /api/v1/me` says who is signed in and their orgs and roles. `POST /api/v1/auth/logout` ends the session.
- Consumer endpoints (`/api/v1/consumers/me/...`) use a consumer token, not the session; the app never calls them.

### Errors

All errors are `application/problem+json`:

```json
{"type": "about:blank", "title": "Not Found", "status": 404, "detail": "..."}
```

| Status | When | Extra fields |
|---|---|---|
| 401 | no or expired session | |
| 403 | role too low, or CSRF header missing or wrong | |
| 404 | unknown entity, or not in your org | |
| 409 | stale `If-Match` | `current_version`, and an `ETag` header |
| 409 | unique or foreign-key conflict | `detail: "Conflicts with existing data"` |
| 413 | upload too large | |
| 422 | validation | `errors: [{"loc": [...], "msg": "..."}]` |
| 428 | `If-Match` missing on a versioned write | |

The mock's `type` URIs, `request_id` and `pointer` are not part of the API; the app reads `title`, `detail`
and `errors[].loc`.

### Versioned writes

Case and other versioned updates send `If-Match: <version>`. On 409 the app shows the conflict and offers to
reload from `current_version`.

### Paging

List endpoints that page take `cursor` and `limit` (1-200, default 50) and return
`{"items": [...], "next_cursor": "..." | null, "total": n}`. Pass `next_cursor` back as `cursor` for the next
page. `total` counts the rows the list matches with its filters, across all pages ("12 of 64").

A sort on a value that changes (`cases_list?sort=result` or `sort=updated`) pages by keyset, so a case whose
result or update time changes between two page loads can be skipped or shown twice. Reload from page one to fix.

All paths below are under `/api/v1/orgs/{org}` unless they start with `/api/v1/`.

### Search

Two kinds of search, and the app never filters a paged list itself (that misses rows past page one):

- **Case text:** `GET /orgs/{org}/search` (`search`) `?q&tag&product&feature&include_archived`, paged. It
  matches the current version's title, preconditions and steps, and needs `q` or `tag` (else 422). The Cases
  list's own `q` (`cases_list?q=`) matches the case key (`PAY-12`) or number, and the current title, steps and
  tag names.
- **Names on other lists** (products, features, plans, members, consumers): a server-side `q` on each list,
  **not yet (F8)**. Until then those views show no search box.

## Views

### 0. Sign-in and invite accept

| Need | Operations | Status |
|---|---|---|
| sign in | `POST /api/v1/auth/login` (`auth_login`) `{email, password}` returns `MeOut` and sets the cookies | exists |
| sign out | `POST /api/v1/auth/logout` (`auth_logout`), 204 | exists |
| who is signed in | `GET /api/v1/me` (`me_get`) | exists |
| accept an invite | `POST /api/v1/invites:accept` (`invites_accept`) | exists |

Accept takes `{token}` when signed in, or `{token, name, password}` (password 8+ characters) to sign up; signup
also starts a session and sets the cookies. It returns the new `MemberOut`.

| Call | Status | When |
|---|---|---|
| login | 401 `Wrong email or password` | unknown email, wrong password or inactive user (one message for all three) |
| login | 422 | email or password missing or too long |
| logout | 400 | called with an API token, not a session |
| accept | 404 `Invite not found` | unknown token |
| accept | 410 `Invite expired` | past `expires_at` |
| accept | 410 `Invite already used` | already accepted, including a concurrent accept |
| accept | 410 `Invite revoked` | revoked by an admin |
| accept | 409 | signup for an email that already has an account: sign in, then accept |
| accept | 403 | signed in as another email, or called with an API token |
| accept | 422 | `name` without `password` or the other way round, or password under 8 characters |

### 1. Products

| Need | Operations | Status |
|---|---|---|
| list, create, edit, archive | `products_list`, `products_create`, `products_update`, `products_archive` | exists |
| current version, latest results | `releases_list`, `reports_product` | exists |
| card counts (features, cases) | `products_list`, `products_get`: `feature_count`, `case_count` (live features, live cases in them) | exists |
| name search | | not yet (F8) |
| owner, "copy feature tree from" | | not yet (F8) |

### 2. Versions (releases)

| Need | Operations | Status |
|---|---|---|
| list, new, detail KPIs, mark released | `releases_list`, `releases_create`, `releases_get`, `releases_update`, `reports_release` | exists |
| set features | `PUT /releases/{id}/features` (`releases_set_features`) | exists |
| plans and cycles of a version | `plans_list`, `cycles_list`, filtered on `release_id` in the app | exists |
| feature case counts | `features_list`: `case_count`, `total_case_count` per node | exists |

### 3. Tree

| Need | Operations | Status |
|---|---|---|
| tree, cases per feature | `features_list`, `cases_list?feature=` | exists |
| search case text | `search?q&feature` (see Search) | exists |
| feature name search | | not yet (F8) |
| new, rename, describe, move, archive a feature | `features_create`, `features_update`, `features_move`, `features_archive` | exists |
| move a case | `cases_move` | exists |
| reports, import, viewer | `reports_feature`, `imports_create`, `cases_get` | exists |
| case count per feature, last-result dot, filters, sort, key search | `features_list` (`case_count` own, `total_case_count` with sub-features); `cases_list` (`last_result`, `last_result_at`; filters, `sort`, `q` as in Cases below) | exists |
| reorder a case within a feature | `CaseOut.position`; `cases_move` `{feature_id, position?}` (no `position` appends; reordering keeps the other cases' `updated_at`) | exists |
| "edited by agent via MCP on behalf of", "in cycles" | | not yet (F2) |

### 4. Cases

| Need | Operations | Status |
|---|---|---|
| table, paging, feature/status/automation filters | `cases_list` | exists |
| title search | `cases_list?q=` | exists |
| text search (title, preconditions, steps, tags) | `search?q&tag&product` (see Search) | exists |
| result and priority filters, sort, total, key search | `cases_list?result&priority&updated_since&edited_by&edited_by_kind&has_ref&sort&q`, `total` on the page | exists |

`result` takes a last result (`fail`, `success`, ...) or `untested`, which means no result in any cycle (the
mock's hint says "in an open cycle"; the app copy follows the API). `has_ref` reads the case's
`automation_ref`. `edited_by` is an actor id, `edited_by_kind` is `user` or `agent`. `sort` is `manual` (the
tree's pre-order, then position), `key`, `title`, `updated` (newest first), `result` (failures first) or
`priority` (critical first). Per-tag case counts for the tag filter come from `tags_list` (`case_count`).
| "No feature yet" option | | not in the API (a case always has a feature) |

### 5. Case editor

| Need | Operations | Status |
|---|---|---|
| read, edit fields and steps, reorder steps, change note | `cases_get`, `cases_update` (with `If-Match`) | exists |
| new case | `cases_create` | exists |
| tags | `tags_list` | exists |
| separate Description field, Markdown get/put | | not yet (F3) |
| version provenance (via, on behalf of), "in cycles" | | not yet (F2) |

### 6. Version history

| Need | Operations | Status |
|---|---|---|
| list, compare (two gets), restore | `cases_versions_list`, `cases_version_get`, `cases_restore` | exists |
| via / on-behalf-of per version, "used in cycles" | | not yet (F2) |

### 7. Plans

| Need | Operations | Status |
|---|---|---|
| list, new, detail, edit | `plans_list`, `plans_create`, `plans_get`, `plans_update` | exists |
| status | `draft`, `active`, `archived` on reads and writes | exists (enum on reads added by this contract) |
| add entries | `POST /plans/{id}/entries` (`plans_add_entries`) | exists |
| remove an entry | `DELETE /plans/{id}/entries/{entry_id}` (`plans_remove_entry`) | exists |
| reorder entries | `PUT /plans/{id}/entries/order` (`plans_reorder_entries`) | exists |
| preview what a plan resolves to | `plans_resolve` | exists |
| filter by version and status | in the app, from `plans_list` | exists |
| name search | | not yet (F8) |
| cycle from plan | `cycles_create` with `plan_id` (the plan must be `active`) | exists |
| per-entry resolution counts | | not yet (F3) |

Add entries, 1 to 500 per call; each entry has exactly one of the four keys:

```json
{"entries": [{"case_id": "..."}, {"feature_id": "..."}, {"query": "..."}, {"release_id": "..."}]}
```

Reorder sends every entry id of the plan, in the new order: `{"entry_ids": ["...", "..."]}`.

`PlanEntryOut`: `{id, case_id, feature_id, query, position}`. The mock's single `PUT /entries` is these three
operations.

### 8. Cycles

| Need | Operations | Status |
|---|---|---|
| list, status filter, new, detail, edit | `cycles_list`, `cycles_create`, `cycles_get`, `cycles_update` | exists |
| add cases, assign, refresh pinned version | `cycle_cases_list`, `cycle_cases_add`, `cycle_cases_assign`, `cycle_cases_refresh_version` | exists |
| close, reopen | `cycles_close`, `cycles_reopen` | exists |
| bulk create, batch | `cycles_bulk_create`, `cycle_batches_get` | exists |
| cycle and batch `created_by`/`closed_by` (a batch closes when its last cycle does) | `cycles_get`, `cycle_batches_get` | exists (F4) |
| per-feature counts (`GET /cycles/{id}/features`) | `cycle_feature_counts` | exists (F4) |
| `name_pattern` (`{release}`, `{env}`, and `{feature}` or `{plan}`; else 422 `bad_name_pattern`), per-cycle `assignees`, `skip_drafts` | `cycles_bulk_create` | exists (F4) |
| released release refuses new cycles (409 `release_closed`) | `cycles_create`, `cycles_bulk_create` | exists (F4) |

### 9. Start a cycle

| Need | Operations | Status |
|---|---|---|
| pick plan or features, preview | `plans_list`, `features_list`, `cycles_preview` | exists |
| mode, environment, tester, machines | `cycles_create`, `members_list`, `consumers_list` | exists |
| `split` (`even` default, `by_feature`, `first_free`), `retries` 0-2 (counts `Result.attempt`), `queue_when_offline` (a revoked machine still 409) | `cycles_create` | exists (F4) |
| cycle-level stop: cancels queued jobs, running jobs finish, no retries after (second stop 409 `cycle_stopped`) | `cycles_stop` | exists (F4) |
| ETA, manual case order | | not yet (F8) |
| "notify the tester" | | out of scope (v1, owner decision) |

### 10. Run

| Need | Operations | Status |
|---|---|---|
| queue, pinned steps | `cycle_cases_list` | exists |
| record results, attempts | `results_create`, `results_list`, `results_bulk_create` | exists |
| evidence | `attachments_upload` (413 when too large), `attachments_download` | exists |
| automated jobs | `jobs_list`, `jobs_cancel`, `jobs_reassign` | exists |
| step statuses `ignore` and `cancel`; `skip_reason` (`defect`, `env`, `data`, `dep`, `na_env`, `flag`, `other`; only on a skip, `other` needs a comment); `build` (120 chars, blank is null) | `results_create`, `results_bulk_create`, `jobs_report` | exists (F4) |
| builds under test for the product, newest first, at most 20 | `cycle_builds` | exists (F4) |
| result undo | | not yet (follow-up) |

### 11. Reports

| Need | Operations | Status |
|---|---|---|
| release, feature, cycle, product, org reports | `reports_release`, `reports_feature`, `reports_cycle`, `reports_product`, `reports_org` | exists |
| period filters, trend, org KPIs, product-wide report, feature history in the mock's shape | | not yet (F5) |

### 12. Members

| Need | Operations | Status |
|---|---|---|
| list, add, change role, remove | `members_list`, `members_add`, `members_update`, `members_remove` | exists |
| invites: list, create, revoke | `invites_list`, `invites_create`, `invites_revoke` | exists |
| copy the invite link | `InviteCreated.token` from `invites_create`, shown once; the link carries it to the accept view | exists |
| resend an invite | revoke, then create (a new token) | exists |
| name search | | not yet (F8) |
| last active | | not yet (F2) |
| invite emails | | out of scope (v1, owner decision) |

### 13. Tokens and agents

| Need | Operations | Status |
|---|---|---|
| tokens: list, create, revoke | `tokens_list`, `tokens_create`, `tokens_revoke` | exists |
| agents: list, create, edit, disable | `agents_list`, `agents_create`, `agents_update`, `agents_disable` | exists |
| agent enable, description, name rule | | not yet (F2) |

### 14. Audit

| Need | Operations | Status |
|---|---|---|
| rows, diff, actor/action/via/entity/date filters, one case's history | `audit_list` | exists |
| actor kind filter, `q`, request id and tool on rows, retention | | not yet (F2) |

Action names are singular (`product.create`), not the mock's `products.create`.

### 15. MCP

All five need the audit-read permission (admins).

| Need | Operations | Status |
|---|---|---|
| server name, version, tool count | `GET /mcp/server` (`mcp_server_get`) | exists |
| tools table, per-tool calls and errors for the chosen range | `GET /mcp/tools` (`mcp_tools_list`) | exists; range added |
| usage chart: reads, writes, errors per hour or day | `GET /mcp/usage` (`mcp_usage`) | exists; reads/writes added |
| clients KPI (count and names) | `GET /mcp/clients` (`mcp_clients`) | added |
| updates feed | `GET /mcp/updates` (`mcp_updates`) | added |
| live usage | poll, see below | added |
| tool description, hints, recent calls, error codes, "last call" in live mode | | not yet (F6) |
| drift-guard CI results in the feed | | out of scope (v1, owner decision) |

**Range.** `mcp_tools_list`, `mcp_usage` and `mcp_clients` take `since` and `until` (ISO 8601). `since` is
floored and `until` ceiled to the bucket. `since >= until`, or a span over 90 days, is a 422.

`mcp_server_get`:

```json
{"name": "...", "version": "...", "tool_count": 92, "tool_list_hash": "..."}
```

`mcp_tools_list?since&until` (default: the last 30 days):

```json
{"since": "...", "until": "...", "total_def_tokens": 0,
 "items": [{"name": "...", "toolset": "...", "scope": "...", "read_only": true, "def_tokens": 0,
            "calls_7d": 0, "errors_7d": 0, "calls_30d": 0, "errors_30d": 0,
            "calls": 0, "errors": 0, "p50_resp_tokens": 0, "p95_resp_tokens": 0}]}
```

`calls` and `errors` cover the chosen range; `calls_7d`/`calls_30d` are fixed windows.

`mcp_usage?since&until&bucket=hour|day&tool&actor`:

```json
{"bucket": "hour", "since": "...", "until": "...",
 "items": [{"start": "...", "calls": 0, "reads": 0, "writes": 0, "errors": 0,
            "resp_bytes": 0, "p50": 0, "p95": 0}]}
```

Only buckets with calls are returned; the app fills the gaps with zeros. `reads + writes = calls`. A tool counts
as a read when it is a `GET`; a tool that is no longer in the running tool list counts as a write.

`mcp_clients?since&until` (default: the last 24 hours), most calls first:

```json
{"since": "...", "until": "...",
 "items": [{"actor_id": "...", "name": "...", "kind": "user", "calls": 0, "errors": 0, "last_hour": 0}]}
```

`kind` is `user` or `agent`.

`mcp_updates` (paged, newest first):

```json
{"items": [{"id": "...", "at": "...", "kind": "tools_changed", "version": "...", "tool_list_hash": "...",
            "added": ["..."], "removed": ["..."], "changed": ["..."]}],
 "next_cursor": null}
```

`kind` is `server_started` or `tools_changed`. The feed is server-wide: every org sees the same rows, which
hold only tool names and versions. Each server start writes one row: `tools_changed` when the tool
list hash differs from the newest row, else `server_started`. With several worker processes, each start writes
its own row, so one deploy can show several `server_started` rows; only the first worker after a change writes
`tools_changed`.

**Live.** The app polls `mcp_usage?bucket=hour` and `mcp_clients` every 15 seconds while live mode is on.
There is no server push (no SSE, no `notifications/tools/list_changed`).

### 16. Consumers (machines)

| Need | Operations | Status |
|---|---|---|
| cards, status filter, product filter | `consumers_list?status&product` | exists |
| name search | | not yet (F8) |
| card "N projects" | `ConsumerOut.project_count` | added |
| detail, heartbeat last 24 h, inventory | `consumers_get` | exists |
| rename, set products | `PATCH /consumers/{id}` `{name?, product_ids?}` | exists |
| revoke | `DELETE /consumers/{id}` | exists |
| pair | `POST /pair/approve` (`pairings_approve`) | exists |
| jobs per machine, rejected reason, pause, deny pairing, pending-pairing preview, roster | | not yet (F7) |

`ConsumerOut`:

```json
{"id": "...", "name": "...", "status": "online", "product_ids": ["..."], "project_count": 2,
 "last_heartbeat_at": "...", "busy_job_id": null, "tj_version": "...", "python": "...", "os": "...",
 "revoked_at": null, "created_at": "..."}
```

`status` is `online`, `offline`, `busy` or `revoked`. `project_count` is the number of inventoried projects.

`ConsumerDetail` adds `heartbeats: [{at, busy_job_id}]` (last 24 hours, newest first) and
`inventory: [{project, hash, test_count, updated_at}]`.

For reference, the machine side (consumer token, not the app):

- `POST /api/v1/consumers/me/heartbeat` `{inventory_hashes, busy_job_id, tj_version, python, os}` returns
  `{inventory_wanted, cancel_job_ids}`. The server derives busy from its own jobs; `busy_job_id` is ignored.
- `PUT /api/v1/consumers/me/inventory/{project}` `{hash, roster}` returns `{changed, test_count}`.
