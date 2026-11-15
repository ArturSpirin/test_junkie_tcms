"""jobs: automated cycle runs on consumers (cycle.mode, cycle_case.runner, job, result via consumer)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-14 16:30:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("cycle_id", sa.String(length=26), nullable=False),
        sa.Column("consumer_id", sa.String(length=26), nullable=False),
        sa.Column("project", sa.String(length=200), nullable=False),
        sa.Column("refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("timeout_s", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_beat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("org_id", sa.String(length=26), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'claimed', 'running', 'done', 'failed', 'cancelled', 'rejected')",
            name=op.f("ck_job_status"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "consumer_id"],
            ["consumer.org_id", "consumer.id"],
            name=op.f("fk_job_org_id_consumer_id_consumer"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "cycle_id"], ["cycle.org_id", "cycle.id"], name=op.f("fk_job_org_id_cycle_id_cycle")
        ),
        sa.ForeignKeyConstraint(["org_id"], ["org.id"], name=op.f("fk_job_org_id_org")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_job_org_id_id")),
    )
    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_job_org_id"), ["org_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_job_cycle_id"), ["cycle_id"], unique=False)
        batch_op.create_index("ix_job_consumer_id_status", ["consumer_id", "status"], unique=False)

    with op.batch_alter_table("cycle", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mode", sa.String(length=10), server_default="manual", nullable=False))
        batch_op.create_check_constraint(op.f("ck_cycle_mode"), "mode IN ('manual', 'automated', 'both')")

    with op.batch_alter_table("cycle_case", schema=None) as batch_op:
        batch_op.add_column(sa.Column("runner", sa.String(length=8), server_default="person", nullable=False))
        batch_op.add_column(sa.Column("consumer_id", sa.String(length=26), nullable=True))
        batch_op.add_column(sa.Column("job_id", sa.String(length=26), nullable=True))
        batch_op.create_index(batch_op.f("ix_cycle_case_job_id"), ["job_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_cycle_case_org_id_consumer_id_consumer"),
            "consumer",
            ["org_id", "consumer_id"],
            ["org_id", "id"],
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_cycle_case_org_id_job_id_job"), "job", ["org_id", "job_id"], ["org_id", "id"]
        )
        batch_op.create_check_constraint(op.f("ck_cycle_case_runner"), "runner IN ('person', 'consumer')")

    # Results a consumer reports carry via = 'consumer'.
    with op.batch_alter_table("result", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_result_via"), type_="check")
        batch_op.create_check_constraint(op.f("ck_result_via"), "via IN ('ui', 'api', 'mcp', 'consumer')")


def downgrade() -> None:
    with op.batch_alter_table("result", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_result_via"), type_="check")
        batch_op.create_check_constraint(op.f("ck_result_via"), "via IN ('ui', 'api', 'mcp')")

    with op.batch_alter_table("cycle_case", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_cycle_case_runner"), type_="check")
        batch_op.drop_constraint(batch_op.f("fk_cycle_case_org_id_job_id_job"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_cycle_case_org_id_consumer_id_consumer"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_cycle_case_job_id"))
        batch_op.drop_column("job_id")
        batch_op.drop_column("consumer_id")
        batch_op.drop_column("runner")

    with op.batch_alter_table("cycle", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_cycle_mode"), type_="check")
        batch_op.drop_column("mode")

    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.drop_index("ix_job_consumer_id_status")
        batch_op.drop_index(batch_op.f("ix_job_cycle_id"))
        batch_op.drop_index(batch_op.f("ix_job_org_id"))

    op.drop_table("job")
