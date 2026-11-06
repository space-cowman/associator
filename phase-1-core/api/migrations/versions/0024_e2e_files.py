"""Encrypted files in private chats (phase 1b step D)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE e2e_files (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      conversation_id uuid NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
      uploader_id uuid REFERENCES users (id) ON DELETE SET NULL,
      size_bytes integer NOT NULL CHECK (size_bytes BETWEEN 17 AND 26214416),
      status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'stored')),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX e2e_files_conversation_idx ON e2e_files (conversation_id)",
    f"REVOKE UPDATE ON e2e_files FROM {APP_ROLE}",
    f"GRANT UPDATE (status) ON e2e_files TO {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = ("DROP TABLE e2e_files",)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
