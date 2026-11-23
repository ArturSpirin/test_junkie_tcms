"""audit_event request_id and tool; existing agent names meet the agent name rule

Every agent that isn't a consumer gets a name of lowercase letters and digits with single dashes, unique in
its org. Names that already meet the rule keep theirs first; the rest are lowercased, each run of other
characters becomes a dash, and a duplicate gets -2, -3, ... in created order. The rename is one-way:
downgrade drops the two columns and keeps the new names.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-23 04:00:00.000000
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

VALID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX = 200


def normalize(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return base[: MAX - 10].strip("-") or "agent"  # room for a suffix


def new_names(rows) -> dict[str, str]:
    """`{actor id: new name}` for the rows (id, org_id, name, created_at) whose name changes."""
    by_org: dict[str, list] = {}
    for row in rows:
        by_org.setdefault(row.org_id, []).append(row)
    renamed = {}
    for agents in by_org.values():
        agents.sort(key=lambda r: (not VALID.match(r.name), r.created_at, r.id))
        taken: set[str] = set()
        for row in agents:
            base = row.name if VALID.match(row.name) else normalize(row.name)
            name, n = base, 2
            while name in taken:
                suffix = f"-{n}"
                name, n = base[: MAX - len(suffix)].strip("-") + suffix, n + 1
            taken.add(name)
            if name != row.name:
                renamed[row.id] = name
    return renamed


def upgrade() -> None:
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("request_id", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("tool", sa.String(length=100), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, org_id, name, created_at FROM actor "
            "WHERE kind = 'agent' AND id NOT IN (SELECT actor_id FROM consumer)"
        )
    ).all()
    for actor_id, name in new_names(rows).items():
        bind.execute(sa.text("UPDATE actor SET name = :name WHERE id = :id"), {"name": name, "id": actor_id})


def downgrade() -> None:
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.drop_column("tool")
        batch_op.drop_column("request_id")
