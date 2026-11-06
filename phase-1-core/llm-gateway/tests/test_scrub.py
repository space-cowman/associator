import pytest

from gateway.scrub import scrub


@pytest.mark.parametrize(
    "secret",
    [
        "sk-proj-AbCdEf123456",
        "sk-or-v1-ab12****9d19",  # pragma: allowlist secret
        "sk-ant-api03-xyz789abc",
        "gsk_Q7rT2mV9xL4pK8wN",
        "AIzaSyB" + "x" * 30,
        "hf_AbCdEfGh12345",
        "ghp_" + "a" * 36,
        "Bearer eyJhbGciOiJIUzI1NiJ9",
    ],
)
def test_key_shapes_are_removed(secret: str) -> None:
    """Key shapes are removed."""
    assert scrub(f"Incorrect API key provided: {secret}.") == "Incorrect API key provided: <KEY>."


def test_exact_key_and_prompts_are_removed() -> None:
    """Exact key and prompts are removed."""
    text = scrub(
        "key=plainkey123456 said: what is postgres exactly? (system: answer briefly please)",
        key="plainkey123456",
        prompts=("what is postgres exactly?", "answer briefly please", "hi"),
    )
    assert text == "key=<KEY> said: <PROMPT> (system: <PROMPT>)"


def test_short_prompts_are_left_and_length_is_bounded() -> None:
    """Short prompts are left and length is bounded."""
    assert scrub("hi there", prompts=("hi",)) == "hi there"
    assert len(scrub("x" * 5000)) == 1000
