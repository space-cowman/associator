"""At most one pending draft per person per question."""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE: tuple[str, ...] = (
    """
    UPDATE drafts d SET status = 'discarded', decided_at = now()
    WHERE d.status = 'pending' AND EXISTS (
      SELECT 1 FROM drafts n
      WHERE n.user_id = d.user_id AND n.thread_id = d.thread_id AND n.status = 'pending'
        AND (n.created_at, n.id) > (d.created_at, d.id))
    """,
    "CREATE UNIQUE INDEX drafts_one_pending_per_thread ON drafts (user_id, thread_id)"
    " WHERE status = 'pending'",
)

DOWNGRADE: tuple[str, ...] = ("DROP INDEX drafts_one_pending_per_thread",)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
