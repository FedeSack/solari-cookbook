"""Three policies, serial. CDP locators vs in-browser vision vs desktop mouse.

Vision is a screenshot + a click in that pixel space. page.evaluate /
dispatchEvent is banned. streamUrl is RFB, never Playwright.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from .geometry import (
    CTA_RGB,
    HEADER_H,
    LOGIN_FIELD_RGB,
    LOGIN_SUBMIT_RGB,
    VIEWPORT_H,
    VIEWPORT_W,
    cta_rect,
    looks_like_stream_url,
)
from .reasons import (
    ABORT_STREAM_NOT_PLAYWRIGHT,
    FAIL_CANVAS_CLICK_MISS,
    FAIL_NO_MUTATION,
    FAIL_OOD_SHIFT,
    FAIL_SOM_NO_DOM,
    FAIL_WRONG_CLAIM,
    HALT_ILLEGIBLE,
    PASS_ORACLE,
)
from .runtime import PORT, Host, read_oracle, refuse_playwright_on_stream, task_url
from .tasks import Task
from .vision import banned_dom_click_methods, plan_click
from .promote import promote_iff

# Hardcoded guest binaries only. argv is not a shell; we still refuse
# unexpected names before interpolating into `sh -c`.
_CHROME_NAMES = ("google-chrome", "chrome", "chromium")


def chrome_probe_argv(name: str) -> tuple:
    if name not in _CHROME_NAMES:
        raise ValueError(f"refusing unexpected binary name: {name!r}")
    return "sh", ["-c", f"command -v {name}"]


def _probe_exit_code(result: Any) -> int:
    return int(getattr(result, "exit_code", getattr(result, "exitCode", 1)))


def refuse_playwright_preview(url: str) -> None:
    """Playwright may open the HTTP preview, never streamUrl (RFB/VNC)."""
    if refuse_playwright_on_stream(url) or looks_like_stream_url(url):
        raise RuntimeError(ABORT_STREAM_NOT_PLAYWRIGHT)


@dataclass
class PolicyResult:
    policy: str
    reason: str
    success: bool
    side_effect_clean: bool
    promoted: bool
    clicked: bool
    note: str = ""


async def _login_cdp(page: Any, url: str) -> None:
    """Real DOM. CDP *must* get through this; the worklist is the hard part."""
    refuse_playwright_preview(url)
    await page.goto(url, wait_until="domcontentloaded")
    await page.locator("#username").fill("clerk")
    await page.locator("#password").fill("synthetic")
    await page.locator("#login-submit").click()
    await page.wait_for_url("**/worklist.html**", timeout=15_000)


async def _verdict(host: Host, task: Task, before_t, before_s, after_t, after_s, *, clicked: bool, reason_hint: Optional[str] = None) -> PolicyResult:
    decision = promote_iff(
        target_before=before_t,
        target_after=after_t,
        side_before=before_s,
        side_after=after_s,
    )
    reason = reason_hint or decision.reason
    if reason_hint is None and decision.reason == FAIL_NO_MUTATION and not clicked:
        reason = FAIL_CANVAS_CLICK_MISS
    return PolicyResult(
        policy="",
        reason=reason,
        success=decision.success,
        side_effect_clean=decision.side_effect_clean,
        promoted=decision.promote,
        clicked=clicked,
    )


async def policy_cdp(browser: Any, host: Host, task: Task) -> PolicyResult:
    ctx = await browser.new_context(
        viewport={"width": task.viewport_w, "height": task.viewport_h},
        device_scale_factor=1,
    )
    page = await ctx.new_page()
    before_t = await read_oracle(host.handle, host.preview, task.oracle)
    before_s = await read_oracle(host.handle, host.preview, task.side_oracle)
    clicked = False
    hint: Optional[str] = None
    som_missing = False
    abort: Optional[str] = None
    try:
        await _login_cdp(page, task_url(host.preview, task, "/"))

        # Set-of-Mark / named AX: the Process CTA is paint. SoM needs DOM.
        named = page.get_by_role("button", name="Process")
        som_missing = await named.count() == 0

        canvas = page.locator("canvas#worklist")
        try:
            # Default actionability: visible + stable + elementFromPoint.
            # Centre of the canvas is the overlay, and even a hit is a miss
            # relative to the corner CTA. force=True would be cheating.
            await canvas.click(timeout=5_000)
            clicked = True
        except Exception:
            clicked = False
        # After a CDP miss the useful next-policy hint is the centre click,
        # not "SoM missing" — we already observed that by counting named
        # Process controls. FAIL_SOM_NO_DOM is a note, not a second verdict.
        hint = FAIL_CANVAS_CLICK_MISS
        await asyncio.sleep(0.8)
    except RuntimeError as exc:
        if str(exc) == ABORT_STREAM_NOT_PLAYWRIGHT:
            abort = ABORT_STREAM_NOT_PLAYWRIGHT
        else:
            hint = FAIL_CANVAS_CLICK_MISS
    finally:
        await ctx.close()

    if abort:
        return PolicyResult(
            policy="cdp",
            reason=abort,
            success=False,
            side_effect_clean=True,
            promoted=False,
            clicked=False,
            note="refused Playwright on streamUrl",
        )

    after_t = await read_oracle(host.handle, host.preview, task.oracle)
    after_s = await read_oracle(host.handle, host.preview, task.side_oracle)
    result = await _verdict(host, task, before_t, before_s, after_t, after_s, clicked=clicked, reason_hint=hint)
    result.policy = "cdp"
    if result.success:
        # Unexpected: locators processed the right claim.
        result.reason = PASS_ORACLE
        result.promoted = False  # CDP ran on the original; we do not promote a pre-fork write
        result.note = "cdp unexpectedly mutated; not promoted"
    else:
        result.reason = FAIL_CANVAS_CLICK_MISS
        if som_missing:
            result.note = f"no named Process control ({FAIL_SOM_NO_DOM}); centre click missed"
    return result


async def policy_browser_vision(browser: Any, host: Host, task: Task, *, region_prior: bool = False) -> PolicyResult:
    """In-browser screenshot. Login may use locators (real DOM). Worklist may not."""
    assert "page.evaluate" in banned_dom_click_methods()
    ctx = await browser.new_context(
        viewport={"width": task.viewport_w, "height": task.viewport_h},
        device_scale_factor=1,
    )
    page = await ctx.new_page()
    before_t = await read_oracle(host.handle, host.preview, task.oracle)
    before_s = await read_oracle(host.handle, host.preview, task.side_oracle)
    clicked = False
    hint: Optional[str] = None
    abort: Optional[str] = None
    try:
        await _login_cdp(page, task_url(host.preview, task, "/"))
        shot = await page.screenshot(type="png", full_page=False)
        region = None
        if region_prior:
            # In-dist CTA box only. An 80px OOD shift should miss this prior.
            # page.screenshot includes the 64px header; CTA coords are canvas-relative.
            box = cta_rect(task.cta_corner, 0, task.viewport_w, task.viewport_h)
            region = (box.x, box.y + HEADER_H, box.w, box.h)
        plan = plan_click(
            shot,
            CTA_RGB,
            expected_size=(task.viewport_w, task.viewport_h),
            search_region=region,
            ood_region_prior=region_prior and task.is_ood,
        )
        if not plan.allowed:
            hint = plan.reason
        else:
            # CSS pixels, DPR 1. Not evaluate(), not dispatchEvent.
            await page.mouse.click(plan.x, plan.y)
            clicked = True
            await asyncio.sleep(0.8)
    except RuntimeError as exc:
        if str(exc) == ABORT_STREAM_NOT_PLAYWRIGHT:
            abort = ABORT_STREAM_NOT_PLAYWRIGHT
        else:
            hint = hint or HALT_ILLEGIBLE
    finally:
        await ctx.close()

    if abort:
        return PolicyResult(
            policy="vision",
            reason=abort,
            success=False,
            side_effect_clean=True,
            promoted=False,
            clicked=False,
            note="refused Playwright on streamUrl",
        )

    after_t = await read_oracle(host.handle, host.preview, task.oracle)
    after_s = await read_oracle(host.handle, host.preview, task.side_oracle)
    if hint in (HALT_ILLEGIBLE, FAIL_OOD_SHIFT) or (hint and hint.startswith("FAIL_")):
        result = PolicyResult(
            policy="vision",
            reason=hint or HALT_ILLEGIBLE,
            success=False,
            side_effect_clean=True,
            promoted=False,
            clicked=False,
            note="no click",
        )
        return result
    result = await _verdict(host, task, before_t, before_s, after_t, after_s, clicked=clicked, reason_hint=None)
    result.policy = "vision"
    return result


async def _open_chrome(desktop: Any, url: str) -> None:
    for name in _CHROME_NAMES:
        cmd, args = chrome_probe_argv(name)
        probe = await desktop.exec(cmd, args=args)
        if _probe_exit_code(probe) == 0 and str(getattr(probe, "stdout", "")).strip():
            await desktop.open(name, args=["--window-size=1280,720", "--window-position=0,0", url])
            return
    raise RuntimeError("no Chrome/Chromium on this desktop template")


async def policy_desktop(host: Host, task: Task) -> PolicyResult:
    if host.kind != "desktop":
        return PolicyResult(
            policy="desktop",
            reason=FAIL_NO_MUTATION,
            success=False,
            side_effect_clean=True,
            promoted=False,
            clicked=False,
            note="skipped: sandbox fallback, no GUI to fake",
        )
    # streamUrl existing is normal (RFB/VNC). Aborting here would kill policy 3
    # on every real desktop. The interlock is refuse_playwright_preview(),
    # which CDP/vision call before page.goto. This policy uses OS mouse.
    if refuse_playwright_on_stream(host.stream_url):
        host.notes.append("streamUrl is RFB/VNC; desktop policy will not hand it to Playwright")

    desktop = host.handle
    before_t = await read_oracle(desktop, host.preview, task.oracle)
    before_s = await read_oracle(desktop, host.preview, task.side_oracle)
    local = f"http://127.0.0.1:{PORT}/?{task.worklist_query()}"
    await _open_chrome(desktop, local)
    await asyncio.sleep(4)

    shot = await desktop.screenshot(format="png")
    # Desktop bitmap must match the requested resolution (DPR 1).
    user = plan_click(shot, LOGIN_FIELD_RGB, expected_size=(VIEWPORT_W, VIEWPORT_H))
    if not user.allowed:
        return PolicyResult(
            policy="desktop",
            reason=user.reason or HALT_ILLEGIBLE,
            success=False,
            side_effect_clean=True,
            promoted=False,
            clicked=False,
            note="illegible or no login field",
        )
    await desktop.mouse.click(user.x, user.y, humanize=True)
    await desktop.keyboard.type("clerk")
    await desktop.keyboard.press("Tab")
    await desktop.keyboard.type("synthetic")
    submit = plan_click(
        await desktop.screenshot(format="png"),
        LOGIN_SUBMIT_RGB,
        expected_size=(VIEWPORT_W, VIEWPORT_H),
    )
    if submit.allowed:
        await desktop.mouse.click(submit.x, submit.y, humanize=True)
    else:
        await desktop.keyboard.press("Enter")
    await asyncio.sleep(3)

    shot2 = await desktop.screenshot(format="png")
    plan = plan_click(shot2, CTA_RGB, expected_size=(VIEWPORT_W, VIEWPORT_H))
    clicked = False
    if not plan.allowed:
        after_t = await read_oracle(desktop, host.preview, task.oracle)
        after_s = await read_oracle(desktop, host.preview, task.side_oracle)
        return PolicyResult(
            policy="desktop",
            reason=plan.reason or HALT_ILLEGIBLE,
            success=False,
            side_effect_clean=True,
            promoted=False,
            clicked=False,
            note="no CTA blob",
        )
    await desktop.mouse.click(plan.x, plan.y, humanize=True)
    clicked = True
    await asyncio.sleep(1.0)

    after_t = await read_oracle(desktop, host.preview, task.oracle)
    after_s = await read_oracle(desktop, host.preview, task.side_oracle)
    result = await _verdict(host, task, before_t, before_s, after_t, after_s, clicked=clicked)
    result.policy = "desktop"
    if result.reason == FAIL_WRONG_CLAIM:
        result.note = "desktop click hit the decoy"
    return result
