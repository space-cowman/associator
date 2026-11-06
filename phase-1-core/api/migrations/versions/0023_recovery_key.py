"""Recovery key (phase 1b step C): approved devices and an encrypted history backup."""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE account_keys (
      user_id uuid PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
      public_key bytea NOT NULL CHECK (octet_length(public_key) = 32),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "ALTER TABLE devices ADD COLUMN approval bytea"
    " CHECK (approval IS NULL OR octet_length(approval) = 64)",
    "ALTER TABLE devices ADD COLUMN approved_at timestamptz",
    "ALTER TABLE devices ADD CHECK ((approval IS NULL) = (approved_at IS NULL))",
    """
    CREATE TABLE key_backups (
      user_id uuid PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
      version integer NOT NULL CHECK (version >= 1),
      blob bytea NOT NULL CHECK (octet_length(blob) BETWEEN 29 AND 10485760),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    f"REVOKE UPDATE ON account_keys FROM {APP_ROLE}",
    f"GRANT UPDATE (approval, approved_at) ON devices TO {APP_ROLE}",
    f"REVOKE UPDATE ON key_backups FROM {APP_ROLE}",
    f"GRANT UPDATE (version, blob, updated_at) ON key_backups TO {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE key_backups",
    "ALTER TABLE devices DROP COLUMN approved_at",
    "ALTER TABLE devices DROP COLUMN approval",
    "DROP TABLE account_keys",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
