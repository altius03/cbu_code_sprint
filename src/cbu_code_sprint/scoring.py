from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreInput:
    duration_ms: int
    accuracy: float
    typo_count: int
    backspace_count: int


def calculate_score(score_input: ScoreInput) -> int:
    """Apply the v1 score formula from docs/PROJECT_SPEC.md."""

    duration_seconds = score_input.duration_ms / 1000
    raw_score = (
        1000
        - (duration_seconds * 8)
        - (score_input.typo_count * 25)
        - score_input.backspace_count
    )
    if score_input.accuracy >= 100.0:
        raw_score += 100
    return max(0, int(round(raw_score)))


def calculate_accuracy(expected: str, typed: str) -> float:
    """Return positional character accuracy as a percentage."""

    if not expected:
        return 100.0
    comparable = typed[: len(expected)]
    matches = sum(1 for expected_ch, typed_ch in zip(expected, comparable) if expected_ch == typed_ch)
    missing = len(expected) - len(comparable)
    effective_matches = max(0, matches - max(0, len(typed) - len(expected)))
    total = len(expected) + max(0, len(typed) - len(expected)) + max(0, missing)
    if total <= 0:
        return 100.0
    return round((effective_matches / total) * 100, 2)


def count_positional_typos(expected: str, typed: str) -> int:
    """Count current positional mismatches, including extra typed characters."""

    comparable = typed[: len(expected)]
    mismatches = sum(1 for expected_ch, typed_ch in zip(expected, comparable) if expected_ch != typed_ch)
    return mismatches + max(0, len(typed) - len(expected))
