"""Recoloured CTA: colour-centroid HALTs. Not a robust detector."""

from arena.geometry import CTA_RGB, VIEWPORT_H, VIEWPORT_W, cta_rect
from arena.reasons import HALT_ILLEGIBLE
from arena.recolor import (
    RECOLOR_RGB,
    format_recolor_table,
    render_worklist_png,
    score_recolor_fixture,
)
from arena.vision import plan_click


def test_orange_cta_is_clickable():
    png = render_worklist_png(cta_rgb=CTA_RGB)
    plan = plan_click(png, CTA_RGB, expected_size=(VIEWPORT_W, VIEWPORT_H))
    assert plan.allowed
    target = cta_rect("bottom-right", 0)
    assert target.contains(plan.x, plan.y - 64)


def test_recolored_cta_halts_no_click():
    png = render_worklist_png(cta_rgb=RECOLOR_RGB)
    plan = plan_click(png, CTA_RGB, expected_size=(VIEWPORT_W, VIEWPORT_H))
    assert not plan.allowed
    assert plan.reason == HALT_ILLEGIBLE
    assert plan.x == -1 and plan.y == -1


def test_recolor_table_shows_halt_not_a_hit():
    rows = score_recolor_fixture()
    assert rows[0]["task"] == "recolor-cta" and rows[0]["clicked"] is True
    assert rows[1]["task"] == "recolor-blue"
    assert rows[1]["clicked"] is False
    assert rows[1]["reason"] == HALT_ILLEGIBLE
    text = format_recolor_table()
    assert "HALT_ILLEGIBLE" in text
    assert "recolor-blue" in text
