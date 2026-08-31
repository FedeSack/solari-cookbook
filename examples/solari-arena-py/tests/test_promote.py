"""Promote-iff: right claim changed, wrong claim untouched, original clean."""

from arena.promote import original_leaked, promote_iff
from arena.reasons import FAIL_NO_MUTATION, FAIL_ORIGINAL_MUTATED, FAIL_WRONG_CLAIM, PASS_ORACLE

PENDING = {"claimId": "CLM-1001", "status": "pending"}
DONE = {"claimId": "CLM-1001", "status": "processed"}
SIDE_P = {"claimId": "CLM-1002", "status": "pending"}
SIDE_D = {"claimId": "CLM-1002", "status": "processed"}


def test_promote_when_oracle_and_original_agree():
    d = promote_iff(
        target_before=PENDING,
        target_after=DONE,
        side_before=SIDE_P,
        side_after=SIDE_P,
        original_target=PENDING,
        original_side=SIDE_P,
        baseline_target=PENDING,
        baseline_side=SIDE_P,
    )
    assert d.promote and d.reason == PASS_ORACLE
    assert d.success and d.side_effect_clean


def test_refuse_wrong_claim():
    d = promote_iff(
        target_before=PENDING,
        target_after=PENDING,
        side_before=SIDE_P,
        side_after=SIDE_D,
    )
    assert not d.promote and d.reason == FAIL_WRONG_CLAIM


def test_refuse_no_mutation():
    d = promote_iff(
        target_before=PENDING,
        target_after=PENDING,
        side_before=SIDE_P,
        side_after=SIDE_P,
    )
    assert not d.promote and d.reason == FAIL_NO_MUTATION


def test_refuse_if_original_leaked():
    d = promote_iff(
        target_before=PENDING,
        target_after=DONE,
        side_before=SIDE_P,
        side_after=SIDE_P,
        original_target=DONE,
        original_side=SIDE_P,
        baseline_target=PENDING,
        baseline_side=SIDE_P,
    )
    assert not d.promote and d.reason == FAIL_ORIGINAL_MUTATED


def test_original_leaked_helper():
    assert original_leaked(
        original_target=DONE,
        original_side=SIDE_P,
        baseline_target=PENDING,
        baseline_side=SIDE_P,
    )
    assert not original_leaked(
        original_target=PENDING,
        original_side=SIDE_P,
        baseline_target=PENDING,
        baseline_side=SIDE_P,
    )
    # No original to compare (killed, not paused) → not a leak signal.
    assert not original_leaked(
        original_target=None,
        original_side=None,
        baseline_target=PENDING,
        baseline_side=SIDE_P,
    )
