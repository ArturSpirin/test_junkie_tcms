"""The tenancy rule (PLAN-27 §3), checked against table metadata.

Every tenant table has a non-null `org_id` (FK to org) and UNIQUE(org_id, id); every FK from one tenant
table to another is composite and carries `org_id`, so a row can't point into another org. The one link
from a tenant table to a global parent is membership.user_id -> user.id.
"""

from sqlalchemy import MetaData, UniqueConstraint

from test_junkie_tcms.db.base import GLOBAL_TABLES

GLOBAL_PARENT_LINKS = {("membership", "user")}


def tenancy_violations(metadata: MetaData, global_tables=GLOBAL_TABLES) -> list[str]:
    problems: list[str] = []
    tenant = {name for name in metadata.tables if name not in global_tables}
    for name in sorted(tenant):
        table = metadata.tables[name]
        org_id = table.c.get("org_id")
        if org_id is None:
            problems.append(f"{name}: no org_id column")
            continue
        if org_id.nullable:
            problems.append(f"{name}: org_id is nullable")
        if not any(fk.column.table.name == "org" for fk in org_id.foreign_keys):
            problems.append(f"{name}: org_id has no FK to org")
        uniques = {
            frozenset(c.name for c in con.columns)
            for con in table.constraints
            if isinstance(con, UniqueConstraint)
        }
        if frozenset({"org_id", "id"}) not in uniques:
            problems.append(f"{name}: no UNIQUE(org_id, id)")
        for fkc in table.foreign_key_constraints:
            target = fkc.referred_table.name
            pairs = {el.parent.name: el.column.name for el in fkc.elements}
            if target == "org":
                continue
            if target in tenant:
                if len(pairs) < 2 or pairs.get("org_id") != "org_id":
                    problems.append(f"{name}: FK {sorted(pairs)} -> {target} is not composite on org_id")
            elif (name, target) not in GLOBAL_PARENT_LINKS:
                problems.append(f"{name}: FK {sorted(pairs)} -> global table {target} is not allowed")
    return problems
