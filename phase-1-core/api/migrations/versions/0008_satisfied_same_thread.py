"""Satisfied mark: the chosen reply must belong to the same thread (enforced by the database)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE threads DROP CONSTRAINT threads_satisfied_reply_fk",
    "ALTER TABLE threads ADD CONSTRAINT threads_satisfied_reply_same_thread_fkey"
    " FOREIGN KEY (satisfied_reply_id, id) REFERENCES replies (id, thread_id)"
    " ON DELETE SET NULL (satisfied_reply_id)",
)

DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE threads DROP CONSTRAINT threads_satisfied_reply_same_thread_fkey",
    "ALTER TABLE threads ADD CONSTRAINT threads_satisfied_reply_fk"
    " FOREIGN KEY (satisfied_reply_id) REFERENCES replies (id) ON DELETE SET NULL",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
