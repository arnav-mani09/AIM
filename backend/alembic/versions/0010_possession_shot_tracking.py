"""possession shot tracking fields

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-09 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("possession", sa.Column("shot_made", sa.Boolean(), nullable=True))
    op.add_column("possession", sa.Column("shot_zone", sa.String(), nullable=True))
    op.add_column("possession", sa.Column("shot_x", sa.Float(), nullable=True))
    op.add_column("possession", sa.Column("shot_y", sa.Float(), nullable=True))
    op.add_column("possession", sa.Column("shot_value", sa.Integer(), nullable=True))
    op.add_column(
        "possession",
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
    )
    op.add_column(
        "possession",
        sa.Column("review_status", sa.String(), nullable=False, server_default="confirmed"),
    )
    op.add_column("possession", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column("possession", sa.Column("reviewed_by_id", sa.Integer(), nullable=True))
    op.add_column("possession", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "possession",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("possession", sa.Column("updated_at", sa.DateTime(), nullable=True))

    op.create_foreign_key(
        "possession_created_by_id_fkey", "possession", "user", ["created_by_id"], ["id"]
    )
    op.create_foreign_key(
        "possession_reviewed_by_id_fkey", "possession", "user", ["reviewed_by_id"], ["id"]
    )
    op.create_index("ix_possession_game_review", "possession", ["game_id", "review_status"])
    op.create_check_constraint(
        "ck_possession_shot_value", "possession", "shot_value IS NULL OR shot_value IN (2,3)"
    )
    op.create_check_constraint(
        "ck_possession_source", "possession", "source IN ('manual','csv','ai')"
    )
    op.create_check_constraint(
        "ck_possession_review_status",
        "possession",
        "review_status IN ('pending','confirmed','rejected')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_possession_review_status", "possession", type_="check")
    op.drop_constraint("ck_possession_source", "possession", type_="check")
    op.drop_constraint("ck_possession_shot_value", "possession", type_="check")
    op.drop_index("ix_possession_game_review", table_name="possession")
    op.drop_constraint("possession_reviewed_by_id_fkey", "possession", type_="foreignkey")
    op.drop_constraint("possession_created_by_id_fkey", "possession", type_="foreignkey")
    for col in [
        "updated_at",
        "created_at",
        "reviewed_at",
        "reviewed_by_id",
        "created_by_id",
        "review_status",
        "source",
        "shot_value",
        "shot_y",
        "shot_x",
        "shot_zone",
        "shot_made",
    ]:
        op.drop_column("possession", col)
