"""Topic groups: record the creator, bound the name, and make groups read-only for the app."""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE topic_groups ADD COLUMN created_by uuid REFERENCES users (id) ON DELETE SET NULL",
    "ALTER TABLE topic_groups ADD CONSTRAINT topic_groups_name_check"
    " CHECK (char_length(name) BETWEEN 1 AND 60 AND name = btrim(name) AND name !~ '[[:cntrl:]]')",
    f"REVOKE UPDATE, DELETE ON topic_groups FROM {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    f"GRANT UPDATE, DELETE ON topic_groups TO {APP_ROLE}",
    "ALTER TABLE topic_groups DROP CONSTRAINT topic_groups_name_check",
    "ALTER TABLE topic_groups DROP COLUMN created_by",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
