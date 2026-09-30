"""track the Modal proxy job and its outputs on game uploads

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-30 04:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_upload", sa.Column("proxy_url", sa.String(), nullable=True))
    op.add_column("game_upload", sa.Column("thumbnail_url", sa.String(), nullable=True))
    op.add_column("game_upload", sa.Column("processing_job_id", sa.String(), nullable=True))
    op.add_column("game_upload", sa.Column("processing_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_upload", "processing_error")
    op.drop_column("game_upload", "processing_job_id")
    op.drop_column("game_upload", "thumbnail_url")
    op.drop_column("game_upload", "proxy_url")
