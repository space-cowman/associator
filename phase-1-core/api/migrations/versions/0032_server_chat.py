"""Private chats stored by the server, encrypted at rest."""

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    "DROP TABLE IF EXISTS e2e_files",
    "DROP TABLE IF EXISTS mls_messages",
    "DROP TABLE IF EXISTS key_packages",
    "DROP TABLE IF EXISTS key_backups",
    "DROP TABLE IF EXISTS account_keys",
    "DROP TABLE IF EXISTS devices",
    """
    CREATE TABLE conversation_keys (
      conversation_id uuid PRIMARY KEY REFERENCES conversations (id) ON DELETE CASCADE,
      key_ciphertext bytea NOT NULL CHECK (octet_length(key_ciphertext) BETWEEN 16 AND 4096),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    f"REVOKE UPDATE, DELETE ON conversation_keys FROM {APP_ROLE}",
    """
    CREATE TABLE chat_messages (
      id bigserial PRIMARY KEY,
      conversation_id uuid NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
      sender_id uuid REFERENCES users (id) ON DELETE SET NULL,
      kind text NOT NULL CHECK (kind IN ('text', 'ask', 'ai')),
      body_sealed bytea CHECK (octet_length(body_sealed) BETWEEN 29 AND 65536),
      attachment_id uuid REFERENCES attachments (id) ON DELETE SET NULL,
      meta jsonb NOT NULL DEFAULT '{}',
      created_at timestamptz NOT NULL DEFAULT now(),
      CHECK (body_sealed IS NOT NULL OR attachment_id IS NOT NULL)
    )
    """,
    "CREATE INDEX chat_messages_log_idx ON chat_messages (conversation_id, id)",
    f"REVOKE UPDATE, DELETE ON chat_messages FROM {APP_ROLE}",
    "ALTER TABLE attachments ADD COLUMN conversation_id uuid"
    " REFERENCES conversations (id) ON DELETE CASCADE",
    "ALTER TABLE attachments ADD CONSTRAINT attachments_chat_or_post_check"
    " CHECK (conversation_id IS NULL OR (thread_id IS NULL AND reply_id IS NULL))",
    "CREATE INDEX attachments_conversation_idx ON attachments (conversation_id)"
    " WHERE conversation_id IS NOT NULL",
    f"GRANT UPDATE (conversation_id) ON attachments TO {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE attachments DROP COLUMN conversation_id",
    "DROP TABLE chat_messages",
    "DROP TABLE conversation_keys",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
