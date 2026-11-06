"""Votes on questions (human and agent separate, like replies) and a short group description."""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE thread_votes (
      thread_id uuid NOT NULL REFERENCES threads (id) ON DELETE CASCADE,
      voter_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      voter_type text NOT NULL CHECK (voter_type IN ('human', 'agent')),
      value smallint NOT NULL CHECK (value IN (-1, 1)),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (thread_id, voter_id, voter_type)
    )
    """,
    f"REVOKE UPDATE ON thread_votes FROM {APP_ROLE}",
    f"GRANT UPDATE (value) ON thread_votes TO {APP_ROLE}",
    "ALTER TABLE topic_groups ADD COLUMN description text"
    " CONSTRAINT topic_groups_description_check"
    " CHECK (description IS NULL OR (char_length(description) BETWEEN 1 AND 200"
    " AND description = btrim(description) AND description !~ '[[:cntrl:]]'))",
)

DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE topic_groups DROP COLUMN description",
    "DROP TABLE thread_votes",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
