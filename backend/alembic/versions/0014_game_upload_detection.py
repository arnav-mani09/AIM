"""player detection job and its tracks file

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-03 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_upload", sa.Column("detection_status", sa.String(), nullable=True))
    op.add_column("game_upload", sa.Column("detection_job_id", sa.String(), nullable=True))
    op.add_column("game_upload", sa.Column("detection_error", sa.Text(), nullable=True))
    op.add_column("game_upload", sa.Column("detection_started_at", sa.DateTime(), nullable=True))
    op.add_column("game_upload", sa.Column("detection_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("game_upload", sa.Column("detection_model", sa.String(), nullable=True))
    op.add_column("game_upload", sa.Column("tracks_url", sa.String(), nullable=True))


def downgrade() -> None:
    for column in ("tracks_url", "detection_model", "detection_attempts", "detection_started_at",
                   "detection_error", "detection_job_id", "detection_status"):
        op.drop_column("game_upload", column)
