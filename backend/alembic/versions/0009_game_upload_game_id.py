"""link game uploads to games

Revision ID: 0009
Revises: 0008
Create Date: 2025-12-11 04:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_upload", sa.Column("game_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "game_upload_game_id_fkey",
        "game_upload",
        "game",
        ["game_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("game_upload_game_id_fkey", "game_upload", type_="foreignkey")
    op.drop_column("game_upload", "game_id")
