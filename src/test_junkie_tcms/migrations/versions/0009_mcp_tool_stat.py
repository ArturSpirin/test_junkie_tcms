"""mcp_tool_stat: MCP calls, errors and response sizes per org, tool, actor and hour

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
        "mcp_tool_stat",
        sa.Column("tool", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.String(length=26), nullable=False),
        sa.Column("hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("resp_bytes_sum", sa.BigInteger(), nullable=False),
        sa.Column("resp_bytes_hist", sa.JSON(), nullable=False),
        sa.Column("org_id", sa.String(length=26), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "actor_id"],
            ["actor.org_id", "actor.id"],
            name=op.f("fk_mcp_tool_stat_org_id_actor_id_actor"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["org.id"], name=op.f("fk_mcp_tool_stat_org_id_org")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_tool_stat")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_mcp_tool_stat_org_id_id")),
        sa.UniqueConstraint(
            "org_id", "tool", "actor_id", "hour", name=op.f("uq_mcp_tool_stat_org_id_tool_actor_id_hour")
        ),
    )
    with op.batch_alter_table("mcp_tool_stat", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mcp_tool_stat_org_id"), ["org_id"], unique=False)
        batch_op.create_index("ix_mcp_tool_stat_org_id_hour", ["org_id", "hour"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("mcp_tool_stat", schema=None) as batch_op:
        batch_op.drop_index("ix_mcp_tool_stat_org_id_hour")
        batch_op.drop_index(batch_op.f("ix_mcp_tool_stat_org_id"))

    op.drop_table("mcp_tool_stat")
