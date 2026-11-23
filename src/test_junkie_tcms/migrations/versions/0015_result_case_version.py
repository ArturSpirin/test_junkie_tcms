"""result.case_version: the version of the case each attempt ran

Backfilled from the cycle case's pin: before this revision a pin could not move once a result existed,
so every existing result ran the version its cycle case still pins.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-22 18:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("result", schema=None) as batch_op:
        batch_op.add_column(sa.Column("case_version", sa.Integer(), nullable=True))

    op.execute(
        "UPDATE result SET case_version = (SELECT cc.case_version FROM cycle_case cc"
        " WHERE cc.org_id = result.org_id AND cc.id = result.cycle_case_id)"
    )

    with op.batch_alter_table("result", schema=None) as batch_op:
        batch_op.alter_column("case_version", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("result", schema=None) as batch_op:
        batch_op.drop_column("case_version")
