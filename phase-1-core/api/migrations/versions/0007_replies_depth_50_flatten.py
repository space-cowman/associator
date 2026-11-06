"""Replies: max depth 8 -> 50 (owner decision); at the limit, replies flatten."""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX_DEPTH = 50

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE replies DROP CONSTRAINT replies_depth_check",
    "ALTER TABLE replies ADD CONSTRAINT replies_depth_check"
    f" CHECK (depth BETWEEN 0 AND {MAX_DEPTH})",
    "ALTER TABLE replies ADD COLUMN reply_to_id uuid",
    "ALTER TABLE replies ADD CONSTRAINT replies_reply_to_same_thread_fkey"
    " FOREIGN KEY (reply_to_id, thread_id) REFERENCES replies (id, thread_id)"
    " ON DELETE SET NULL (reply_to_id)",
    "ALTER TABLE replies ADD CONSTRAINT replies_reply_to_check"
    f" CHECK (reply_to_id IS NULL OR depth = {MAX_DEPTH})",
)

DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE replies DROP CONSTRAINT replies_reply_to_check",
    "ALTER TABLE replies DROP CONSTRAINT replies_reply_to_same_thread_fkey",
    "ALTER TABLE replies DROP COLUMN reply_to_id",
    "ALTER TABLE replies DROP CONSTRAINT replies_depth_check",
    "ALTER TABLE replies ADD CONSTRAINT replies_depth_check CHECK (depth BETWEEN 0 AND 8)",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
