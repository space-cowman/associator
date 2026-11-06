"""Browser sessions for GitHub / Google sign-in: one refresh token per row, rotated on every use."""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE sessions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      family uuid NOT NULL,
      token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
      created_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz NOT NULL,
      used_at timestamptz,
      revoked_at timestamptz,
      CHECK (expires_at > created_at AND expires_at <= created_at + interval '31 days')
    )
    """,
    "CREATE INDEX sessions_family_idx ON sessions (family)",
    "CREATE INDEX sessions_user_idx ON sessions (user_id)",
    f"REVOKE UPDATE ON sessions FROM {APP_ROLE}",
    f"GRANT UPDATE (used_at, revoked_at) ON sessions TO {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = ("DROP TABLE sessions",)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
