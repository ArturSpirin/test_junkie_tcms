# Test Junkie TCMS

An AI-native, open-source test case management system for [Test Junkie](https://github.com/ArturSpirin/test_junkie).
Apache-2.0.

## What's in this release

- **Orgs and access:** orgs, members, invites, roles, scoped API tokens, agents, the session login and an
  append-only audit log.
- **Catalog:** products, feature trees, releases and test plans.
- **Cases:** test cases with version history, tags, search, and CSV and markdown-bundle import and export.
- **Execution:** cycles pinned to case versions, bulk cycles by release, single and bulk results with per-step
  status, attachments, and automated runs on paired consumers.
- **Reports:** org, product, release, feature and cycle reports.
- **MCP server** at `/mcp`, so AI agents can use all of the above (see [MCP](#mcp)).

The interactive API docs are at `/api/v1/docs` and the schema at `/api/v1/openapi.json`. Over MCP, `tools/list`
shows the tools your token and toolsets give you; an org admin (or a token with `audit:read`) also sees every tool
at `GET /api/v1/orgs/{org}/mcp/tools`.

## Try it (SQLite, one command)

Python 3.11 or newer, in a bash shell (Git Bash on Windows):

```sh
pip install -r requirements.lock && pip install --no-deps .
TJ_TCMS_ADMIN_PASSWORD=change-me-now test-junkie-tcms create-admin --email you@example.com --name You --org-slug acme --org-name Acme
TJ_TCMS_INSECURE_COOKIES=true test-junkie-tcms serve
```

The data goes to `./tcms.db`. The API is at `http://127.0.0.1:8000/api/v1`, its schema at `/api/v1/openapi.json`.

## Run it with Postgres (Docker Compose)

```sh
docker compose up --build
docker compose exec -e TJ_TCMS_ADMIN_PASSWORD=change-me-now app \
  test-junkie-tcms create-admin --email you@example.com --name You --org-slug acme --org-name Acme
```

Consumers long-poll for jobs (`GET /api/v1/consumers/me/jobs/next?wait=30`). Each waiting consumer holds one
server worker thread for up to 30 s, so N consumers use N threads; size the server's thread pool to your consumer
count plus normal traffic.

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `TJ_TCMS_DATABASE_URL` | `sqlite:///./tcms.db` | SQLAlchemy URL; `postgresql+psycopg://...` for Postgres |
| `TJ_TCMS_SECRET_KEY` | a dev value | Key for session hashing. Set it in every real deployment |
| `TJ_TCMS_INSECURE_COOKIES` | `false` | `true` drops the `Secure` cookie flag, for plain http on localhost |
| `TJ_TCMS_SESSION_TTL_HOURS` | `336` | Session lifetime |
| `TJ_TCMS_ATTACHMENTS_DIR` | `./attachments` | Where uploaded result attachments are kept |
| `TJ_TCMS_ATTACHMENT_MAX_BYTES` | `26214400` (25 MiB) | Largest attachment accepted |
| `TJ_TCMS_MCP_DEFAULT_TOOLSETS` | `core,cases,execution` | MCP toolsets `/mcp` serves when the client names none; a comma list or `all` |
| `TJ_TCMS_MCP_ALLOWED_HOSTS` | empty | `Host` headers `/mcp` accepts (comma list, `*` wildcards); empty turns the DNS-rebinding check off |
| `TJ_TCMS_ADMIN_PASSWORD` | prompt | Password for `create-admin` |

## Commands

- `test-junkie-tcms serve [--host H] [--port P]`: applies migrations, then serves.
- `test-junkie-tcms migrate`: applies migrations.
- `test-junkie-tcms create-admin ...`: the first user, their org and the owner role. It applies migrations first,
  so it works on a new database; so does `sweep-idempotency`.
- `test-junkie-tcms sweep-idempotency [--batch-size N] [--max-batches M]`: deletes `Idempotency-Key` records
  past their 24 h window, `N` (default 1000) per commit. A record still pending is kept an hour longer. Run it
  hourly, e.g. from cron: `0 * * * * test-junkie-tcms sweep-idempotency`.
- `test-junkie-tcms mcp --url URL [--token-env VAR] [--toolsets LIST]`: a stdio MCP server that relays to a
  TCMS server's `/mcp` (see [MCP](#mcp)).

## Auth

- **Browser:** `POST /api/v1/auth/login` sets a session cookie and a `tj_csrf` cookie. Every unsafe request
  sends the `tj_csrf` value back in the `X-CSRF-Token` header.
- **Scripts and agents:** `Authorization: Bearer tjt_...`. Tokens are scoped to one org, carry scopes, and can be
  revoked. No CSRF header is needed.

Every change is written to an append-only audit log naming the person, the agent and the token behind it.

## MCP

The server speaks MCP (streamable HTTP) at `/mcp`, with the same `Authorization: Bearer tjt_...` token as the API.
A token only sees the tools its scopes allow.

Tools come in toolsets. By default `/mcp` serves `core,cases,execution`; ask for others with `?toolsets=`, e.g.
`/mcp?toolsets=reports,planning` or `/mcp?toolsets=all`. `core` is always on, and an unknown name is rejected with
a 400. To change the server's default, set `TJ_TCMS_MCP_DEFAULT_TOOLSETS`.

| Toolset | Tools |
| --- | --- |
| `core` | who am I, my orgs |
| `cases` | cases and their versions, tags, search, import and export |
| `execution` | cycles and their cases, results (single and bulk), attachments, automated jobs |
| `planning` | creating and changing cycles (bulk by release too), test plans |
| `catalog` | products, features, releases |
| `admin` | members, invites, agents, tokens, the audit log, MCP usage |
| `consumers` | paired consumers and pairing approval |
| `reports` | org, product, release, feature and cycle reports |

For a client that only speaks stdio, `test-junkie-tcms mcp` relays to a server's `/mcp`:

```sh
TJ_TCMS_TOKEN=tjt_... test-junkie-tcms mcp --url https://tcms.example.com --toolsets reports,planning
```

`--token-env` names another env var for the token; without `--toolsets` the server's default applies.

## Develop

```sh
pip install -r requirements.lock && pip install --no-deps -e .
ruff check . && ruff format --check .
PYTHONPATH=. python -m test_junkie run -s tests
```

`requirements.lock` is made by `python scripts/lock.py` (uv, one lock for every platform, with markers). Never edit
it by hand: after changing a pin in `pyproject.toml`, run the script and commit both. CI runs
`python scripts/lock.py --check`.

The tests are [Test Junkie](https://github.com/ArturSpirin/test_junkie) suites, one per file under `tests/`, and
the run exits non-zero on any failed or errored test. They run on SQLite. To run them on Postgres too, set
`TJ_TCMS_TEST_POSTGRES_URL=postgresql+psycopg://user:pw@host:port/db`.
