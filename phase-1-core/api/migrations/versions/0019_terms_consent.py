"""Record which Terms version each person accepted, and when."""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE users ADD COLUMN terms_version text"
    " CHECK (terms_version ~ '^\\d{4}-\\d{2}-\\d{2}$')",
    "ALTER TABLE users ADD COLUMN terms_accepted_at timestamptz",
    "ALTER TABLE users ADD CONSTRAINT users_terms_both"
    " CHECK ((terms_version IS NULL) = (terms_accepted_at IS NULL))",
)

DOWNGRADE: tuple[str, ...] = (
    "ALTER TABLE users DROP CONSTRAINT users_terms_both",
    "ALTER TABLE users DROP COLUMN terms_accepted_at",
    "ALTER TABLE users DROP COLUMN terms_version",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
