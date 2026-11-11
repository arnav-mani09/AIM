"""drafted shot events per upload, and the event job on game_upload

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-11 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPLOAD_COLUMNS = (
    ("events_status", sa.String()),
    ("events_job_id", sa.String()),
    ("events_error", sa.Text()),
    ("events_started_at", sa.DateTime()),
    ("events_url", sa.String()),
    ("events_info", sa.JSON()),
    ("valley_jersey", sa.String()),
    ("opponent_jersey", sa.String()),
)


def upgrade() -> None:
    for name, kind in UPLOAD_COLUMNS:
        op.add_column("game_upload", sa.Column(name, kind, nullable=True))
    op.create_table(
        "shot_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("upload_id", sa.Integer(), sa.ForeignKey("game_upload.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(), nullable=False, server_default="shot"),
        sa.Column("t", sa.Float(), nullable=False),
        sa.Column("team", sa.String(), nullable=False),
        sa.Column("shot_type", sa.String(), nullable=False),
        sa.Column("made", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("player_number", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("original", sa.JSON(), nullable=True),
        sa.Column("rim", sa.JSON(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_shot_event_id", "shot_event", ["id"])
    op.create_index("ix_shot_event_upload_id", "shot_event", ["upload_id"])


def downgrade() -> None:
    op.drop_index("ix_shot_event_upload_id", table_name="shot_event")
    op.drop_index("ix_shot_event_id", table_name="shot_event")
    op.drop_table("shot_event")
    for name, _ in reversed(UPLOAD_COLUMNS):
        op.drop_column("game_upload", name)
