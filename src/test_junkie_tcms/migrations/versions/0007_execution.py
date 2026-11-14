"""execution: cycles pinned to case versions, bulk cycle batches, results and attachments

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14 12:45:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachment",
        sa.Column("product_id", sa.String(length=26), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=127), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("created_by_actor_id", sa.String(length=26), nullable=False),
        sa.Column("org_id", sa.String(length=26), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "created_by_actor_id"],
            ["actor.org_id", "actor.id"],
            name=op.f("fk_attachment_org_id_created_by_actor_id_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "product_id"],
            ["product.org_id", "product.id"],
            name=op.f("fk_attachment_org_id_product_id_product"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["org.id"], name=op.f("fk_attachment_org_id_org")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachment")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_attachment_org_id_id")),
        sa.UniqueConstraint(
            "org_id",
            "product_id",
            "sha256",
            "filename",
            name=op.f("uq_attachment_org_id_product_id_sha256_filename"),
        ),
    )
    with op.batch_alter_table("attachment", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_attachment_org_id"), ["org_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_attachment_product_id"), ["product_id"], unique=False)

    op.create_table(
        "cycle_batch",
        sa.Column("product_id", sa.String(length=26), nullable=False),
        sa.Column("release_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=True),
        sa.Column("created_by_actor_id", sa.String(length=26), nullable=False),
        sa.Column("org_id", sa.String(length=26), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mode IN ('features', 'plans')", name=op.f("ck_cycle_batch_mode")),
        sa.ForeignKeyConstraint(
            ["org_id", "created_by_actor_id"],
            ["actor.org_id", "actor.id"],
            name=op.f("fk_cycle_batch_org_id_created_by_actor_id_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "product_id"],
            ["product.org_id", "product.id"],
            name=op.f("fk_cycle_batch_org_id_product_id_product"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "release_id"],
            ["release.org_id", "release.id"],
            name=op.f("fk_cycle_batch_org_id_release_id_release"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["org.id"], name=op.f("fk_cycle_batch_org_id_org")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cycle_batch")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_cycle_batch_org_id_id")),
    )
    with op.batch_alter_table("cycle_batch", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cycle_batch_org_id"), ["org_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cycle_batch_product_id"), ["product_id"], unique=False)

    op.create_table(
        "cycle",
        sa.Column("product_id", sa.String(length=26), nullable=False),
        sa.Column("release_id", sa.String(length=26), nullable=True),
        sa.Column("plan_id", sa.String(length=26), nullable=True),
        sa.Column("batch_id", sa.String(length=26), nullable=True),
        sa.Column("feature_id", sa.String(length=26), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("default_assignee_actor_id", sa.String(length=26), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_actor_id", sa.String(length=26), nullable=False),
        sa.Column("org_id", sa.String(length=26), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('open', 'closed')", name=op.f("ck_cycle_status")),
        sa.ForeignKeyConstraint(
            ["org_id", "batch_id"],
            ["cycle_batch.org_id", "cycle_batch.id"],
            name=op.f("fk_cycle_org_id_batch_id_cycle_batch"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "created_by_actor_id"],
            ["actor.org_id", "actor.id"],
            name=op.f("fk_cycle_org_id_created_by_actor_id_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "default_assignee_actor_id"],
            ["actor.org_id", "actor.id"],
            name=op.f("fk_cycle_org_id_default_assignee_actor_id_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "feature_id"],
            ["feature.org_id", "feature.id"],
            name=op.f("fk_cycle_org_id_feature_id_feature"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "plan_id"],
            ["test_plan.org_id", "test_plan.id"],
            name=op.f("fk_cycle_org_id_plan_id_test_plan"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "product_id"],
            ["product.org_id", "product.id"],
            name=op.f("fk_cycle_org_id_product_id_product"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "release_id"],
            ["release.org_id", "release.id"],
            name=op.f("fk_cycle_org_id_release_id_release"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["org.id"], name=op.f("fk_cycle_org_id_org")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cycle")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_cycle_org_id_id")),
    )
    with op.batch_alter_table("cycle", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cycle_org_id"), ["org_id"], unique=False)
        batch_op.create_index("ix_cycle_org_id_batch_id", ["org_id", "batch_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cycle_product_id"), ["product_id"], unique=False)

    op.create_table(
        "cycle_case",
        sa.Column("cycle_id", sa.String(length=26), nullable=False),
        sa.Column("case_id", sa.String(length=26), nullable=False),
        sa.Column("case_version_id", sa.String(length=26), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("assignee_actor_id", sa.String(length=26), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("last_result_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("org_id", sa.String(length=26), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('untested', 'success', 'fail', 'error', 'ignore', 'skip', 'cancel')",
            name=op.f("ck_cycle_case_status"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "assignee_actor_id"],
            ["actor.org_id", "actor.id"],
            name=op.f("fk_cycle_case_org_id_assignee_actor_id_actor"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "case_id"],
            ["test_case.org_id", "test_case.id"],
            name=op.f("fk_cycle_case_org_id_case_id_test_case"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "case_version_id"],
            ["case_version.org_id", "case_version.id"],
            name=op.f("fk_cycle_case_org_id_case_version_id_case_version"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "cycle_id"],
            ["cycle.org_id", "cycle.id"],
            name=op.f("fk_cycle_case_org_id_cycle_id_cycle"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["org.id"], name=op.f("fk_cycle_case_org_id_org")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cycle_case")),
        sa.UniqueConstraint(
            "org_id", "cycle_id", "case_id", name=op.f("uq_cycle_case_org_id_cycle_id_case_id")
        ),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_cycle_case_org_id_id")),
    )
    with op.batch_alter_table("cycle_case", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cycle_case_case_id"), ["case_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cycle_case_cycle_id"), ["cycle_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_cycle_case_org_id"), ["org_id"], unique=False)

    op.create_table(
        "result",
        sa.Column("cycle_case_id", sa.String(length=26), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=26), nullable=False),
        sa.Column("via", sa.String(length=8), nullable=False),
        sa.Column("comment", sa.JSON(), nullable=False),
        sa.Column("comment_text", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("attachment_ids", sa.JSON(), nullable=False),
        sa.Column("defects", sa.JSON(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("org_id", sa.String(length=26), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('success', 'fail', 'error', 'ignore', 'skip', 'cancel')",
            name=op.f("ck_result_status"),
        ),
        sa.CheckConstraint("via IN ('ui', 'api', 'mcp')", name=op.f("ck_result_via")),
        sa.ForeignKeyConstraint(
            ["org_id", "actor_id"], ["actor.org_id", "actor.id"], name=op.f("fk_result_org_id_actor_id_actor")
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "cycle_case_id"],
            ["cycle_case.org_id", "cycle_case.id"],
            name=op.f("fk_result_org_id_cycle_case_id_cycle_case"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["org.id"], name=op.f("fk_result_org_id_org")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_result")),
        sa.UniqueConstraint(
            "org_id", "cycle_case_id", "attempt", name=op.f("uq_result_org_id_cycle_case_id_attempt")
        ),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_result_org_id_id")),
    )
    with op.batch_alter_table("result", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_result_cycle_case_id"), ["cycle_case_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_result_org_id"), ["org_id"], unique=False)

    op.create_table(
        "result_attachment",
        sa.Column("result_id", sa.String(length=26), nullable=False),
        sa.Column("attachment_id", sa.String(length=26), nullable=False),
        sa.Column("org_id", sa.String(length=26), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "attachment_id"],
            ["attachment.org_id", "attachment.id"],
            name=op.f("fk_result_attachment_org_id_attachment_id_attachment"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "result_id"],
            ["result.org_id", "result.id"],
            name=op.f("fk_result_attachment_org_id_result_id_result"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["org.id"], name=op.f("fk_result_attachment_org_id_org")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_result_attachment")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_result_attachment_org_id_id")),
        sa.UniqueConstraint(
            "org_id",
            "result_id",
            "attachment_id",
            name=op.f("uq_result_attachment_org_id_result_id_attachment_id"),
        ),
    )
    with op.batch_alter_table("result_attachment", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_result_attachment_attachment_id"), ["attachment_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_result_attachment_org_id"), ["org_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_result_attachment_result_id"), ["result_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("result_attachment", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_result_attachment_result_id"))
        batch_op.drop_index(batch_op.f("ix_result_attachment_org_id"))
        batch_op.drop_index(batch_op.f("ix_result_attachment_attachment_id"))

    op.drop_table("result_attachment")
    with op.batch_alter_table("result", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_result_org_id"))
        batch_op.drop_index(batch_op.f("ix_result_cycle_case_id"))

    op.drop_table("result")
    with op.batch_alter_table("cycle_case", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cycle_case_org_id"))
        batch_op.drop_index(batch_op.f("ix_cycle_case_cycle_id"))
        batch_op.drop_index(batch_op.f("ix_cycle_case_case_id"))

    op.drop_table("cycle_case")
    with op.batch_alter_table("cycle", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cycle_product_id"))
        batch_op.drop_index("ix_cycle_org_id_batch_id")
        batch_op.drop_index(batch_op.f("ix_cycle_org_id"))

    op.drop_table("cycle")
    with op.batch_alter_table("cycle_batch", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cycle_batch_product_id"))
        batch_op.drop_index(batch_op.f("ix_cycle_batch_org_id"))

    op.drop_table("cycle_batch")
    with op.batch_alter_table("attachment", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_attachment_product_id"))
        batch_op.drop_index(batch_op.f("ix_attachment_org_id"))

    op.drop_table("attachment")
