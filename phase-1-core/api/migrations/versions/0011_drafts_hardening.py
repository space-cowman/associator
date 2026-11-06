"""Drafts: only the decision changes; the instruction is required."""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_v2_app"
BAD_CHARS = r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f‪-‮⁦-⁩]"

UPGRADE: tuple[str, ...] = (
    "ALTER TABLE drafts ADD COLUMN reply_id uuid REFERENCES replies (id) ON DELETE SET NULL",
    "ALTER TABLE drafts ADD CONSTRAINT drafts_instruction_check"
    " CHECK (char_length(instruction) BETWEEN 1 AND 300)",
    f"ALTER TABLE drafts ADD CONSTRAINT drafts_text_chars_check CHECK (text !~ '{BAD_CHARS}')",
    "ALTER TABLE drafts ADD CONSTRAINT drafts_idempotency_key_check"
    " CHECK (idempotency_key ~ '^[A-Za-z0-9-]{8,64}$')",
    "ALTER TABLE drafts ADD CONSTRAINT drafts_decision_check CHECK ("
    "(status = 'pending' AND decided_at IS NULL AND reply_id IS NULL)"
    " OR (status = 'discarded' AND decided_at IS NOT NULL AND reply_id IS NULL)"
    " OR (status = 'approved' AND decided_at IS NOT NULL))",
    f"REVOKE UPDATE, DELETE ON drafts FROM {APP_ROLE}",
    f"GRANT UPDATE (status, decided_at, reply_id) ON drafts TO {APP_ROLE}",
)

DOWNGRADE: tuple[str, ...] = (
    f"GRANT UPDATE, DELETE ON drafts TO {APP_ROLE}",
    "ALTER TABLE drafts DROP CONSTRAINT drafts_decision_check",
    "ALTER TABLE drafts DROP CONSTRAINT drafts_idempotency_key_check",
    "ALTER TABLE drafts DROP CONSTRAINT drafts_text_chars_check",
    "ALTER TABLE drafts DROP CONSTRAINT drafts_instruction_check",
    "ALTER TABLE drafts DROP COLUMN reply_id",
)


def upgrade() -> None:
    """Apply this migration."""
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    """Undo this migration."""
    for statement in DOWNGRADE:
        op.execute(statement)
