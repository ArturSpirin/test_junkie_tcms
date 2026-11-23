"""product owner; cycle eta and order

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-23 04:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("product", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_actor_id", sa.String(length=26), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_product_org_id_owner_actor_id_actor"),
            "actor",
            ["org_id", "owner_actor_id"],
            ["org_id", "id"],
        )

    with op.batch_alter_table("cycle", schema=None) as batch_op:
        batch_op.add_column(sa.Column("order", sa.String(length=10), server_default="source", nullable=False))
        batch_op.add_column(sa.Column("eta", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            batch_op.f("ck_cycle_order"), "\"order\" IN ('source', 'feature', 'priority', 'manual')"
        )


def downgrade() -> None:
    with op.batch_alter_table("cycle", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_cycle_order"), type_="check")
        batch_op.drop_column("eta")
        batch_op.drop_column("order")

    with op.batch_alter_table("product", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_product_org_id_owner_actor_id_actor"), type_="foreignkey")
        batch_op.drop_column("owner_actor_id")
