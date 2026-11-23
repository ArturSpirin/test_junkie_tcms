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
| F6 | MCP tool descriptions and hints, recent calls, error-code breakdown (done) |
| F7 | Consumer jobs per machine, rejected reason, pause, deny pairing, pending-pairing preview, roster (done) |
| F8 | Name search (`q`) on lists, product owner, copy feature tree, ETA and manual case order on Start (done) |

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
  matches the current version's title, description, preconditions and steps, and needs `q` or `tag` (else 422). The
  Cases list's own `q` (`cases_list?q=`) matches the case key (`PAY-12`) or number, and the current title, steps and
  tag names.
- **Names on other lists** (products, features, plans, members, consumers): `q` on each list, a
  case-insensitive part of the name (members: the name or email), at most 200 characters. It filters before
  paging, so it holds on every cursor page and `total` counts the matches; `%` and `_` match only themselves,
  and a blank `q` is no filter. `features_list?q=` returns each match with its parents, so the tree still nests.

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
| name search | `products_list?q=` (see Search) | exists (F8) |
| owner | `owner_actor_id` on `products_create`, `products_update` (null clears) and reads; an active user member's actor, else 422 `owner_not_member` | exists (F8) |
| "copy feature tree from" | `products_create` `copy_features_from` (id or key): copies the live tree with new ids; a product in another org is 404 | exists (F8) |

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
| feature name search | `features_list?q=` (matches with their parents, see Search) | exists (F8) |
| new, rename, describe, move, archive a feature | `features_create`, `features_update`, `features_move`, `features_archive` | exists |
| move a case | `cases_move` | exists |
| reports, import, viewer | `reports_feature`, `imports_create`, `cases_get` | exists |
| case count per feature, last-result dot, filters, sort, key search | `features_list` (`case_count` own, `total_case_count` with sub-features); `cases_list` (`last_result`, `last_result_at`; filters, `sort`, `q` as in Cases below) | exists |
| reorder a case within a feature | `CaseOut.position`; `cases_move` `{feature_id, position?}` (no `position` appends; reordering keeps the other cases' `updated_at`) | exists |
| "edited by agent via MCP on behalf of", "in cycles" | `cases_versions_list` (`via`, `token_id`, `on_behalf_of_user_id`), `actors_list`, `cases_cycles` | exists (F2) |

### 4. Cases

| Need | Operations | Status |
|---|---|---|
| table, paging, feature/status/automation filters | `cases_list` | exists |
| title search | `cases_list?q=` | exists |
| text search (title, description, preconditions, steps, tags) | `search?q&tag&product` (see Search) | exists |
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
| separate Description field | `description` on `cases_get`, `cases_create`, `cases_update`; versioned and restored with the other fields | exists (F3) |
| Markdown get/put | `GET`/`PUT /cases/{case}/markdown` (`cases_markdown_get`, `cases_markdown_put`): one md-bundle file; `ETag` is the version, `PUT` takes `If-Match`. A file without a Description section keeps the stored one | exists (F3) |
| version provenance (via, on behalf of), "in cycles" | `cases_get` / `cases_version_get` (`via`, `token_id`, `on_behalf_of_user_id`), `cases_cycles` | exists (F2) |

### 6. Version history

| Need | Operations | Status |
|---|---|---|
| list, compare (two gets), restore | `cases_versions_list`, `cases_version_get`, `cases_restore` | exists |
| via / on-behalf-of per version, "used in cycles" | `cases_versions_list`, `cases_cycles` | exists (F2) |

Each version carries `via` (`ui`, `api`, `mcp`; null on versions saved before F2), `token_id` and
`on_behalf_of_user_id` (the agent's owner, set only when an agent saved it). Names come from `actors_list`.

`GET /cases/{case}/cycles` (`cases_cycles`, read) lists the cycles the case is in, newest first:
`CaseCycleOut {cycle_id, name, cycle_status, environment, started_at, closed_at, cycle_case_id, case_version,
status, last_result_at}`, where `case_version` is the version the cycle pinned. A case in a product the caller
can't see is a 404.

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
| name search | `plans_list?q=` (see Search) | exists (F8) |
| cycle from plan | `cycles_create` with `plan_id` (the plan must be `active`) | exists |
| per-entry resolution counts | each entry on `plans_list`/`plans_get` has `cases` (live cases it selects) and `new_cases` (those no earlier entry did; they sum to the `plans_resolve` total) | exists (F3) |

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
| batch "created by", closed by, per-feature counts, name pattern and per-cycle assignee, skip drafts, released release refuses cycles | | not yet (F4) |

### 9. Start a cycle

| Need | Operations | Status |
|---|---|---|
| pick plan or features, preview | `plans_list`, `features_list`, `cycles_preview` | exists |
| mode, environment, tester, machines | `cycles_create`, `members_list`, `consumers_list` | exists |
| split strategy, retries, queue when offline, cycle-level stop | | not yet (F4) |
| ETA | `cycles_create`, `cycles_update` `eta` (null clears), read on `CycleOut.eta`; an `eta` sent in the past is 422 `eta_in_past` (an update that doesn't send `eta` still works after it passes) | exists (F8) |
| run order, manual case order | `cycles_create` `order` (`source`, the default, `feature` or `priority`) and `case_order` (case keys or ids run first, in that order; the rest follow `order`). `CycleOut.order` reads back the strategy, `manual` when `case_order` was given; a request can't send `order: "manual"` (422). A `case_order` case the run doesn't have (unknown, archived or deprecated) is 422 `case_not_in_run`. `cycle_cases_list?sort=position` lists the run order. Not on `cycles_bulk_create` | exists (F8) |
| "notify the tester" | | out of scope (v1, owner decision) |

### 10. Run

| Need | Operations | Status |
|---|---|---|
| queue, pinned steps | `cycle_cases_list` | exists |
| record results, attempts | `results_create`, `results_list`, `results_bulk_create` | exists |
| evidence | `attachments_upload` (413 when too large), `attachments_download` | exists |
| automated jobs | `jobs_list`, `jobs_cancel`, `jobs_reassign` | exists |
| per-step ignore/cancel, skip reason code, build under test, undo | | not yet (F4) |

### 11. Reports

| Need | Operations | Status |
|---|---|---|
| release, feature, cycle, product, org reports | `reports_release`, `reports_feature`, `reports_cycle`, `reports_product`, `reports_org` | exists |
| period filter: `from`, `to` (days in `tz`, both included), `tz` (IANA, default UTC); default the last 30 days ending today in `tz`; 422 for an unknown `tz`, `from` after `to`, or more than 366 days | `reports_release`, `reports_feature`, `reports_product`, `reports_org` | exists |
| trend: `trend{days[{date, success..cancel}], total, peak_day{date, total} or null, by_agents_pct}`, one zero-filled row per day of the period | `reports_release`, `reports_product`, `reports_org` | exists |
| release KPIs: `kpis{cases, ran, fail, error, skip, drift, success_rate}`; ran = all - untested, success rate = success / ran (ignore, skip and cancel count as ran) | `reports_release` | exists |
| feature rows: `path`, `drift`, `drifted[{key, ran_version, current_version}]`, `verdict` (`at_risk` on fail, error, stale or drift; else `not_started`, `ready` or `in_progress`) | `reports_release`, `reports_product` | exists |
| org KPIs: `kpis{ready_cases, products, success_rate, automated_pct, open_cycles, open_untested}`; product rows add `name, cases, automated_pct, results, success_rate, open_cycles` (`results.untested` counts untested cases in open cycles) | `reports_org` | exists |
| product-wide report: without `release`, `whole{counts, kpis, features}`, the product as it stands in the period | `reports_product` | exists |
| feature report: `release` optional (none: the period); items add `ran_version, current_version, actor{kind, name}, attempt, comment, defects, last_result{status, version, at, actor, attempt}` (`last_result` is set for a stale case too); `kpis{cases, success, success_rate_last5, drift}` | `reports_feature` | exists |
| feature history: `history[]`, the feature's last 5 cycles `{cycle_id, release_version, environment, status, at, counts, success_rate}`; ignores the period and the release | `reports_feature` | exists |
| "since last release" period | the app sets `from` to the latest `Release.released_at` from `releases_list` | exists |

### 12. Members

| Need | Operations | Status |
|---|---|---|
| list, add, change role, remove | `members_list`, `members_add`, `members_update`, `members_remove` | exists |
| invites: list, create, revoke | `invites_list`, `invites_create`, `invites_revoke` | exists |
| copy the invite link | `InviteCreated.token` from `invites_create`, shown once; the link carries it to the accept view | exists |
| resend an invite | revoke, then create (a new token) | exists |
| name search | `members_list?q=` (name or email, see Search) | exists (F8) |
| last active | `members_list` (`last_active_at`) | exists (F2) |
| invite emails | | out of scope (v1, owner decision) |

### 13. Tokens and agents

| Need | Operations | Status |
|---|---|---|
| tokens: list, create, revoke | `tokens_list`, `tokens_create`, `tokens_revoke` | exists |
| agents: list, create, edit, disable | `agents_list`, `agents_create`, `agents_update`, `agents_disable` | exists |
| agent enable, description, last active | `agents_enable`, `agents_create` / `agents_update` (`description`), `agents_list` (`last_active_at`) | exists (F2) |
| agent name rule | `agents_create`, `agents_update` (`name`) | exists |

`POST /agents/{agent_id}/enable` (`agents_enable`, admin) clears `disabled_at` and is idempotent. It is a 422
when the agent's owner is no longer a member or the agent's role is now above the owner's, the same rule as
`agents_create`. `description` is at most 500 characters; an empty string clears it.

An agent's `name` is the shared name rule (trimmed, 1 to 200 characters) and also lowercase letters and digits
with single dashes between them (`nightly-bot`), else a 422. It is unique among the org's agents, disabled ones
included, else a 409; a consumer may share it. Migration `0018` renamed existing agents to fit: each name was
lowercased with runs of other characters turned into one dash (`agent` when nothing was left). An already valid
name kept its own, and a later duplicate in the same org got `-2`, `-3`, oldest first.

`last_active_at` is the actor's latest authenticated request in the org, any method, written at most once a
minute.

### Actor directory

`GET /actors` (`actors_list`, read, any member) gives names for every actor and token that can appear on a
row, past ones included, with no emails or roles:

```json
{"actors": [{"id": "...", "kind": "user|agent|consumer", "name": "...", "disabled": false}],
 "tokens": [{"id": "...", "name": "...", "actor_id": "..."}]}
```

`disabled` is true for a removed member, a disabled agent or a revoked consumer.

### 14. Audit

| Need | Operations | Status |
|---|---|---|
| rows, diff, actor/action/via/entity/date filters, one case's history | `audit_list` | exists |
| actor kind filter, `q`, retention | `audit_list?actor_kind=&q=`, `audit_retention` | exists (F2) |
| request id and tool on rows | `audit_list` (`request_id`, `tool`, both found by `q`) | exists |

`request_id` is the `X-Request-ID` the API sent back on the response that wrote the row (`req_` and a ULID;
a client's own `X-Request-ID` is not used). Rows written by an MCP tool call carry the id of the `/mcp`
request and the tool's name in `tool`; `tool` is null for every other row. Both are null on rows from before
the change and on rows written outside a request.

`actor_kind` is one of `user` (a member in the app, no token), `token` (a member through a token), `agent` or
`consumer`; the four split the log. Agents use tokens too, but their rows are `agent`, not `token`. `q` (at
most 200 characters) matches, case-insensitively, the action, entity type, entity id or the actor's name.

`GET /audit/retention` (`audit_retention`) returns `{days, oldest_kept}`. `days` is the stated policy (90);
**it is not enforced yet**: nothing deletes audit rows. `oldest_kept` is the `created_at` of the oldest stored
row, null when there is none.

Action names are singular (`product.create`), not the mock's `products.create`.

### 15. MCP

All six need the audit-read permission (admins).

| Need | Operations | Status |
|---|---|---|
| server name, version, tool count | `GET /mcp/server` (`mcp_server_get`) | exists |
| tools table, per-tool calls and errors for the chosen range | `GET /mcp/tools` (`mcp_tools_list`) | exists; range added |
| usage chart: reads, writes, errors per hour or day | `GET /mcp/usage` (`mcp_usage`) | exists; reads/writes added |
| clients KPI (count and names) | `GET /mcp/clients` (`mcp_clients`) | added |
| updates feed | `GET /mcp/updates` (`mcp_updates`) | added |
| live usage | poll, see below | added |
| tool description, idempotent and destructive hints, errors by code | `McpToolOut.description`, `idempotent`, `destructive`, `errors_by_code` | added |
| recent calls with status and latency, "last call" in live mode | `GET /mcp/calls` (`mcp_calls`) | added |
| a call's target in its label (`cases_get PAY-101`, `search q=refund`) | | out of scope: arguments can carry case data, so they are not stored |
| a failed call's error body or note | | out of scope: only the HTTP status is stored |
| drift-guard CI results in the feed | | out of scope (v1, owner decision) |

**Range.** `mcp_tools_list`, `mcp_usage` and `mcp_clients` take `since` and `until` (ISO 8601). `since` is
floored and `until` ceiled to the bucket. `since >= until`, or a span over 90 days, is a 422.

`mcp_server_get`:

```json
{"name": "...", "version": "...", "tool_count": 105, "tool_list_hash": "..."}
```

`mcp_tools_list?since&until` (default: the last 30 days):

```json
{"since": "...", "until": "...", "total_def_tokens": 0,
 "items": [{"name": "...", "toolset": "...", "scope": "...", "description": "...",
            "read_only": true, "idempotent": true, "destructive": false, "def_tokens": 0,
            "calls_7d": 0, "errors_7d": 0, "calls_30d": 0, "errors_30d": 0,
            "calls": 0, "errors": 0, "errors_by_code": {"404": 0, "422": 0},
            "p50_resp_tokens": 0, "p95_resp_tokens": 0}]}
```

`calls` and `errors` cover the chosen range; `calls_7d`/`calls_30d` are fixed windows. `errors_by_code` splits
`errors` by HTTP status (keys are strings, only codes that occurred); its values sum to `errors` for calls
recorded since F6 (older hour rows have no codes). The mock's tool kind comes from `read_only`, `idempotent`
and `destructive`.

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
 "next_cursor": null, "total": 0}
```

`kind` is `server_started` or `tools_changed`. The feed is server-wide: every org sees the same rows, which
hold only tool names and versions. Each server start writes one row: `tools_changed` when the tool
list hash differs from the newest row, else `server_started`. With several worker processes, each start writes
its own row, so one deploy can show several `server_started` rows; only the first worker after a change writes
`tools_changed`.

`mcp_calls?since&until&tool&actor&cursor&limit` (paged, newest first; `limit` default 20, at most 100):

```json
{"items": [{"id": "...", "at": "...", "tool": "...", "actor_id": "...", "name": "...", "kind": "agent",
            "status": 200, "ms": 0, "resp_tokens": 0}],
 "next_cursor": null, "total": 0}
```

One row per call that reached a tool, kept 7 days. `status` is the HTTP status the tool got (an error when
`>= 400`), `ms` the time spent in the tool, `resp_tokens` the response size in ≈ tokens (bytes ÷ 4). A tool's
recent calls are `mcp_calls?tool=<name>`. The call's arguments and response body are not stored.

**Live.** The app polls `mcp_usage?bucket=hour`, `mcp_clients` and `mcp_calls?limit=1` (the "last call") every
15 seconds while live mode is on.
There is no server push (no SSE, no `notifications/tools/list_changed`).

### 16. Consumers (machines)

| Need | Operations | Status |
|---|---|---|
| cards, status filter, product filter | `consumers_list?status&product` | exists |
| name search | `consumers_list?q=` (see Search) | exists (F8) |
| card "N projects" | `ConsumerOut.project_count` | added |
| detail, heartbeat last 24 h, inventory | `consumers_get` | exists |
| rename, set products | `PATCH /consumers/{id}` `{name?, product_ids?}` | exists |
| revoke | `DELETE /consumers/{id}` | exists |
| pair | `POST /pair/approve` (`pairings_approve`) | exists |
| jobs per machine, with the rejected reason | `GET /consumers/{id}/jobs?status&cursor&limit` (`consumers_jobs`), `JobOut.reason` | added |
| jobs today, rejected today | `ConsumerDetail.jobs_today`, `rejected_today` | added |
| pause, resume | `POST /consumers/{id}/pause` (`consumers_pause`), `POST /consumers/{id}/resume` (`consumers_resume`) | added |
| pair paused ("accept jobs now" off) | `pairings_approve` `{..., accept_jobs: false}` | added |
| pending-pairing preview | `GET /pair/{user_code}` (`pairings_get`) | added |
| deny pairing | `POST /pair/deny` `{user_code}` (`pairings_deny`) | added |
| inventory roster, tests found and linked | `GET /consumers/{id}/roster?project&cursor&limit` (`consumers_roster`), `ConsumerDetail.tests_found`, `tests_linked` | added |

`ConsumerOut`:

```json
{"id": "...", "name": "...", "status": "online", "product_ids": ["..."], "project_count": 2,
 "last_heartbeat_at": "...", "busy_job_id": null, "tj_version": "...", "python": "...", "os": "...",
 "paused_at": null, "revoked_at": null, "created_at": "..."}
```

`status` is `online`, `offline`, `busy` or `revoked`. `project_count` is the number of inventoried projects.
Paused is not a status: a paused consumer keeps its status and has `paused_at` set.

`ConsumerDetail` adds `heartbeats: [{at, busy_job_id}]` (last 24 hours, newest first),
`inventory: [{project, hash, test_count, updated_at}]`, `jobs_today`, `rejected_today`, `tests_found` and
`tests_linked`. `jobs_today` and `rejected_today` count jobs created for the consumer in the **last 24 hours**
(a rolling window, not the calendar day), so the app labels them "last 24 h". `tests_found` counts the refs in
its inventory across projects; `tests_linked` those that are the `automation_ref` of a case the caller can see.

**Jobs.** `consumers_jobs` pages the consumer's jobs, newest first, limited to products the caller can see;
`status` filters (`queued`, `running`, `done`, `failed`, `rejected`, ...). Each item is a `JobOut`, which now has
`reason`: why the job was rejected (always set) or failed (`consumer lost` when it stalled twice), else `null`.

**Rejected.** A machine that can't run a job reports `state: "rejected"` with a `reason` (required, 422 without
it). The job ends `rejected` and is not requeued: its open cycle cases are cancelled with the comment
`job rejected: <reason>`, as a failed job's are, so people see why and rerun them. The consumer stays online.

**Pause.** `consumers_pause` and `consumers_resume` (admin) set and clear `paused_at`; a second call is a no-op
with no audit row, and a revoked consumer is a 409. A paused consumer keeps and finishes the job it holds but
`next_job` gives it no new one, starting a cycle that names it is a 409 `consumer_paused`, and a stalled job is
not requeued onto it.

**Pairing preview and deny.** The machine may send `{os, tj_version, python, projects}` with `POST /pair`
(every field optional; an empty body is still fine). `pairings_get` (admin) returns
`{user_code, status, expires_at, os, tj_version, python, projects}` for a request not yet tied to an org, or
tied to this one; unknown (or another org's) is 404, an expired pending one is 410. `pairings_deny` (admin, 204) marks a pending request `denied`; the machine's
next `POST /pair/token` gets 403 `access_denied`, and denying it again is a 409 `pairing_not_pending`.

**Roster.** `consumers_roster` pages `{project, ref, case_key}` for the consumer's inventory, by project, then
in the order the machine uploaded them; `project` filters. `case_key` (`PAY-12`) is the visible case whose `automation_ref` is the ref, else `null`.

**Undo.** Migration `0014` adds only nullable columns and the `denied` pairing status. Its downgrade deletes
`denied` pairing requests (short-lived, and the old schema has no such status); everything else is kept.

For reference, the machine side (consumer token, not the app):

- `POST /api/v1/consumers/me/heartbeat` `{inventory_hashes, busy_job_id, tj_version, python, os}` returns
  `{inventory_wanted, cancel_job_ids}`. The server derives busy from its own jobs; `busy_job_id` is ignored.
- `PUT /api/v1/consumers/me/inventory/{project}` `{hash, roster}` returns `{changed, test_count}`.
