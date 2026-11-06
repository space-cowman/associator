"""Runs every check over every part of a post and builds the report."""

from collections.abc import Iterator

from safety.commands import find_dangerous
from safety.limits import check_limits
from safety.models import CheckIn, Finding, SafetyReport
from safety.packages import find_missing
from safety.pii import find_pii
from safety.secrets_scan import find_secrets


def parts(body: CheckIn) -> Iterator[tuple[str, str, str]]:
    """(location, kind, text) for the main text and every sub-block or step."""
    if body.text:
        yield "text", "text", body.text
    for i, block in enumerate(body.sub_blocks):
        if block.content is not None:
            yield f"sub_blocks[{i}]", block.kind, block.content
        for j, step in enumerate(block.steps or []):
            yield f"sub_blocks[{i}].steps[{j}]", "steps", step


def run_checks(body: CheckIn) -> list[Finding]:
    """CPU-bound checks (run in a worker thread by the endpoint)."""
    found = [] if body.secrets_only else check_limits(body)
    for location, kind, text in parts(body):
        for secret_kind, start, end in find_secrets(text):
            found.append(
                Finding(
                    check="secret",
                    severity="block",
                    location=location,
                    kind=secret_kind,
                    start=start,
                    end=end,
                )
            )
        if body.secrets_only:
            continue
        for entity, severity, start, end in find_pii(text, kind):
            found.append(
                Finding(
                    check="pii",
                    severity="block" if severity == "block" else "warn",
                    location=location,
                    kind=entity,
                    start=start,
                    end=end,
                )
            )
        if kind in ("code", "steps") and not body.secrets_only:
            for label, start, end in find_dangerous(text):
                found.append(
                    Finding(
                        check="dangerous_command",
                        severity="warn",
                        location=location,
                        kind=label,
                        start=start,
                        end=end,
                    )
                )
    return found


async def package_checks(body: CheckIn) -> list[Finding]:
    """Network checks (PyPI / npm); run concurrently with nothing else to wait on."""
    found: list[Finding] = []
    if body.secrets_only:
        return found
    for location, kind, text in parts(body):
        if kind in ("code", "steps"):
            for label, start, end in await find_missing(text):
                found.append(
                    Finding(
                        check="package",
                        severity="warn",
                        location=location,
                        kind=label,
                        start=start,
                        end=end,
                    )
                )
    return found


def report(found: list[Finding]) -> SafetyReport:
    """Build the check report from findings."""
    blocks = [f for f in found if f.severity == "block"]
    return SafetyReport(
        ok=not blocks,
        over_limit=any(f.check == "limit" for f in found),
        blocks=blocks,
        warnings=[f for f in found if f.severity == "warn"],
    )
