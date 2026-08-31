"""OSWorld-ish task records. Goal-conditioned instruction must name claim_id."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from .geometry import VIEWPORT_H, VIEWPORT_W
from .oracle import OracleSpec, parse_oracle

SIDE_CLAIM_DEFAULT = "CLM-1002"


@dataclass(frozen=True)
class Task:
    id: str
    seed: int
    viewport: tuple
    device_scale_factor: int
    cta_corner: str
    ood_shift_px: int
    instruction: str
    oracle: OracleSpec
    side_oracle: OracleSpec

    @property
    def is_ood(self) -> bool:
        return self.ood_shift_px != 0

    @property
    def viewport_w(self) -> int:
        return int(self.viewport[0])

    @property
    def viewport_h(self) -> int:
        return int(self.viewport[1])

    def worklist_query(self) -> str:
        return (
            f"ctaCorner={self.cta_corner}"
            f"&oodShiftPx={self.ood_shift_px}"
            f"&claimId={self.oracle.claim_id}"
        )


def _sibling_path(path: str, claim_id: str) -> str:
    if "/" in path:
        parent, name = path.rsplit("/", 1)
        if name.endswith(".json"):
            return f"{parent}/{claim_id}.json"
    return path.replace("CLM-1001", claim_id)


def parse_task(raw: dict) -> Task:
    if not isinstance(raw, dict):
        raise ValueError("task must be an object")
    vp = raw.get("viewport") or {}
    if not isinstance(vp, dict):
        raise ValueError("viewport must be an object")
    w = int(vp.get("width", VIEWPORT_W))
    h = int(vp.get("height", VIEWPORT_H))
    oracle = parse_oracle(raw["oracle"])
    side_raw = raw.get("sideOracle") or {
        "type": oracle.type,
        "path": raw.get("sidePath") or _sibling_path(oracle.path, raw.get("sideClaimId") or SIDE_CLAIM_DEFAULT),
        "claimId": raw.get("sideClaimId") or SIDE_CLAIM_DEFAULT,
    }
    side = parse_oracle(side_raw)
    instruction = str(raw.get("instruction") or "")
    if oracle.claim_id not in instruction:
        raise ValueError("instruction must be goal-conditioned and mention claimId")
    dsf = int(raw.get("deviceScaleFactor", 1))
    if dsf != 1:
        raise ValueError("deviceScaleFactor must be 1 (DPR is pinned)")
    return Task(
        id=str(raw["id"]),
        seed=int(raw.get("seed", 0)),
        viewport=(w, h),
        device_scale_factor=dsf,
        cta_corner=str(raw.get("ctaCorner", "bottom-right")),
        ood_shift_px=int(raw.get("oodShiftPx", 0)),
        instruction=instruction,
        oracle=oracle,
        side_oracle=side,
    )


def load_task(path: Path) -> Task:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a JSON object")
    return parse_task(raw)


def load_tasks(tasks_dir: Path) -> List[Task]:
    paths = sorted(tasks_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"no tasks in {tasks_dir}")
    return [load_task(p) for p in paths]
