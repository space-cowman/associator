"""Saved models: one per person, never edited in place."""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    "DROP INDEX model_registry_user_idx",
    "CREATE UNIQUE INDEX model_registry_one_per_user ON model_registry (user_id)",
    "ALTER TABLE model_registry ADD CONSTRAINT model_registry_key_check CHECK ("
    "provider = 'platform' OR (key_ciphertext IS NOT NULL AND char_length(key_last4) = 4))",
    f"REVOKE UPDATE ON model_registry FROM {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    f"GRANT UPDATE ON model_registry TO {APP_ROLE}",
    "ALTER TABLE model_registry DROP CONSTRAINT model_registry_key_check",
    "DROP INDEX model_registry_one_per_user",
    "CREATE INDEX model_registry_user_idx ON model_registry (user_id)",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
