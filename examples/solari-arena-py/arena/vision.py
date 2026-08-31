"""Pixel vision. A screenshot is evidence; ``page.evaluate`` is not.

Illegible frame → HALT_ILLEGIBLE, no click. DPR is pinned at 1; a bitmap
that disagrees with the CSS viewport is FAIL_COORD_SPACE, not a guessed scale.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional, Tuple

from .reasons import FAIL_COORD_SPACE, FAIL_OOD_SHIFT, HALT_ILLEGIBLE

try:
    from PIL import Image
except ImportError:  # pragma: no cover - declared in requirements.txt
    Image = None  # type: ignore


MIN_BYTES = 200
MIN_EDGE = 32
MIN_UNIQUE = 8
MIN_BLOB = 12


@dataclass(frozen=True)
class ClickPlan:
    x: int
    y: int
    reason: Optional[str] = None  # set when we refuse to click

    @property
    def allowed(self) -> bool:
        return self.reason is None


def _open_rgb(png: bytes):
    if Image is None:
        raise RuntimeError("Pillow is required to decode screenshots")
    im = Image.open(io.BytesIO(png))
    return im.convert("RGB")


def screenshot_illegible(png: bytes) -> bool:
    """Blank, tiny, or near-uniform frames must HALT — do not click."""
    if not png or len(png) < MIN_BYTES:
        return True
    try:
        im = _open_rgb(png)
    except Exception:
        return True
    w, h = im.size
    if w < MIN_EDGE or h < MIN_EDGE:
        return True
    # Sample a coarse grid — getdata() is deprecated in Pillow 14.
    step_x = max(1, w // 80)
    step_y = max(1, h // 45)
    sampled = []
    px = im.load()
    for y in range(0, h, step_y):
        for x in range(0, w, step_x):
            sampled.append(px[x, y])
    # A real worklist has a dominant paper colour; that is not illegible.
    # Halt only when the frame is essentially one (or a handful of) colours.
    return len(set(sampled)) < MIN_UNIQUE


def find_color_centroid(
    png: bytes,
    rgb: Tuple[int, int, int],
    *,
    tolerance: int = 28,
    region: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[Tuple[int, int]]:
    """Centroid of pixels matching ``rgb``. ``region`` is (x, y, w, h) in shot px."""
    if screenshot_illegible(png):
        return None
    im = _open_rgb(png)
    w, h = im.size
    x0, y0, x1, y1 = 0, 0, w, h
    if region is not None:
        rx, ry, rw, rh = region
        x0, y0 = max(0, rx), max(0, ry)
        x1, y1 = min(w, rx + rw), min(h, ry + rh)
    px = im.load()
    sx = sy = n = 0
    tr, tg, tb = rgb
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y]
            if abs(r - tr) <= tolerance and abs(g - tg) <= tolerance and abs(b - tb) <= tolerance:
                sx += x
                sy += y
                n += 1
    if n < MIN_BLOB:
        return None
    return (sx // n, sy // n)


def plan_click(
    png: bytes,
    rgb: Tuple[int, int, int],
    *,
    expected_size: Tuple[int, int],
    search_region: Optional[Tuple[int, int, int, int]] = None,
    ood_region_prior: bool = False,
) -> ClickPlan:
    """Plan a click in the same pixel space as the screenshot.

    ``expected_size`` is CSS viewport (in-browser, DPR 1) or desktop resolution.
    A mismatch is FAIL_COORD_SPACE — we do not silently scale.
    """
    # Decode first so a DPR-2 bitmap is FAIL_COORD_SPACE, not a guessed scale
    # and not a generic HALT. Tiny/undecodable frames still halt.
    if not png or len(png) < MIN_BYTES:
        return ClickPlan(x=-1, y=-1, reason=HALT_ILLEGIBLE)
    try:
        im = _open_rgb(png)
    except Exception:
        return ClickPlan(x=-1, y=-1, reason=HALT_ILLEGIBLE)
    shot_w, shot_h = im.size
    if shot_w < MIN_EDGE or shot_h < MIN_EDGE:
        return ClickPlan(x=-1, y=-1, reason=HALT_ILLEGIBLE)
    exp_w, exp_h = expected_size
    if shot_w != exp_w or shot_h != exp_h:
        return ClickPlan(x=-1, y=-1, reason=FAIL_COORD_SPACE)
    if screenshot_illegible(png):
        return ClickPlan(x=-1, y=-1, reason=HALT_ILLEGIBLE)
    pt = find_color_centroid(png, rgb, region=search_region)
    if pt is None:
        reason = FAIL_OOD_SHIFT if ood_region_prior else HALT_ILLEGIBLE
        return ClickPlan(x=-1, y=-1, reason=reason)
    return ClickPlan(x=pt[0], y=pt[1], reason=None)


def banned_dom_click_methods() -> frozenset:
    """These are not vision, even if they 'click' the CTA."""
    return frozenset({"page.evaluate", "dispatchEvent", "page.evaluate_handle"})
