"""AI app access: tokens, questions from agents, answers that wait for approval."""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE access_tokens (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      name text NOT NULL CHECK (name ~ '^[A-Za-z0-9 ._-]{1,40}$'),
      token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
      token_last4 text NOT NULL CHECK (char_length(token_last4) = 4),
      created_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL,
      last_used_at timestamptz,
      revoked_at timestamptz
    )
    """,
    "CREATE INDEX access_tokens_user_idx ON access_tokens (user_id)",
    f"REVOKE UPDATE, DELETE ON access_tokens FROM {APP_ROLE}",
    f"GRANT UPDATE (last_used_at, revoked_at) ON access_tokens TO {APP_ROLE}",
    "ALTER TABLE threads ADD COLUMN by_agent boolean NOT NULL DEFAULT false",
    "ALTER TABLE threads ADD COLUMN deleted_at timestamptz",
    f"GRANT UPDATE (deleted_at) ON threads TO {APP_ROLE}",
    "ALTER TABLE drafts DROP CONSTRAINT drafts_mode_check",
    "ALTER TABLE drafts ADD CONSTRAINT drafts_mode_check"
    " CHECK (mode IN ('ask_my_ai', 'platform_ai', 'mcp'))",
    "ALTER TABLE replies DROP CONSTRAINT replies_mode_check",
    "ALTER TABLE replies ADD CONSTRAINT replies_mode_check"
    " CHECK (mode IN ('self', 'ask_my_ai', 'platform_ai', 'mcp'))",
)

DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE replies DROP CONSTRAINT replies_mode_check",
    "ALTER TABLE replies ADD CONSTRAINT replies_mode_check"
    " CHECK (mode IN ('self', 'ask_my_ai', 'platform_ai'))",
    "ALTER TABLE drafts DROP CONSTRAINT drafts_mode_check",
    "ALTER TABLE drafts ADD CONSTRAINT drafts_mode_check"
    " CHECK (mode IN ('ask_my_ai', 'platform_ai'))",
    f"REVOKE UPDATE (deleted_at) ON threads FROM {APP_ROLE}",
    "ALTER TABLE threads DROP COLUMN deleted_at",
    "ALTER TABLE threads DROP COLUMN by_agent",
    "DROP TABLE access_tokens",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
