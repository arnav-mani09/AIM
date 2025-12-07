"""team clip uploads

Revision ID: 0004
Revises: 0003
Create Date: 2025-12-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("clip", "game_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("clip", sa.Column("team_id", sa.Integer(), nullable=True))
    op.add_column("clip", sa.Column("uploaded_by_id", sa.Integer(), nullable=True))
    op.add_column("clip", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("clip", sa.Column("status", sa.String(), nullable=False, server_default="pending"))
    op.add_column("clip", sa.Column("uploaded_at", sa.DateTime(), nullable=False, server_default=func.now()))
    op.create_foreign_key("clip_team_id_fkey", "clip", "team", ["team_id"], ["id"])
    op.create_foreign_key("clip_uploaded_by_id_fkey", "clip", "user", ["uploaded_by_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("clip_uploaded_by_id_fkey", "clip", type_="foreignkey")
    op.drop_constraint("clip_team_id_fkey", "clip", type_="foreignkey")
    op.drop_column("clip", "uploaded_at")
    op.drop_column("clip", "status")
    op.drop_column("clip", "notes")
    op.drop_column("clip", "uploaded_by_id")
    op.drop_column("clip", "team_id")
    op.alter_column("clip", "game_id", existing_type=sa.Integer(), nullable=False)
