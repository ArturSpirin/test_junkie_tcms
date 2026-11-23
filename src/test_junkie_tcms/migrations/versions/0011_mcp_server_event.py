"""mcp_server_event: MCP server starts and tool-list changes, server-wide

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-22 18:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_server_event",
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("tool_list_hash", sa.String(length=64), nullable=False),
        sa.Column("tool_hashes", sa.JSON(), nullable=False),
        sa.Column("added", sa.JSON(), nullable=False),
        sa.Column("removed", sa.JSON(), nullable=False),
        sa.Column("changed", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('server_started', 'tools_changed')", name=op.f("ck_mcp_server_event_kind")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mcp_server_event")),
    )
    with op.batch_alter_table("mcp_server_event", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mcp_server_event_at"), ["at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("mcp_server_event", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mcp_server_event_at"))

    op.drop_table("mcp_server_event")
