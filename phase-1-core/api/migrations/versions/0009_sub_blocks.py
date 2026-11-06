"""Sub-blocks: ordered, text checked, read-only once written."""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"
BAD_CHARS = r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f‪-‮⁦-⁩]"
MAX_BLOCKS = 5

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE sub_blocks ALTER COLUMN content DROP NOT NULL",
    "ALTER TABLE sub_blocks ADD COLUMN steps text[]",
    "ALTER TABLE sub_blocks ADD COLUMN position smallint NOT NULL DEFAULT 0"
    f" CONSTRAINT sub_blocks_position_check CHECK (position BETWEEN 0 AND {MAX_BLOCKS - 1})",
    "ALTER TABLE sub_blocks ADD CONSTRAINT sub_blocks_shape_check CHECK (CASE WHEN kind = 'steps'"
    " THEN content IS NULL AND cardinality(steps) BETWEEN 1 AND 10"
    " ELSE steps IS NULL AND content IS NOT NULL END)",
    "ALTER TABLE sub_blocks ADD CONSTRAINT sub_blocks_chars_check CHECK ("
    f"coalesce(content, '') !~ '{BAD_CHARS}'"
    f" AND coalesce(array_to_string(steps, ' '), '') !~ '{BAD_CHARS}')",
    "ALTER TABLE sub_blocks ADD CONSTRAINT sub_blocks_owner_position_key"
    " UNIQUE (owner_type, owner_id, position)",
    "DROP INDEX sub_blocks_owner_idx",
    f"REVOKE UPDATE, DELETE ON sub_blocks FROM {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    f"GRANT UPDATE, DELETE ON sub_blocks TO {APP_ROLE}",
    "CREATE INDEX sub_blocks_owner_idx ON sub_blocks (owner_type, owner_id)",
    "ALTER TABLE sub_blocks DROP CONSTRAINT sub_blocks_owner_position_key",
    "ALTER TABLE sub_blocks DROP CONSTRAINT sub_blocks_chars_check",
    "ALTER TABLE sub_blocks DROP CONSTRAINT sub_blocks_shape_check",
    "ALTER TABLE sub_blocks DROP COLUMN position",
    "DELETE FROM sub_blocks WHERE kind = 'steps'",
    "ALTER TABLE sub_blocks DROP COLUMN steps",
    "ALTER TABLE sub_blocks ALTER COLUMN content SET NOT NULL",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
