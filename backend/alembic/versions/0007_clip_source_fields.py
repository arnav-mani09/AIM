"""clip source metadata

Revision ID: 0007
Revises: 0006
Create Date: 2025-12-06

"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clip", sa.Column("source_upload_id", sa.Integer(), nullable=True))
    op.add_column("clip", sa.Column("source_start_second", sa.Integer(), nullable=True))
    op.add_column("clip", sa.Column("source_end_second", sa.Integer(), nullable=True))
    op.create_foreign_key("clip_source_upload_id_fkey", "clip", "game_upload", ["source_upload_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("clip_source_upload_id_fkey", "clip", type_="foreignkey")
    op.drop_column("clip", "source_end_second")
    op.drop_column("clip", "source_start_second")
    op.drop_column("clip", "source_upload_id")
