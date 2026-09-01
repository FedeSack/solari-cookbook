"""Canvas-click-miss geometry and the 80px OOD shift."""

from arena.geometry import (
    HEADER_H,
    VIEWPORT_H,
    VIEWPORT_W,
    canvas_center_misses_cta,
    canvas_rect,
    classify_click,
    cta_rect,
    decoy_rect,
    looks_like_stream_url,
    ood_shift_misses_in_dist_click,
    overlay_covers_canvas_center,
    overlay_rect,
)
from arena.runtime import refuse_playwright_on_stream
from arena.reasons import ABORT_STREAM_NOT_PLAYWRIGHT


def test_viewport_and_header():
    c = canvas_rect()
    assert c.w == VIEWPORT_W
    assert c.h == VIEWPORT_H - HEADER_H
    assert c.center == (640, 328)


def test_canvas_center_misses_corner_cta():
    for corner in ("top-left", "top-right", "bottom-left", "bottom-right"):
        cta = cta_rect(corner, 0)
        assert canvas_center_misses_cta(cta), corner
        assert classify_click(*canvas_rect().center, cta, decoy_rect(corner)) == "miss"


def test_overlay_sits_on_the_actionability_point():
    assert overlay_covers_canvas_center()
    assert overlay_rect().contains(*canvas_rect().center)


def test_ood_shift_80_leaves_in_dist_click():
    assert ood_shift_misses_in_dist_click("bottom-right", 80)
    in_dist = cta_rect("bottom-right", 0)
    shifted = cta_rect("bottom-right", 80)
    assert classify_click(*in_dist.center, shifted, decoy_rect()) == "miss"
    # The shifted CTA still does not contain the canvas centre.
    assert canvas_center_misses_cta(shifted)
    # Pinned numbers (keep worklist.js in sync): canvas 1280x656, pad 18, CTA 168x44.
    assert in_dist.x == 1094 and in_dist.y == 594
    assert shifted.x == 1014 and shifted.y == 514
    assert in_dist.center == (1178, 616)
    assert not shifted.contains(1178, 616)


def test_canvas_center_is_not_any_corner_cta():
    cx, cy = canvas_rect().center
    for corner in ("top-left", "top-right", "bottom-left", "bottom-right"):
        assert not cta_rect(corner, 0).contains(cx, cy)
        assert not cta_rect(corner, 80).contains(cx, cy)


def test_target_and_decoy_do_not_overlap():
    target = cta_rect("bottom-right", 0)
    decoy = decoy_rect("bottom-right")
    assert not target.overlaps(decoy)
    assert classify_click(*target.center, target, decoy) == "target"
    assert classify_click(*decoy.center, target, decoy) == "decoy"


def test_stream_url_is_not_playwright():
    assert looks_like_stream_url("wss://api.getsolari.com/stream/abc")
    assert refuse_playwright_on_stream("wss://api.getsolari.com/stream/abc") == ABORT_STREAM_NOT_PLAYWRIGHT
    assert refuse_playwright_on_stream("wss://api.getsolari.com/ws/session") is None
