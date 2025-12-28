"""add clip possession link

Revision ID: 0008
Revises: 0007
Create Date: 2025-12-06 07:33:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("possession", sa.Column("video_start_second", sa.Integer(), nullable=True))
    op.add_column("possession", sa.Column("video_end_second", sa.Integer(), nullable=True))
    op.create_table(
        "clip_possession_link",
        sa.Column("clip_id", sa.Integer(), nullable=False),
        sa.Column("possession_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["clip_id"], ["clip.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["possession_id"], ["possession.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("clip_id", "possession_id"),
    )


def downgrade() -> None:
    op.drop_table("clip_possession_link")
    op.drop_column("possession", "video_end_second")
    op.drop_column("possession", "video_start_second")
