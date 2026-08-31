"""Reason codes for one canvas worklist.

success = the right claim JSON was processed.
side-effect-clean = the other claim did not move.
"""

from __future__ import annotations

from typing import FrozenSet

PASS_ORACLE = "PASS_ORACLE"
FAIL_WRONG_CLAIM = "FAIL_WRONG_CLAIM"
FAIL_NO_MUTATION = "FAIL_NO_MUTATION"
FAIL_ORIGINAL_MUTATED = "FAIL_ORIGINAL_MUTATED"
HALT_ILLEGIBLE = "HALT_ILLEGIBLE"
FAIL_CANVAS_CLICK_MISS = "FAIL_CANVAS_CLICK_MISS"
FAIL_SOM_NO_DOM = "FAIL_SOM_NO_DOM"
FAIL_COORD_SPACE = "FAIL_COORD_SPACE"
FAIL_OOD_SHIFT = "FAIL_OOD_SHIFT"
ABORT_CONCURRENCY = "ABORT_CONCURRENCY"
ABORT_STREAM_NOT_PLAYWRIGHT = "ABORT_STREAM_NOT_PLAYWRIGHT"

REASON_CODES: FrozenSet[str] = frozenset(
    {
        PASS_ORACLE,
        FAIL_WRONG_CLAIM,
        FAIL_NO_MUTATION,
        FAIL_ORIGINAL_MUTATED,
        HALT_ILLEGIBLE,
        FAIL_CANVAS_CLICK_MISS,
        FAIL_SOM_NO_DOM,
        FAIL_COORD_SPACE,
        FAIL_OOD_SHIFT,
        ABORT_CONCURRENCY,
        ABORT_STREAM_NOT_PLAYWRIGHT,
    }
)

# These must not click. An illegible frame that still clicks is a bug.
NO_CLICK_REASONS: FrozenSet[str] = frozenset(
    {HALT_ILLEGIBLE, ABORT_STREAM_NOT_PLAYWRIGHT, ABORT_CONCURRENCY, FAIL_COORD_SPACE}
)


def is_known_reason(code: str) -> bool:
    return code in REASON_CODES
