"""idempotency: index expires_at for the sweeper

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14 10:30:00.000000
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("idempotency_record", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_idempotency_record_expires_at"), ["expires_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("idempotency_record", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_idempotency_record_expires_at"))
