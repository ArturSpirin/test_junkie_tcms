"""consumers F7: job.reason, consumer.paused_at, pairing_request.machine, denied pairings

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-22 22:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only nullable columns and a wider check: existing rows stay as they are.
    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reason", sa.String(length=500), nullable=True))
    with op.batch_alter_table("consumer", schema=None) as batch_op:
        batch_op.add_column(sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("pairing_request", schema=None) as batch_op:
        batch_op.add_column(sa.Column("machine", sa.JSON(none_as_null=True), nullable=True))
        batch_op.drop_constraint(op.f("ck_pairing_request_status"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_pairing_request_status"), "status IN ('pending', 'approved', 'claimed', 'denied')"
        )


def downgrade() -> None:
    # Denied requests are short-lived and the old schema has no denied: they are deleted.
    op.execute("DELETE FROM pairing_request WHERE status = 'denied'")
    with op.batch_alter_table("pairing_request", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_pairing_request_status"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_pairing_request_status"), "status IN ('pending', 'approved', 'claimed')"
        )
        batch_op.drop_column("machine")
    with op.batch_alter_table("consumer", schema=None) as batch_op:
        batch_op.drop_column("paused_at")
    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.drop_column("reason")
