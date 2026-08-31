"""Region-prior vision on the OOD task → FAIL_OOD_SHIFT, no click."""

from __future__ import annotations

import io

from PIL import Image

from arena.geometry import CTA_RGB, HEADER_H, VIEWPORT_H, VIEWPORT_W, cta_rect
from arena.reasons import FAIL_OOD_SHIFT
from arena.vision import plan_click


def _frame_with_cta(rect) -> bytes:
    im = Image.new("RGB", (VIEWPORT_W, VIEWPORT_H))
    px = im.load()
    for y in range(VIEWPORT_H):
        for x in range(VIEWPORT_W):
            px[x, y] = ((x * 13 + y) % 180, (y * 7) % 160 + 20, (x + y) % 140 + 30)
    # CTA is canvas-relative; the page screenshot includes the 64px header.
    x0, y0 = rect.x, rect.y + HEADER_H
    for x in range(x0, x0 + rect.w):
        for y in range(y0, y0 + rect.h):
            if 0 <= x < VIEWPORT_W and 0 <= y < VIEWPORT_H:
                px[x, y] = CTA_RGB
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_in_dist_prior_misses_shifted_cta():
    shifted = cta_rect("bottom-right", 80)
    prior = cta_rect("bottom-right", 0)
    png = _frame_with_cta(shifted)
    plan = plan_click(
        png,
        CTA_RGB,
        expected_size=(VIEWPORT_W, VIEWPORT_H),
        search_region=(prior.x, prior.y + HEADER_H, prior.w, prior.h),
        ood_region_prior=True,
    )
    assert not plan.allowed
    assert plan.reason == FAIL_OOD_SHIFT


def test_full_frame_finds_shifted_cta():
    shifted = cta_rect("bottom-right", 80)
    png = _frame_with_cta(shifted)
    plan = plan_click(png, CTA_RGB, expected_size=(VIEWPORT_W, VIEWPORT_H))
    assert plan.allowed
    assert shifted.contains(plan.x, plan.y - HEADER_H)
