# Test Junkie TCMS

An AI-native, open-source test case management system for [Test Junkie](https://github.com/ArturSpirin/test_junkie).
Apache-2.0.

Early days: this release has orgs, users, roles, API tokens, the session login and the audit log. Test cases, runs
and reports come next.

## Try it (SQLite, one command)

Python 3.11 or newer:

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

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `TJ_TCMS_DATABASE_URL` | `sqlite:///./tcms.db` | SQLAlchemy URL; `postgresql+psycopg://...` for Postgres |
| `TJ_TCMS_SECRET_KEY` | a dev value | Key for session hashing. Set it in every real deployment |
| `TJ_TCMS_INSECURE_COOKIES` | `false` | `true` drops the `Secure` cookie flag, for plain http on localhost |
| `TJ_TCMS_SESSION_TTL_HOURS` | `336` | Session lifetime |
| `TJ_TCMS_ADMIN_PASSWORD` | prompt | Password for `create-admin` |

## Commands

- `test-junkie-tcms serve [--host H] [--port P]`: applies migrations, then serves.
- `test-junkie-tcms migrate`: applies migrations.
- `test-junkie-tcms create-admin ...`: the first user, their org and the owner role.
- `test-junkie-tcms sweep-idempotency [--batch-size N] [--max-batches M]`: deletes `Idempotency-Key` records
  past their 24 h window, `N` (default 1000) per commit. A record still pending is kept an hour longer. Run it
  hourly, e.g. from cron: `0 * * * * test-junkie-tcms sweep-idempotency`.

## Auth

- **Browser:** `POST /api/v1/auth/login` sets a session cookie and a `tj_csrf` cookie. Every unsafe request
  sends the `tj_csrf` value back in the `X-CSRF-Token` header.
- **Scripts and agents:** `Authorization: Bearer tjt_...`. Tokens are scoped to one org, carry scopes, and can be
  revoked. No CSRF header is needed.

Every change is written to an append-only audit log naming the person, the agent and the token behind it.

## Develop

```sh
pip install -r requirements.lock && pip install --no-deps -e .
ruff check . && ruff format --check .
pytest
```

The tests run on SQLite. Set `TJ_TCMS_TEST_POSTGRES_URL=postgresql+psycopg://user:pw@host:port/db` to run them
on Postgres too.
