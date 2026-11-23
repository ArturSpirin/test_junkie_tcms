"""case_version.description: a case's Description, versioned like its preconditions

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

# Existing versions get the empty document, the same value cases_create stores when none is given.
EMPTY_DOC = '{"type": "doc", "content": []}'


def upgrade() -> None:
    with op.batch_alter_table("case_version", schema=None) as batch_op:
        batch_op.add_column(sa.Column("description", sa.JSON(), server_default=EMPTY_DOC, nullable=False))
        batch_op.add_column(sa.Column("description_text", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("case_version", schema=None) as batch_op:
        batch_op.drop_column("description_text")
        batch_op.drop_column("description")
