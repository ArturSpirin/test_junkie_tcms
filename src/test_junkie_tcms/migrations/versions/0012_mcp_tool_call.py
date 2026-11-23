"""mcp_tool_call: one row per MCP call (kept 7 days), and mcp_tool_stat.error_codes

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-22 20:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("mcp_tool_stat", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("error_codes", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
    op.create_table(
        "mcp_tool_call",
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tool", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.String(length=26), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("ms", sa.Integer(), nullable=False),
        sa.Column("resp_bytes", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(length=26), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "actor_id"],
            ["actor.org_id", "actor.id"],
            name=op.f("fk_mcp_tool_call_org_id_actor_id_actor"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["org.id"], name=op.f("fk_mcp_tool_call_org_id_org")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_tool_call")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_mcp_tool_call_org_id_id")),
    )
    with op.batch_alter_table("mcp_tool_call", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mcp_tool_call_org_id"), ["org_id"], unique=False)
        batch_op.create_index("ix_mcp_tool_call_org_id_at", ["org_id", "at"], unique=False)
        batch_op.create_index("ix_mcp_tool_call_org_id_tool_at", ["org_id", "tool", "at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("mcp_tool_call", schema=None) as batch_op:
        batch_op.drop_index("ix_mcp_tool_call_org_id_tool_at")
        batch_op.drop_index("ix_mcp_tool_call_org_id_at")
        batch_op.drop_index(batch_op.f("ix_mcp_tool_call_org_id"))

    op.drop_table("mcp_tool_call")
    with op.batch_alter_table("mcp_tool_stat", schema=None) as batch_op:
        batch_op.drop_column("error_codes")
