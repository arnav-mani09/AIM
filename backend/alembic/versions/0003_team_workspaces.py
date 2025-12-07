"""team workspace structures

Revision ID: 0003
Revises: 0002
Create Date: 2025-12-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("team", sa.Column("season_label", sa.String(), nullable=True))
    op.add_column("team", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column("team", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=func.now()))
    op.create_foreign_key("fk_team_created_by", "team", "user", ["created_by_id"], ["id"])

    op.drop_constraint("user_team_id_fkey", "user", type_="foreignkey")
    op.drop_column("user", "team_id")

    op.create_table(
        "team_membership",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("team.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=func.now()),
    )
    op.create_unique_constraint("uq_team_membership_team_user", "team_membership", ["team_id", "user_id"])

    op.create_table(
        "team_invite",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("team.id"), nullable=False),
        sa.Column("code", sa.String(), nullable=False, unique=True),
        sa.Column("role", sa.String(), nullable=False, server_default="member"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_team_invite_code", "team_invite", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_team_invite_code", table_name="team_invite")
    op.drop_table("team_invite")
    op.drop_constraint("uq_team_membership_team_user", "team_membership", type_="unique")
    op.drop_table("team_membership")

    op.add_column("user", sa.Column("team_id", sa.Integer(), nullable=True))
    op.create_foreign_key("user_team_id_fkey", "user", "team", ["team_id"], ["id"])

    op.drop_constraint("fk_team_created_by", "team", type_="foreignkey")
    op.drop_column("team", "created_at")
    op.drop_column("team", "created_by_id")
    op.drop_column("team", "season_label")
