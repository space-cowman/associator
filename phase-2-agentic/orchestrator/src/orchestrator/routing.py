"""Which of the person's models answers what."""

from orchestrator.contract import ModelRef

WANTS = {"code": "coding", "explain": "reasoning", "check": "reasoning", "opinion": "writing"}


def pick(kind: str, models: list[ModelRef], used: list[int]) -> int:
    """Pick the model for a part by its strength."""
    want = WANTS[kind]
    tagged = [i for i, m in enumerate(models) if want in m.strengths]
    for group in ([i for i in tagged if i not in used], tagged):
        if group:
            return group[0]
    unused = [i for i in range(len(models)) if i not in used]
    return unused[0] if unused else 0


def best(models: list[ModelRef]) -> int:
    """Pick the model that answers on its own."""
    return next((i for i, m in enumerate(models) if "cheap" not in m.strengths), 0)


def chain(first: int, models: list[ModelRef], *, platform: bool = True) -> list[int | None]:
    """The order to try models in when one fails."""
    others = sorted(
        (i for i in range(len(models)) if i != first), key=lambda i: "cheap" in models[i].strengths
    )
    order: list[int | None] = [first, *others]
    return [*order, None] if platform else order
