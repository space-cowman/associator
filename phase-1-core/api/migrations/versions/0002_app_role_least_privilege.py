"""Least privilege for the app role: votes change only their value; migration history read-only."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    f"REVOKE UPDATE ON votes FROM {APP_ROLE}",
    f"GRANT UPDATE (value) ON votes TO {APP_ROLE}",
    f"REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    f"GRANT INSERT, UPDATE, DELETE ON alembic_version TO {APP_ROLE}",
    f"GRANT UPDATE ON votes TO {APP_ROLE}",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
