"""Promote the fork write IFF the oracle agrees and the original stayed put.

A snapshot-fork is a copy. Writes on the fork must not appear on the paused
original. If they do, something leaked: FAIL_ORIGINAL_MUTATED, never promote.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .oracle import score_oracle
from .reasons import FAIL_ORIGINAL_MUTATED, PASS_ORACLE


@dataclass(frozen=True)
class PromoteDecision:
    promote: bool
    reason: str
    success: bool
    side_effect_clean: bool


def original_leaked(
    *,
    original_target: Optional[Mapping[str, Any]],
    original_side: Optional[Mapping[str, Any]],
    baseline_target: Optional[Mapping[str, Any]],
    baseline_side: Optional[Mapping[str, Any]],
) -> bool:
    if original_target is None or baseline_target is None:
        return False
    if dict(original_target) != dict(baseline_target):
        return True
    if original_side is not None and baseline_side is not None:
        return dict(original_side) != dict(baseline_side)
    return False


def promote_iff(
    *,
    target_before: Mapping[str, Any],
    target_after: Mapping[str, Any],
    side_before: Mapping[str, Any],
    side_after: Mapping[str, Any],
    original_target: Optional[Mapping[str, Any]] = None,
    original_side: Optional[Mapping[str, Any]] = None,
    baseline_target: Optional[Mapping[str, Any]] = None,
    baseline_side: Optional[Mapping[str, Any]] = None,
) -> PromoteDecision:
    """Accept the write only when:

    1. the right claim JSON changed to processed
    2. the other claim is untouched on the fork
    3. the paused original still matches the pre-fork baseline
    """
    if original_leaked(
        original_target=original_target,
        original_side=original_side,
        baseline_target=baseline_target,
        baseline_side=baseline_side,
    ):
        return PromoteDecision(
            promote=False,
            reason=FAIL_ORIGINAL_MUTATED,
            success=False,
            side_effect_clean=False,
        )

    verdict = score_oracle(
        target_before=target_before,
        target_after=target_after,
        side_before=side_before,
        side_after=side_after,
    )
    return PromoteDecision(
        promote=verdict.reason == PASS_ORACLE,
        reason=verdict.reason,
        success=verdict.success,
        side_effect_clean=verdict.side_effect_clean,
    )
