"""Allow auth_provider 'dev' for dev tokens (`make dev-token`) until Google/GitHub sign-in."""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE users DROP CONSTRAINT users_auth_provider_check",
    "ALTER TABLE users ADD CONSTRAINT users_auth_provider_check"
    " CHECK (auth_provider IN ('google', 'github', 'dev'))",
)

DOWNGRADE: tuple[str, ...] = (
    "DELETE FROM users WHERE auth_provider = 'dev'",
    "ALTER TABLE users DROP CONSTRAINT users_auth_provider_check",
    "ALTER TABLE users ADD CONSTRAINT users_auth_provider_check"
    " CHECK (auth_provider IN ('google', 'github'))",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
