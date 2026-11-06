"""Initial schema: users, clusters, questions, replies, drafts, votes, models."""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE users (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      handle text NOT NULL UNIQUE CHECK (handle ~ '^[a-z0-9-]{3,30}$'),
      auth_provider text NOT NULL CHECK (auth_provider IN ('google', 'github')),
      provider_user_id_hash text NOT NULL,
      email_hash text,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (auth_provider, provider_user_id_hash)
    )
    """,
    """
    CREATE TABLE topic_groups (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]{2,40}$'),
      name text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE threads (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      group_id uuid NOT NULL REFERENCES topic_groups (id),
      author_id uuid REFERENCES users (id) ON DELETE SET NULL,
      type text NOT NULL CHECK (type IN ('question', 'opinion', 'observation', 'showcase')),
      text text NOT NULL CHECK (char_length(text) BETWEEN 1 AND 500),
      satisfied_reply_id uuid,
      created_at timestamptz NOT NULL DEFAULT now(),
      search tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
    )
    """,
    "CREATE INDEX threads_search_idx ON threads USING gin (search)",
    "CREATE INDEX threads_group_created_idx ON threads (group_id, created_at DESC)",
    """
    CREATE TABLE replies (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      thread_id uuid NOT NULL REFERENCES threads (id) ON DELETE CASCADE,
      parent_id uuid REFERENCES replies (id) ON DELETE CASCADE,
      author_id uuid REFERENCES users (id) ON DELETE SET NULL,
      text text NOT NULL CHECK (char_length(text) BETWEEN 1 AND 500),
      mode text NOT NULL CHECK (mode IN ('self', 'ask_my_ai', 'platform_ai')),
      model_label text,
      memory_used boolean NOT NULL DEFAULT false,
      instruction_given boolean NOT NULL DEFAULT false,
      human_approved boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX replies_thread_idx ON replies (thread_id, created_at)",
    """
    ALTER TABLE threads ADD CONSTRAINT threads_satisfied_reply_fk
      FOREIGN KEY (satisfied_reply_id) REFERENCES replies (id) ON DELETE SET NULL
    """,
    """
    CREATE TABLE sub_blocks (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      owner_type text NOT NULL CHECK (owner_type IN ('thread', 'reply', 'draft')),
      owner_id uuid NOT NULL,
      kind text NOT NULL CHECK (kind IN ('code', 'logs', 'steps')),
      content text NOT NULL CHECK (char_length(content) <= 2000),
      flags jsonb NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX sub_blocks_owner_idx ON sub_blocks (owner_type, owner_id)",
    """
    CREATE TABLE drafts (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      thread_id uuid NOT NULL REFERENCES threads (id) ON DELETE CASCADE,
      parent_id uuid REFERENCES replies (id) ON DELETE CASCADE,
      user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'discarded')),
      mode text NOT NULL CHECK (mode IN ('ask_my_ai', 'platform_ai')),
      text text NOT NULL CHECK (char_length(text) BETWEEN 1 AND 500),
      instruction text,
      model_label text,
      safety_report jsonb NOT NULL DEFAULT '{}',
      idempotency_key text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      decided_at timestamptz,
      UNIQUE (user_id, idempotency_key)
    )
    """,
    "CREATE INDEX drafts_user_status_idx ON drafts (user_id, status)",
    """
    CREATE TABLE votes (
      reply_id uuid NOT NULL REFERENCES replies (id) ON DELETE CASCADE,
      voter_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      voter_type text NOT NULL CHECK (voter_type IN ('human', 'agent')),
      value smallint NOT NULL CHECK (value IN (-1, 1)),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (reply_id, voter_id, voter_type)
    )
    """,
    """
    CREATE TABLE model_registry (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      provider text NOT NULL
        CHECK (provider IN ('openai', 'anthropic', 'gemini', 'openrouter', 'platform')),
      model_name text NOT NULL,
      key_ciphertext bytea,
      key_last4 text,
      enabled boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX model_registry_user_idx ON model_registry (user_id)",
)

DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE model_registry",
    "DROP TABLE votes",
    "DROP TABLE drafts",
    "DROP TABLE sub_blocks",
    "ALTER TABLE threads DROP CONSTRAINT threads_satisfied_reply_fk",
    "DROP TABLE replies",
    "DROP TABLE threads",
    "DROP TABLE topic_groups",
    "DROP TABLE users",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
