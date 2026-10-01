"""track when processing started and how many attempts it took

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-01 02:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_upload", sa.Column("processing_started_at", sa.DateTime(), nullable=True))
    op.add_column("game_upload", sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("game_upload", "processing_attempts")
    op.drop_column("game_upload", "processing_started_at")
