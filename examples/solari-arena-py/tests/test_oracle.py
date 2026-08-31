"""Oracle parser + dual-score. No API key."""

from __future__ import annotations

import json

import pytest

from arena.oracle import (
    OracleSpec,
    parse_claim_json,
    parse_oracle,
    score_oracle,
)
from arena.reasons import FAIL_NO_MUTATION, FAIL_WRONG_CLAIM, PASS_ORACLE
from arena.tasks import parse_task


PENDING = {"claimId": "CLM-1001", "status": "pending", "watermark": "SYNTHETIC"}
DONE = {"claimId": "CLM-1001", "status": "processed", "watermark": "SYNTHETIC"}
SIDE_P = {"claimId": "CLM-1002", "status": "pending", "watermark": "SYNTHETIC"}
SIDE_D = {"claimId": "CLM-1002", "status": "processed", "watermark": "SYNTHETIC"}


def test_parse_file_and_http():
    file_spec = parse_oracle({"type": "file", "path": "/tmp/clinic/data/CLM-1001.json", "claimId": "CLM-1001"})
    http_spec = parse_oracle({"type": "http", "path": "/api/claims/CLM-1002", "claimId": "CLM-1002"})
    assert file_spec == OracleSpec("file", "/tmp/clinic/data/CLM-1001.json", "CLM-1001")
    assert http_spec.type == "http"


def test_parse_rejects_unknown_type():
    with pytest.raises(ValueError, match="file|http"):
        parse_oracle({"type": "llm", "path": "/x", "claimId": "CLM-1001"})


def test_parse_rejects_missing_fields():
    with pytest.raises(ValueError):
        parse_oracle({"type": "file", "path": "", "claimId": "CLM-1001"})
    with pytest.raises(ValueError):
        parse_oracle({"type": "file", "path": "/x"})


def test_parse_claim_json():
    assert parse_claim_json(json.dumps(PENDING))["status"] == "pending"
    with pytest.raises(ValueError):
        parse_claim_json("[1]")


def test_score_pass_oracle():
    v = score_oracle(
        target_before=PENDING, target_after=DONE, side_before=SIDE_P, side_after=SIDE_P
    )
    assert v.success and v.side_effect_clean and v.reason == PASS_ORACLE


def test_score_wrong_claim():
    v = score_oracle(
        target_before=PENDING, target_after=PENDING, side_before=SIDE_P, side_after=SIDE_D
    )
    assert not v.success and not v.side_effect_clean and v.reason == FAIL_WRONG_CLAIM


def test_score_no_mutation():
    v = score_oracle(
        target_before=PENDING, target_after=PENDING, side_before=SIDE_P, side_after=SIDE_P
    )
    assert not v.success and v.side_effect_clean and v.reason == FAIL_NO_MUTATION


def test_task_instruction_must_name_claim():
    raw = {
        "id": "x",
        "viewport": {"width": 1280, "height": 720},
        "deviceScaleFactor": 1,
        "ctaCorner": "bottom-right",
        "oodShiftPx": 0,
        "instruction": "do the thing",
        "oracle": {"type": "file", "path": "/tmp/clinic/data/CLM-1001.json", "claimId": "CLM-1001"},
    }
    with pytest.raises(ValueError, match="goal-conditioned"):
        parse_task(raw)


def test_shipped_tasks_parse(tmp_path):
    from pathlib import Path

    from arena.tasks import load_tasks

    tasks = load_tasks(Path(__file__).resolve().parents[1] / "tasks")
    assert {t.id for t in tasks} == {"process-claim", "process-claim-ood"}
    assert tasks[0].device_scale_factor == 1
    ood = next(t for t in tasks if t.is_ood)
    assert ood.ood_shift_px == 80
    assert ood.side_oracle.type == "http"
