"""Questions: read-only for the app except Satisfied; text checked; paging index."""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"
BAD_CHARS = r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f‪-‮⁦-⁩]"

UPGRADE: tuple[str, ...] = (
    f"REVOKE UPDATE, DELETE ON threads FROM {APP_ROLE}",
    f"GRANT UPDATE (satisfied_reply_id) ON threads TO {APP_ROLE}",
    "ALTER TABLE threads ADD CONSTRAINT threads_text_chars_check"
    f" CHECK (text = btrim(text) AND text !~ '{BAD_CHARS}')",
    "DROP INDEX threads_group_created_idx",
    "CREATE INDEX threads_group_created_idx ON threads (group_id, created_at DESC, id DESC)",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP INDEX threads_group_created_idx",
    "CREATE INDEX threads_group_created_idx ON threads (group_id, created_at DESC)",
    "ALTER TABLE threads DROP CONSTRAINT threads_text_chars_check",
    f"GRANT UPDATE, DELETE ON threads TO {APP_ROLE}",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
