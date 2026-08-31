"""Assessment report aggregation — ported from the standalone reportController."""
from __future__ import annotations


def mode(arr: list) -> str:
    if not arr:
        return "neutral"
    freq: dict[str, int] = {}
    for v in arr:
        k = v or "neutral"
        freq[k] = freq.get(k, 0) + 1
    return max(freq, key=lambda x: freq[x])


def summary(total_score: float, weak_areas: list[str], hint_count: int) -> str:
    if total_score >= 85:
        return (
            "Excellent performance! You answered "
            f"{round(total_score)}% of questions correctly with strong understanding."
        )
    if total_score >= 60:
        weak = f" Review the following concepts: {', '.join(weak_areas)}." if weak_areas else ""
        return f"Good effort! You scored {round(total_score)}%.{weak} Keep practicing to strengthen understanding."
    return (
        f"You scored {round(total_score)}%. Several concepts need revision: {', '.join(weak_areas)}. "
        f"{hint_count} hints were used during the assessment."
    )
