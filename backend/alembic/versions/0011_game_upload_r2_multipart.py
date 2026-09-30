"""track R2 multipart uploads on game uploads

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-30 02:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_upload", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("game_upload", sa.Column("storage_upload_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_upload", "storage_upload_id")
    op.drop_column("game_upload", "size_bytes")
