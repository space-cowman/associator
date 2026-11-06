"""Replies: read-only for the app, text checked, AI replies only when approved."""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"
BAD_CHARS = r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f‪-‮⁦-⁩]"
MAX_DEPTH = 8

UPGRADE: tuple[str, ...] = (
    f"REVOKE UPDATE, DELETE ON replies FROM {APP_ROLE}",
    "ALTER TABLE replies ADD CONSTRAINT replies_text_chars_check"
    f" CHECK (text = btrim(text) AND text !~ '{BAD_CHARS}')",
    "ALTER TABLE replies ADD CONSTRAINT replies_ai_approved_check"
    " CHECK (mode = 'self' OR human_approved)",
    "ALTER TABLE replies ADD COLUMN depth smallint NOT NULL DEFAULT 0"
    f" CONSTRAINT replies_depth_check CHECK (depth BETWEEN 0 AND {MAX_DEPTH})",
    "ALTER TABLE replies ADD CONSTRAINT replies_id_thread_key UNIQUE (id, thread_id)",
    "ALTER TABLE replies DROP CONSTRAINT replies_parent_id_fkey",
    "ALTER TABLE replies ADD CONSTRAINT replies_parent_same_thread_fkey"
    " FOREIGN KEY (parent_id, thread_id) REFERENCES replies (id, thread_id) ON DELETE CASCADE",
    "DROP INDEX replies_thread_idx",
    "CREATE INDEX replies_thread_idx ON replies (thread_id, created_at, id)",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP INDEX replies_thread_idx",
    "CREATE INDEX replies_thread_idx ON replies (thread_id, created_at)",
    "ALTER TABLE replies DROP CONSTRAINT replies_parent_same_thread_fkey",
    "ALTER TABLE replies ADD CONSTRAINT replies_parent_id_fkey"
    " FOREIGN KEY (parent_id) REFERENCES replies (id) ON DELETE CASCADE",
    "ALTER TABLE replies DROP CONSTRAINT replies_id_thread_key",
    "ALTER TABLE replies DROP COLUMN depth",
    "ALTER TABLE replies DROP CONSTRAINT replies_ai_approved_check",
    "ALTER TABLE replies DROP CONSTRAINT replies_text_chars_check",
    f"GRANT UPDATE, DELETE ON replies TO {APP_ROLE}",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
