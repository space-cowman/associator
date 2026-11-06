"""Private clusters and one-to-one chats (phase 1b step A: people and membership, no messages)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE conversations (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      kind text NOT NULL CHECK (kind IN ('cluster', 'direct')),
      name text CHECK (
        name IS NULL OR (char_length(name) BETWEEN 1 AND 60 AND name = btrim(name)
                         AND name !~ '[[:cntrl:]]')
      ),
      created_by uuid REFERENCES users (id) ON DELETE SET NULL,
      ai_enabled boolean NOT NULL DEFAULT true,
      direct_low uuid REFERENCES users (id) ON DELETE CASCADE,
      direct_high uuid REFERENCES users (id) ON DELETE CASCADE,
      created_at timestamptz NOT NULL DEFAULT now(),
      CHECK ((kind = 'cluster') = (name IS NOT NULL)),
      CHECK ((kind = 'direct') = (direct_low IS NOT NULL AND direct_high IS NOT NULL)),
      CHECK (direct_low IS NULL OR direct_low < direct_high),
      UNIQUE (direct_low, direct_high)
    )
    """,
    """
    CREATE TABLE conversation_members (
      conversation_id uuid NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
      user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      role text NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
      state text NOT NULL CHECK (state IN ('invited', 'active', 'left')),
      invited_by uuid REFERENCES users (id) ON DELETE SET NULL,
      invited_at timestamptz NOT NULL DEFAULT now(),
      joined_at timestamptz,
      PRIMARY KEY (conversation_id, user_id),
      CHECK (state <> 'active' OR joined_at IS NOT NULL)
    )
    """,
    "CREATE INDEX conversation_members_user_idx ON conversation_members (user_id, state)",
    """
    CREATE TABLE blocks (
      blocker_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      blocked_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (blocker_id, blocked_id),
      CHECK (blocker_id <> blocked_id)
    )
    """,
    f"REVOKE UPDATE ON conversations FROM {APP_ROLE}",
    f"GRANT UPDATE (name, ai_enabled) ON conversations TO {APP_ROLE}",
    f"REVOKE UPDATE ON conversation_members FROM {APP_ROLE}",
    f"GRANT UPDATE (role, state, invited_by, invited_at, joined_at)"
    f" ON conversation_members TO {APP_ROLE}",
    f"REVOKE UPDATE ON blocks FROM {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE blocks",
    "DROP TABLE conversation_members",
    "DROP TABLE conversations",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
