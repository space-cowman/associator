"""End-to-end encrypted messages (phase 1b step B): devices, key packages, MLS message log."""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE devices (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      signature_key bytea NOT NULL UNIQUE CHECK (octet_length(signature_key) BETWEEN 32 AND 4096),
      created_at timestamptz NOT NULL DEFAULT now(),
      last_seen_at timestamptz NOT NULL DEFAULT now(),
      revoked_at timestamptz
    )
    """,
    "CREATE INDEX devices_user_idx ON devices (user_id) WHERE revoked_at IS NULL",
    """
    CREATE TABLE key_packages (
      id bigserial PRIMARY KEY,
      device_id uuid NOT NULL REFERENCES devices (id) ON DELETE CASCADE,
      key_package bytea NOT NULL CHECK (octet_length(key_package) BETWEEN 64 AND 16384),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX key_packages_device_idx ON key_packages (device_id, id)",
    """
    CREATE TABLE mls_messages (
      id bigserial PRIMARY KEY,
      conversation_id uuid NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
      sender_device_id uuid REFERENCES devices (id) ON DELETE SET NULL,
      kind text NOT NULL CHECK (kind IN ('app', 'commit', 'welcome')),
      epoch bigint NOT NULL CHECK (epoch >= 0),
      recipient_device_id uuid REFERENCES devices (id) ON DELETE CASCADE,
      body bytea NOT NULL CHECK (octet_length(body) BETWEEN 1 AND 262144),
      created_at timestamptz NOT NULL DEFAULT now(),
      CHECK ((kind = 'welcome') = (recipient_device_id IS NOT NULL))
    )
    """,
    "CREATE UNIQUE INDEX mls_messages_one_commit_per_epoch ON mls_messages (conversation_id, epoch)"
    " WHERE kind = 'commit'",
    "CREATE INDEX mls_messages_log_idx ON mls_messages (conversation_id, id)",
    "CREATE INDEX mls_messages_welcome_idx ON mls_messages (recipient_device_id)"
    " WHERE kind = 'welcome'",
    f"REVOKE UPDATE ON devices FROM {APP_ROLE}",
    f"GRANT UPDATE (last_seen_at, revoked_at) ON devices TO {APP_ROLE}",
    f"REVOKE UPDATE ON key_packages FROM {APP_ROLE}",
    f"REVOKE UPDATE, DELETE ON mls_messages FROM {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE mls_messages",
    "DROP TABLE key_packages",
    "DROP TABLE devices",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
