"""case_position: a case's index among the cases of its feature, for manual order

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
    with op.batch_alter_table("test_case", schema=None) as batch_op:
        batch_op.add_column(sa.Column("position", sa.Integer(), server_default="0", nullable=False))
    # Existing cases keep their key order within each feature. Leaves updated_at as it was.
    op.execute(
        "UPDATE test_case SET position = (SELECT COUNT(*) FROM test_case t2"
        " WHERE t2.org_id = test_case.org_id AND t2.feature_id = test_case.feature_id"
        " AND t2.number < test_case.number)"
    )


def downgrade() -> None:
    with op.batch_alter_table("test_case", schema=None) as batch_op:
        batch_op.drop_column("position")
