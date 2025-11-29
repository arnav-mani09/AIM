"""create core tables

Revision ID: 0001
Revises:
Create Date: 2025-11-27

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=True),
    )

    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("team.id"), nullable=True),
    )

    op.create_index("ix_user_email", "user", ["email"], unique=True)

    op.create_table(
        "game",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("matchup", sa.String(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("home_team_id", sa.Integer(), sa.ForeignKey("team.id"), nullable=True),
        sa.Column("away_team_id", sa.Integer(), sa.ForeignKey("team.id"), nullable=True),
    )

    op.create_table(
        "player",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jersey_number", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("team.id"), nullable=True),
    )

    op.create_table(
        "possession",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("game.id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("player.id"), nullable=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=True),
    )

    op.create_table(
        "clip",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("game.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("storage_url", sa.String(), nullable=False),
        sa.Column("shared_with", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("clip")
    op.drop_table("possession")
    op.drop_table("player")
    op.drop_table("game")
    op.drop_index("ix_user_email")
    op.drop_table("user")
    op.drop_table("team")
