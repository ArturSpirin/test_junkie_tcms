"""invites: emailed invites to join an org

Revision ID: 0004_invites
Revises: 0003
Create Date: 2026-11-14 11:20:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_invites"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invite",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_actor_id", sa.String(length=26), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", sa.String(length=26), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("org_id", sa.String(length=26), nullable=False),
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('viewer', 'tester', 'editor', 'admin', 'owner')", name=op.f("ck_invite_role")
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "accepted_user_id"],
            ["membership.org_id", "membership.user_id"],
            name=op.f("fk_invite_org_id_accepted_user_id_membership"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "invited_by_actor_id"],
            ["actor.org_id", "actor.id"],
            name=op.f("fk_invite_org_id_invited_by_actor_id_actor"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["org.id"], name=op.f("fk_invite_org_id_org")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invite")),
        sa.UniqueConstraint("org_id", "id", name=op.f("uq_invite_org_id_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invite_token_hash")),
    )
    with op.batch_alter_table("invite", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_invite_email"), ["email"], unique=False)
        batch_op.create_index(batch_op.f("ix_invite_org_id"), ["org_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("invite", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invite_org_id"))
        batch_op.drop_index(batch_op.f("ix_invite_email"))

    op.drop_table("invite")
