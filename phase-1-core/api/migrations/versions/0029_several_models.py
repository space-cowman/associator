"""Model registry: up to 3 models per person (Phase 2), each with strength tags and a label."""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"
STRENGTHS = "ARRAY['coding', 'reasoning', 'writing', 'cheap']::text[]"

UPGRADE: tuple[str, ...] = (
    "DROP INDEX model_registry_one_per_user",
    "CREATE UNIQUE INDEX model_registry_once ON model_registry (user_id, provider, model_name)",
    "ALTER TABLE model_registry ADD COLUMN label text"
    " CHECK (label IS NULL OR char_length(label) BETWEEN 1 AND 40)",
    "ALTER TABLE model_registry ADD COLUMN strengths text[] NOT NULL DEFAULT '{}'"
    f" CHECK (strengths <@ {STRENGTHS})",
    f"GRANT UPDATE (enabled, strengths, label) ON model_registry TO {APP_ROLE}",
)
DOWNGRADE: tuple[str, ...] = (
    f"REVOKE UPDATE (enabled, strengths, label) ON model_registry FROM {APP_ROLE}",
    "ALTER TABLE model_registry DROP COLUMN strengths",
    "ALTER TABLE model_registry DROP COLUMN label",
    "DROP INDEX model_registry_once",
    "CREATE UNIQUE INDEX model_registry_one_per_user ON model_registry (user_id)",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
