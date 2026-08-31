"""FILE / HTTP oracle. The claim JSON is the ground truth, not an LLM."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .reasons import FAIL_NO_MUTATION, FAIL_WRONG_CLAIM, PASS_ORACLE


@dataclass(frozen=True)
class OracleSpec:
    type: str  # "file" | "http"
    path: str
    claim_id: str

    def __post_init__(self) -> None:
        if self.type not in ("file", "http"):
            raise ValueError(f"oracle.type must be file|http, got {self.type!r}")
        if not self.path:
            raise ValueError("oracle.path is required")
        if not self.claim_id:
            raise ValueError("oracle.claimId is required")


def parse_oracle(raw: Mapping[str, Any]) -> OracleSpec:
    if not isinstance(raw, Mapping):
        raise ValueError("oracle must be an object")
    typ = raw.get("type")
    path = raw.get("path")
    claim_id = raw.get("claimId", raw.get("claim_id"))
    if not isinstance(typ, str) or not isinstance(path, str) or not isinstance(claim_id, str):
        raise ValueError("oracle needs string fields type, path, claimId")
    if not typ.strip() or not path.strip() or not claim_id.strip():
        raise ValueError("oracle type/path/claimId must be non-empty")
    return OracleSpec(type=typ.strip(), path=path.strip(), claim_id=claim_id.strip())


def parse_claim_json(text: str) -> dict:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("claim JSON must be an object")
    return data


def claim_processed(claim: Mapping[str, Any]) -> bool:
    return str(claim.get("status", "")).lower() == "processed"


def claim_changed(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    return dict(before) != dict(after)


@dataclass(frozen=True)
class OracleVerdict:
    success: bool
    side_effect_clean: bool
    reason: str
    target_after: Optional[dict] = None
    side_after: Optional[dict] = None


def score_oracle(
    *,
    target_before: Mapping[str, Any],
    target_after: Mapping[str, Any],
    side_before: Mapping[str, Any],
    side_after: Mapping[str, Any],
) -> OracleVerdict:
    """Dual score: success (right claim) vs side-effect (wrong claim must stay)."""
    target_ok = claim_processed(target_after) and claim_changed(target_before, target_after)
    side_clean = dict(side_before) == dict(side_after)
    if target_ok and side_clean:
        reason = PASS_ORACLE
    elif not side_clean:
        reason = FAIL_WRONG_CLAIM
    else:
        reason = FAIL_NO_MUTATION
    return OracleVerdict(
        success=target_ok,
        side_effect_clean=side_clean,
        reason=reason,
        target_after=dict(target_after),
        side_after=dict(side_after),
    )
