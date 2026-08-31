"""Reason taxonomy — every code the runner may emit is listed once."""

from arena.reasons import (
    ABORT_CONCURRENCY,
    ABORT_STREAM_NOT_PLAYWRIGHT,
    FAIL_CANVAS_CLICK_MISS,
    FAIL_COORD_SPACE,
    FAIL_NO_MUTATION,
    FAIL_OOD_SHIFT,
    FAIL_ORIGINAL_MUTATED,
    FAIL_SOM_NO_DOM,
    FAIL_WRONG_CLAIM,
    HALT_ILLEGIBLE,
    NO_CLICK_REASONS,
    PASS_ORACLE,
    REASON_CODES,
    is_known_reason,
)


def test_taxonomy_is_closed():
    expected = {
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
    assert REASON_CODES == expected
    assert all(is_known_reason(c) for c in expected)
    assert not is_known_reason("PASS_FAKE_LEADERBOARD")


def test_illegible_is_a_no_click_reason():
    assert HALT_ILLEGIBLE in NO_CLICK_REASONS
    assert FAIL_COORD_SPACE in NO_CLICK_REASONS
    assert PASS_ORACLE not in NO_CLICK_REASONS
