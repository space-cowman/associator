"""Memory for Ask my AI (Phase 2): what a person's AI knows about them, encrypted."""

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE memory_keys (
      user_id uuid PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
      key_ciphertext bytea NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE memory_items (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
      text_ct bytea NOT NULL,
      vec_ct bytea,
      vec_model text CHECK (vec_model IS NULL OR char_length(vec_model) <= 100),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX memory_items_user_idx ON memory_items (user_id, created_at)",
    f"GRANT SELECT, INSERT ON memory_keys TO {APP_ROLE}",
    f"GRANT SELECT, INSERT, DELETE ON memory_items TO {APP_ROLE}",
    f"GRANT UPDATE (text_ct, vec_ct, vec_model, updated_at) ON memory_items TO {APP_ROLE}",
)
DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE memory_items",
    "DROP TABLE memory_keys",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
