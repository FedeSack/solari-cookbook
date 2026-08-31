"""Illegible screenshot → HALT, no click. Evaluate/dispatchEvent is not vision."""

from __future__ import annotations

import io

from PIL import Image

from arena.geometry import CTA_RGB, VIEWPORT_H, VIEWPORT_W
from arena.reasons import FAIL_COORD_SPACE, HALT_ILLEGIBLE
from arena.vision import banned_dom_click_methods, plan_click, screenshot_illegible


def _png(w: int, h: int, color=(12, 12, 12)) -> bytes:
    im = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _busy_bg(w: int, h: int) -> Image.Image:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 13 + y) % 180, (y * 7) % 160 + 20, (x + y) % 140 + 30)
    return im


def _cta_frame() -> bytes:
    im = _busy_bg(VIEWPORT_W, VIEWPORT_H)
    px = im.load()
    for x in range(1100, 1260):
        for y in range(620, 660):
            px[x, y] = CTA_RGB
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_empty_and_tiny_are_illegible():
    assert screenshot_illegible(b"")
    assert screenshot_illegible(b"not-a-png")
    assert screenshot_illegible(_png(16, 16))


def test_flat_frame_is_illegible():
    assert screenshot_illegible(_png(VIEWPORT_W, VIEWPORT_H, (0, 0, 0)))


def test_illegible_plan_does_not_click():
    plan = plan_click(_png(VIEWPORT_W, VIEWPORT_H, (0, 0, 0)), CTA_RGB, expected_size=(VIEWPORT_W, VIEWPORT_H))
    assert not plan.allowed
    assert plan.reason == HALT_ILLEGIBLE
    assert plan.x == -1 and plan.y == -1


def test_dpr_mismatch_is_coord_space():
    # A DPR-2 bitmap must not be clicked as CSS pixels.
    noisy = Image.new("RGB", (VIEWPORT_W * 2, VIEWPORT_H * 2), (30, 30, 30))
    for i in range(0, 2000, 3):
        noisy.putpixel((i % (VIEWPORT_W * 2), (i * 7) % (VIEWPORT_H * 2)), ((i * 13) % 255, 80, 90))
    buf = io.BytesIO()
    noisy.save(buf, format="PNG")
    plan = plan_click(buf.getvalue(), CTA_RGB, expected_size=(VIEWPORT_W, VIEWPORT_H))
    assert not plan.allowed
    assert plan.reason == FAIL_COORD_SPACE


def test_legible_cta_is_clickable():
    plan = plan_click(_cta_frame(), CTA_RGB, expected_size=(VIEWPORT_W, VIEWPORT_H))
    assert plan.allowed
    assert 1100 <= plan.x < 1260
    assert 620 <= plan.y < 660


def test_evaluate_is_not_vision():
    banned = banned_dom_click_methods()
    assert "page.evaluate" in banned
    assert "dispatchEvent" in banned
