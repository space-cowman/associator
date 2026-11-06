"""Reports from private chats (phase 1b step F)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE reports (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      reporter_id uuid REFERENCES users (id) ON DELETE SET NULL,
      conversation_id uuid REFERENCES conversations (id) ON DELETE SET NULL,
      reported_handle text CHECK (reported_handle ~ '^[a-z0-9-]{3,30}$'),
      reason text NOT NULL CHECK (reason IN
        ('spam', 'harassment', 'hate', 'sexual', 'violence', 'self_harm', 'illegal', 'other')),
      details text CHECK (char_length(details) <= 1000),
      content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'array'
        AND jsonb_array_length(content) BETWEEN 1 AND 20),
      status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'actioned', 'dismissed')),
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX reports_open_idx ON reports (created_at) WHERE status = 'open'",
    f"REVOKE SELECT, UPDATE, DELETE ON reports FROM {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = ("DROP TABLE reports",)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
