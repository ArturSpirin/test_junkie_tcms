"""plans: draft status, audit_event entity index

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14 10:30:00.000000
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing plans keep their status; only new plans start as draft (model default).
    with op.batch_alter_table("test_plan", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_test_plan_status"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_test_plan_status"), "status IN ('draft', 'active', 'archived')"
        )
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.create_index("ix_audit_event_entity", ["org_id", "entity_type", "entity_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_event_entity")
    # Drafts become active: the old schema has no draft.
    op.execute("UPDATE test_plan SET status = 'active' WHERE status = 'draft'")
    with op.batch_alter_table("test_plan", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_test_plan_status"), type_="check")
        batch_op.create_check_constraint(op.f("ck_test_plan_status"), "status IN ('active', 'archived')")
