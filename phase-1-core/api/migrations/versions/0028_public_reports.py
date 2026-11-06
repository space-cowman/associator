"""Reports on public questions and replies (IT Rules 2021 grievance handling)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE reports ADD COLUMN thread_id uuid REFERENCES threads (id) ON DELETE SET NULL",
    "ALTER TABLE reports ADD COLUMN reply_id uuid REFERENCES replies (id) ON DELETE SET NULL",
    "CREATE UNIQUE INDEX reports_once_per_thread ON reports (reporter_id, thread_id)"
    " WHERE thread_id IS NOT NULL AND reply_id IS NULL",
    "CREATE UNIQUE INDEX reports_once_per_reply ON reports (reporter_id, reply_id)"
    " WHERE reply_id IS NOT NULL",
)
DOWNGRADE: tuple[str, ...] = (
    "DROP INDEX reports_once_per_reply",
    "DROP INDEX reports_once_per_thread",
    "ALTER TABLE reports DROP COLUMN reply_id",
    "ALTER TABLE reports DROP COLUMN thread_id",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
