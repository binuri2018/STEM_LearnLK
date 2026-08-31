"""Pure quiz helpers: question sampling and the rule-based learning-state fallback."""
from __future__ import annotations

import random
from typing import Any

QUESTIONS_PER_LEVEL = 3


def pick_random(arr: list[Any], n: int) -> list[Any]:
    if len(arr) <= n:
        return arr
    idx = list(range(len(arr)))
    random.shuffle(idx)
    return [arr[i] for i in idx[:n]]


def rule_based_fallback(
    correctness: Any,
    response_time: Any,
    answer_changes: int | float,
    detected_expression: str,
) -> str:
    """Used when the ML model is unavailable."""
    learning_state = "partial_understanding"
    confused_exprs = {"confused", "frustrated"}
    corr = correctness
    det = detected_expression or "neutral"
    rt = float(response_time or 0)
    ach = float(answer_changes or 0)

    if corr == 1 and rt < 15 and det not in confused_exprs:
        learning_state = "strong_understanding"
    elif corr == 0 and det in confused_exprs:
        learning_state = "needs_hint"
    elif corr == 0 or rt > 30 or ach > 2:
        learning_state = "weak_understanding"

    return learning_state
