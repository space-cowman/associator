"""Hidden clusters: their content is shown to members only."""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE topic_groups ADD COLUMN hidden boolean NOT NULL DEFAULT false",
    f"REVOKE INSERT ON topic_groups FROM {APP_ROLE}",
    f"GRANT INSERT (slug, name, description, created_by) ON topic_groups TO {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    f"REVOKE INSERT ON topic_groups FROM {APP_ROLE}",
    f"GRANT INSERT ON topic_groups TO {APP_ROLE}",
    "ALTER TABLE topic_groups DROP COLUMN hidden",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
