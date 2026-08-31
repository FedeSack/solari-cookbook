"""Canvas CTA geometry. Numbers are pinned; keep portal/worklist.js in sync.

Playwright ``locator('canvas').click()`` aims at the canvas bounding-box
centre. The CTA is painted in a *corner*, so that click is a miss, and the
centre is covered by a DOM overlay, so actionability (visible + stable +
elementFromPoint) often refuses the click anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple

Corner = Literal["top-left", "top-right", "bottom-left", "bottom-right"]

VIEWPORT_W = 1280
VIEWPORT_H = 720
HEADER_H = 64
CTA_W = 168
CTA_H = 44
PAD = 18
OVERLAY_W = 420
OVERLAY_H = 180

# Distinctive paint. Vision matches pixels; there is no named AX node.
CTA_RGB = (232, 93, 4)  # #E85D04  target "Process"
DECOY_RGB = (29, 78, 137)  # #1D4E89  wrong claim
LOGIN_FIELD_RGB = (255, 243, 191)  # #FFF3BF  username field, desktop pixel-find
LOGIN_SUBMIT_RGB = (45, 106, 79)  # #2D6A4F


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def overlaps(self, other: "Rect") -> bool:
        return not (
            self.x + self.w <= other.x
            or other.x + other.w <= self.x
            or self.y + self.h <= other.y
            or other.y + other.h <= self.y
        )


def canvas_rect(viewport_w: int = VIEWPORT_W, viewport_h: int = VIEWPORT_H) -> Rect:
    return Rect(0, 0, viewport_w, viewport_h - HEADER_H)


def _corner_origin(canvas: Rect, corner: Corner) -> Tuple[int, int]:
    if corner == "top-left":
        return (canvas.x + PAD, canvas.y + PAD)
    if corner == "top-right":
        return (canvas.x + canvas.w - PAD - CTA_W, canvas.y + PAD)
    if corner == "bottom-left":
        return (canvas.x + PAD, canvas.y + canvas.h - PAD - CTA_H)
    if corner == "bottom-right":
        return (canvas.x + canvas.w - PAD - CTA_W, canvas.y + canvas.h - PAD - CTA_H)
    raise ValueError(f"unknown ctaCorner: {corner}")


def _shift_toward_center(x: int, y: int, corner: Corner, shift: int) -> Tuple[int, int]:
    if shift == 0:
        return (x, y)
    # 80px toward centre on both axes so the in-dist click centre is outside.
    if "right" in corner:
        x -= shift
    else:
        x += shift
    if "bottom" in corner:
        y -= shift
    else:
        y += shift
    return (x, y)


def cta_rect(
    corner: Corner = "bottom-right",
    ood_shift_px: int = 0,
    viewport_w: int = VIEWPORT_W,
    viewport_h: int = VIEWPORT_H,
) -> Rect:
    canvas = canvas_rect(viewport_w, viewport_h)
    x, y = _corner_origin(canvas, corner)
    x, y = _shift_toward_center(x, y, corner, ood_shift_px)
    return Rect(x, y, CTA_W, CTA_H)


def decoy_rect(
    target_corner: Corner = "bottom-right",
    viewport_w: int = VIEWPORT_W,
    viewport_h: int = VIEWPORT_H,
) -> Rect:
    """Wrong-claim CTA sits in the opposite corner from the in-dist target."""
    opposite: Corner = {
        "top-left": "bottom-right",
        "top-right": "bottom-left",
        "bottom-left": "top-right",
        "bottom-right": "top-left",
    }[target_corner]
    return cta_rect(opposite, 0, viewport_w, viewport_h)


def overlay_rect(viewport_w: int = VIEWPORT_W, viewport_h: int = VIEWPORT_H) -> Rect:
    canvas = canvas_rect(viewport_w, viewport_h)
    cx, cy = canvas.center
    return Rect(cx - OVERLAY_W // 2, cy - OVERLAY_H // 2, OVERLAY_W, OVERLAY_H)


def canvas_center_misses_cta(
    cta: Rect, viewport_w: int = VIEWPORT_W, viewport_h: int = VIEWPORT_H
) -> bool:
    """True when a centre click on the canvas does not land in the CTA."""
    return not cta.contains(*canvas_rect(viewport_w, viewport_h).center)


def overlay_covers_canvas_center(
    viewport_w: int = VIEWPORT_W, viewport_h: int = VIEWPORT_H
) -> bool:
    return overlay_rect(viewport_w, viewport_h).contains(
        *canvas_rect(viewport_w, viewport_h).center
    )


def ood_shift_misses_in_dist_click(
    corner: Corner,
    ood_shift_px: int,
    viewport_w: int = VIEWPORT_W,
    viewport_h: int = VIEWPORT_H,
) -> bool:
    """Clicking the in-distribution CTA centre misses after the OOD shift."""
    in_dist = cta_rect(corner, 0, viewport_w, viewport_h)
    shifted = cta_rect(corner, ood_shift_px, viewport_w, viewport_h)
    return not shifted.contains(*in_dist.center)


def classify_click(x: int, y: int, target: Rect, decoy: Rect) -> str:
    if target.contains(x, y):
        return "target"
    if decoy.contains(x, y):
        return "decoy"
    return "miss"


def looks_like_stream_url(url: str) -> bool:
    """streamUrl is raw RFB/VNC. Playwright against it is the wrong protocol."""
    u = (url or "").lower()
    return "/stream/" in u or u.startswith("rfb") or "vnc://" in u
