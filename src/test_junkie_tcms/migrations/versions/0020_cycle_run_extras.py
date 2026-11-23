"""cycle and run extras: closed/stopped by, split, retries, result skip_reason and build (F4)

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-22 19:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cycle", schema=None) as batch_op:
        batch_op.add_column(sa.Column("closed_by_actor_id", sa.String(length=26), nullable=True))
        batch_op.add_column(sa.Column("split", sa.String(length=10), server_default="even", nullable=False))
        batch_op.add_column(sa.Column("retries", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("stopped_by_actor_id", sa.String(length=26), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_cycle_org_id_closed_by_actor_id_actor"),
            "actor",
            ["org_id", "closed_by_actor_id"],
            ["org_id", "id"],
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_cycle_org_id_stopped_by_actor_id_actor"),
            "actor",
            ["org_id", "stopped_by_actor_id"],
            ["org_id", "id"],
        )
        batch_op.create_check_constraint(
            op.f("ck_cycle_split"), "split IN ('even', 'by_feature', 'first_free')"
        )
        batch_op.create_check_constraint(op.f("ck_cycle_retries"), "retries >= 0 AND retries <= 2")

    with op.batch_alter_table("result", schema=None) as batch_op:
        batch_op.add_column(sa.Column("skip_reason", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("build", sa.String(length=120), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_result_skip_reason"),
            "skip_reason IS NULL"
            " OR skip_reason IN ('defect', 'env', 'data', 'dep', 'na_env', 'flag', 'other')",
        )


def downgrade() -> None:
    with op.batch_alter_table("result", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_result_skip_reason"), type_="check")
        batch_op.drop_column("build")
        batch_op.drop_column("skip_reason")

    with op.batch_alter_table("cycle", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_cycle_retries"), type_="check")
        batch_op.drop_constraint(op.f("ck_cycle_split"), type_="check")
        batch_op.drop_constraint(op.f("fk_cycle_org_id_stopped_by_actor_id_actor"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_cycle_org_id_closed_by_actor_id_actor"), type_="foreignkey")
        batch_op.drop_column("stopped_by_actor_id")
        batch_op.drop_column("stopped_at")
        batch_op.drop_column("retries")
        batch_op.drop_column("split")
        batch_op.drop_column("closed_by_actor_id")
