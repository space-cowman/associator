"""Product length limits (PRODUCT-SPEC §3 and §5)."""

from safety.models import CheckIn, Finding

TEXT_LIMIT = 500
CONTENT_LIMIT = 2_000
STEPS_LIMIT = 10
STEP_LIMIT = 200


def check_limits(body: CheckIn) -> list[Finding]:
    """Check text and blocks against the size limits."""
    found: list[Finding] = []

    def over(location: str, kind: str) -> None:
        """Record one limit that was passed."""
        found.append(Finding(check="limit", severity="block", location=location, kind=kind))

    if len(body.text) > TEXT_LIMIT:
        over("text", f"text longer than {TEXT_LIMIT} characters")
    for i, block in enumerate(body.sub_blocks):
        where = f"sub_blocks[{i}]"
        if block.content is not None and len(block.content) > CONTENT_LIMIT:
            over(where, f"{block.kind} longer than {CONTENT_LIMIT} characters")
        if block.steps is not None:
            if len(block.steps) > STEPS_LIMIT:
                over(where, f"more than {STEPS_LIMIT} steps")
            for j, step in enumerate(block.steps):
                if len(step) > STEP_LIMIT:
                    over(f"{where}.steps[{j}]", f"step longer than {STEP_LIMIT} characters")
    return found
