"""Link each AI draft to its LangSmith trace."""

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE: tuple[str, ...] = ("ALTER TABLE drafts ADD COLUMN trace_id uuid",)
DOWNGRADE: tuple[str, ...] = ("ALTER TABLE drafts DROP COLUMN trace_id",)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
