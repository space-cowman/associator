"""Cluster membership and notifications."""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE group_members (
      group_id uuid NOT NULL REFERENCES topic_groups (id) ON DELETE CASCADE,
      user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      joined_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (group_id, user_id)
    )
    """,
    "CREATE INDEX group_members_user_idx ON group_members (user_id)",
    f"REVOKE UPDATE ON group_members FROM {APP_ROLE}",
    """
    CREATE TABLE notifications (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      kind text NOT NULL CHECK (kind IN ('reply', 'satisfied')),
      thread_id uuid NOT NULL REFERENCES threads (id) ON DELETE CASCADE,
      reply_id uuid REFERENCES replies (id) ON DELETE CASCADE,
      actor_id uuid REFERENCES users (id) ON DELETE SET NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      read_at timestamptz
    )
    """,
    "CREATE INDEX notifications_user_idx ON notifications (user_id, created_at DESC)",
    f"REVOKE UPDATE, DELETE ON notifications FROM {APP_ROLE}",
    f"GRANT UPDATE (read_at) ON notifications TO {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE notifications",
    "DROP TABLE group_members",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
