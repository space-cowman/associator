"""Drafts from the orchestrator: its run, models, plan and memory used."""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE drafts ADD COLUMN run_id uuid",
    "ALTER TABLE drafts ADD COLUMN models_used text[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE drafts ADD COLUMN plan jsonb NOT NULL DEFAULT '[]'",
    "ALTER TABLE drafts ADD COLUMN memory_used uuid[] NOT NULL DEFAULT '{}'",
)
DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE drafts DROP COLUMN memory_used",
    "ALTER TABLE drafts DROP COLUMN plan",
    "ALTER TABLE drafts DROP COLUMN models_used",
    "ALTER TABLE drafts DROP COLUMN run_id",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
