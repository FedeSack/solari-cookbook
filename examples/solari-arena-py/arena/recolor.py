"""Documented vision failure: recoloured CTA.

The detector is a colour-blob centroid of CTA_RGB. Recolour the paint and
it HALTs. That is the point, not a bug to paper over with a second model.
"""

from __future__ import annotations

import io
from typing import Dict, List

from .geometry import (
    CTA_RGB,
    DECOY_RGB,
    HEADER_H,
    VIEWPORT_H,
    VIEWPORT_W,
    cta_rect,
    decoy_rect,
)
from .reasons import HALT_ILLEGIBLE
from .vision import plan_click

# Not #E85D04. Same geometry, different paint.
RECOLOR_RGB = (40, 120, 200)
PAPER_RGB = (232, 226, 214)


def render_worklist_png(
    *,
    cta_rgb=CTA_RGB,
    decoy_rgb=DECOY_RGB,
    corner: str = "bottom-right",
    ood_shift_px: int = 0,
) -> bytes:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required") from exc

    im = Image.new("RGB", (VIEWPORT_W, VIEWPORT_H), (27, 31, 36))
    px = im.load()
    # Real worklists are not one flat fill. A uniform paper frame is
    # HALT_ILLEGIBLE before we ever look for the CTA.
    for y in range(HEADER_H, VIEWPORT_H):
        for x in range(VIEWPORT_W):
            px[x, y] = (
                (PAPER_RGB[0] - (x * 3 + y) % 40),
                (PAPER_RGB[1] - (y * 5) % 35),
                (PAPER_RGB[2] - (x + y) % 30),
            )
    target = cta_rect(corner, ood_shift_px)
    decoy = decoy_rect(corner)
    for rect, color in ((target, cta_rgb), (decoy, decoy_rgb)):
        x0, y0 = rect.x, rect.y + HEADER_H
        for x in range(x0, x0 + rect.w):
            for y in range(y0, y0 + rect.h):
                if 0 <= x < VIEWPORT_W and 0 <= y < VIEWPORT_H:
                    px[x, y] = color
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def score_recolor_fixture() -> List[Dict[str, object]]:
    """Two rows: orange CTA is clickable; blue CTA is HALT_ILLEGIBLE."""
    orange = plan_click(
        render_worklist_png(cta_rgb=CTA_RGB),
        CTA_RGB,
        expected_size=(VIEWPORT_W, VIEWPORT_H),
    )
    blue = plan_click(
        render_worklist_png(cta_rgb=RECOLOR_RGB),
        CTA_RGB,
        expected_size=(VIEWPORT_W, VIEWPORT_H),
    )
    return [
        {
            "task": "recolor-cta",
            "policy": "vision",
            "clicked": bool(orange.allowed),
            "reason": orange.reason or "centroid",
        },
        {
            "task": "recolor-blue",
            "policy": "vision",
            "clicked": bool(blue.allowed),
            "reason": blue.reason or "centroid",
        },
    ]


def format_recolor_table() -> str:
    rows = score_recolor_fixture()
    lines = [
        "recolor fixture (no VM; colour-centroid is not a robust detector)",
        f"{'fixture':<22} {'policy':<10} clicked reason",
    ]
    for r in rows:
        lines.append(
            f"{r['task']:<22} {r['policy']:<10} "
            f"{'yes' if r['clicked'] else 'no':<7} {r['reason']}"
        )
    assert rows[0]["clicked"] is True
    assert rows[1]["clicked"] is False
    assert rows[1]["reason"] == HALT_ILLEGIBLE
    return "\n".join(lines) + "\n"
