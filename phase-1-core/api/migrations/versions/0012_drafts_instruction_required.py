"""Drafts: the instruction is NOT NULL (a CHECK alone lets NULL through)."""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.execute("ALTER TABLE drafts ALTER COLUMN instruction SET NOT NULL")


def downgrade() -> None:
    """Undo this migration."""
    op.execute("ALTER TABLE drafts ALTER COLUMN instruction DROP NOT NULL")
