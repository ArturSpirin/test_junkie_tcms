"""actor last_active_at and description; case_version via, token and on-behalf-of

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-22 20:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("actor", schema=None) as batch_op:
        batch_op.add_column(sa.Column("description", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("case_version", schema=None) as batch_op:
        batch_op.add_column(sa.Column("via", sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column("token_id", sa.String(length=26), nullable=True))
        batch_op.add_column(sa.Column("on_behalf_of_user_id", sa.String(length=26), nullable=True))
        batch_op.create_check_constraint(
            batch_op.f("ck_case_version_via"), "via IS NULL OR via IN ('ui', 'api', 'mcp')"
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_case_version_org_id_token_id_api_token"),
            "api_token",
            ["org_id", "token_id"],
            ["org_id", "id"],
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_case_version_org_id_on_behalf_of_user_id_membership"),
            "membership",
            ["org_id", "on_behalf_of_user_id"],
            ["org_id", "user_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("case_version", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_case_version_org_id_on_behalf_of_user_id_membership"), type_="foreignkey"
        )
        batch_op.drop_constraint(batch_op.f("fk_case_version_org_id_token_id_api_token"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("ck_case_version_via"), type_="check")
        batch_op.drop_column("on_behalf_of_user_id")
        batch_op.drop_column("token_id")
        batch_op.drop_column("via")

    with op.batch_alter_table("actor", schema=None) as batch_op:
        batch_op.drop_column("last_active_at")
        batch_op.drop_column("description")
