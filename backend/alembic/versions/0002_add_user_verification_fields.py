"""add user verification fields

Revision ID: 0002
Revises: 0001
Create Date: 2025-11-27

"""
from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user", sa.Column("verification_token", sa.String(), nullable=True))
    op.add_column("user", sa.Column("verification_sent_at", sa.DateTime(), nullable=True))
    op.create_index("ix_user_verification_token", "user", ["verification_token"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_verification_token", table_name="user")
    op.drop_column("user", "verification_sent_at")
    op.drop_column("user", "verification_token")
    op.drop_column("user", "is_verified")
