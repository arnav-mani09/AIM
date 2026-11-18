"""Background direct-download film imports."""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("game_upload", sa.Column("import_job_id", sa.String(), nullable=True))
    op.add_column("game_upload", sa.Column("import_started_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_upload", "import_started_at")
    op.drop_column("game_upload", "import_job_id")
