"""Cluster setting: share AI questions to improve Associator (off by default; admins only)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE conversations ADD COLUMN ai_sharing boolean NOT NULL DEFAULT false",
    "ALTER TABLE conversations ADD CHECK (kind = 'cluster' OR NOT ai_sharing)",
    f"GRANT UPDATE (ai_sharing) ON conversations TO {APP_ROLE}",
)
DOWNGRADE: tuple[str, ...] = ("ALTER TABLE conversations DROP COLUMN ai_sharing",)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
