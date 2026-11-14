"""Roles and the scopes they grant (PLAN-27 §4, T1 plan v2)."""

from test_junkie_tcms.db.models import ROLES

READ = "read"
WRITE_CATALOG = "write:catalog"
WRITE_PLANNING = "write:planning"
WRITE_CASES = "write:cases"
WRITE_EXECUTION = "write:execution"
AUDIT_READ = "audit:read"
ADMIN = "admin"
TOKENS_SELF = "tokens:self"

ALL_SCOPES = frozenset(
    {READ, WRITE_CATALOG, WRITE_PLANNING, WRITE_CASES, WRITE_EXECUTION, AUDIT_READ, ADMIN, TOKENS_SELF}
)

ROLE_RANK = {role: rank for rank, role in enumerate(ROLES)}

_VIEWER = frozenset({READ, TOKENS_SELF})
_TESTER = _VIEWER | {WRITE_EXECUTION}
_EDITOR = _TESTER | {WRITE_CASES, WRITE_PLANNING}

ROLE_SCOPES = {
    "viewer": _VIEWER,
    "tester": _TESTER,
    "editor": _EDITOR,
    "admin": ALL_SCOPES,
    "owner": ALL_SCOPES,
}


def lower_role(a: str | None, b: str | None) -> str | None:
    if a is None or b is None:
        return None
    return a if ROLE_RANK[a] <= ROLE_RANK[b] else b
