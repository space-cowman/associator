"""Formatted text in one field, and file attachments on posts."""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"
MAX_BYTES = 25 * 1024 * 1024

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE threads DROP COLUMN type",
    "DROP TABLE sub_blocks",
    "ALTER TABLE threads ADD COLUMN warnings text[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE replies ADD COLUMN warnings text[] NOT NULL DEFAULT '{}'",
    f"""
    CREATE TABLE attachments (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      kind text NOT NULL CHECK (kind IN ('image', 'video', 'pdf', 'text')),
      content_type text NOT NULL CHECK (content_type IN (
        'image/png', 'image/jpeg', 'image/webp', 'image/gif',
        'video/mp4', 'video/webm', 'application/pdf', 'text/plain')),
      size_bytes integer NOT NULL CHECK (size_bytes BETWEEN 1 AND {MAX_BYTES}),
      filename text NOT NULL CHECK (filename ~ '^[A-Za-z0-9 ._()-]{{1,120}}$'),
      status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'ready', 'rejected')),
      thread_id uuid REFERENCES threads (id) ON DELETE CASCADE,
      reply_id uuid REFERENCES replies (id) ON DELETE CASCADE,
      position smallint CHECK (position BETWEEN 0 AND 3),
      created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT attachments_one_post_check CHECK (thread_id IS NULL OR reply_id IS NULL),
      CONSTRAINT attachments_linked_ready_check
        CHECK ((thread_id IS NULL AND reply_id IS NULL) OR status = 'ready')
    )
    """,
    "CREATE INDEX attachments_thread_idx ON attachments (thread_id) WHERE thread_id IS NOT NULL",
    "CREATE INDEX attachments_reply_idx ON attachments (reply_id) WHERE reply_id IS NOT NULL",
    "CREATE INDEX attachments_owner_idx ON attachments (owner_id, created_at)",
    f"REVOKE UPDATE, DELETE ON attachments FROM {APP_ROLE}",
    f"GRANT UPDATE (status, thread_id, reply_id, position) ON attachments TO {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE attachments",
    "ALTER TABLE replies DROP COLUMN warnings",
    "ALTER TABLE threads DROP COLUMN warnings",
    "ALTER TABLE threads ADD COLUMN type text NOT NULL DEFAULT 'question'"
    " CHECK (type IN ('question', 'opinion', 'observation', 'showcase'))",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
