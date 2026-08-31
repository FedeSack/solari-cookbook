"""Solari Arena: OSWorld-style eval on the real products.

CDP locators miss a canvas-painted corner CTA (no named AX; Playwright
clicks the canvas centre). Screenshot vision and desktop mouse can hit it.
A FILE/HTTP oracle scores the right claim vs a side-effect on the other.

Free plan = 3 browsers + 1 VM, so policies run serial. Vision runs on a
snapshot-fork; pause or kill the original first. record:true cannot combine
with fromSnapshot (400). No stealth (Free 402). No custom templates
(files.write at runtime). 1 vCPU / 2GB.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List

from arena.geometry import HEADER_H, VIEWPORT_H, VIEWPORT_W, cta_rect
from arena.policies import policy_browser_vision, policy_cdp, policy_desktop
from arena.promote import original_leaked
from arena.reasons import ABORT_CONCURRENCY, FAIL_OOD_SHIFT, FAIL_ORIGINAL_MUTATED
from arena.runtime import (
    BASE_URL,
    CPU,
    MEM_MB,
    PORT,
    TIMEOUT_MS,
    Host,
    api_key,
    boot_original,
    end_vm,
    maybe_poll_browser_replay,
    read_oracle,
    release_then_fork,
    row,
    snapshot_original,
)
from arena.tasks import Task, load_tasks

HERE = Path(__file__).resolve().parent


def _print_row(r: dict) -> None:
    print(
        f"{r['task']:<22} {r['policy']:<10} "
        f"success={int(r['success'])} side_effect_clean={int(r['side_effect_clean'])} "
        f"{r['reason']:<26} promote={r['promoted']}"
    )


async def _run_cdp(solari, host: Host, tasks: List[Task], rows: List[dict]) -> None:
    """Policy 1 on the ORIGINAL. Login is real DOM; worklist should miss."""
    # recording=True is per session and extra spend. Default off.
    # Opt in with SOLARI_ARENA_REPLAY=1; poll ~30s after release. Retention: 1 day.
    record = os.environ.get("SOLARI_ARENA_REPLAY") == "1"
    browser = await solari.launch(recording=record, stealth=False)
    session_id = browser.id
    try:
        for task in tasks:
            result = await policy_cdp(browser, host, task)
            rows.append(
                row(
                    task.id,
                    result.policy,
                    int(result.success),
                    int(result.side_effect_clean),
                    result.reason,
                    "no",
                )
            )
            _print_row(rows[-1])
            if result.note:
                print(f"  note: {result.note}")
    finally:
        await browser.close()
    if os.environ.get("SOLARI_ARENA_REPLAY") == "1":
        replay_n = await maybe_poll_browser_replay(solari, session_id)
        if replay_n is None:
            print("  replay: none after ~30s (upload is async; retention is 1 day)")
        else:
            print(f"  replay: {replay_n} bytes")


async def _boot_fork_from_snap(sbx, kind: str, snap_id: str) -> Host:
    """Original already released. fromSnapshot only; no record flag."""
    from arena.runtime import _wait_desktop_ready, _wait_preview

    if kind == "desktop":
        handle = await sbx.create_desktop(
            from_snapshot=snap_id,
            resolution=f"{VIEWPORT_W}x{VIEWPORT_H}",
            cpu=CPU,
            mem_mb=MEM_MB,
            timeout_ms=TIMEOUT_MS,
        )
    else:
        handle = await sbx.create(
            from_snapshot=snap_id,
            cpu=CPU,
            mem_mb=MEM_MB,
            timeout_ms=TIMEOUT_MS,
        )
    await handle.connect()
    if kind == "desktop":
        await _wait_desktop_ready(handle)
    preview = await handle.preview_url(PORT)
    url = preview["url"] if isinstance(preview, dict) else str(preview)
    await _wait_preview(url)
    return Host(
        kind=kind,
        handle=handle,
        preview=url,
        stream_url=getattr(handle, "streamUrl", "") or "",
    )


async def _run_fork_policies(solari, fork: Host, task: Task, rows: List[dict]) -> None:
    browser = await solari.launch(stealth=False)
    try:
        vis = await policy_browser_vision(browser, fork, task, region_prior=False)
    finally:
        await browser.close()
    rows.append(
        row(
            task.id,
            vis.policy,
            int(vis.success),
            int(vis.side_effect_clean),
            vis.reason,
            "yes" if vis.promoted else "no",
        )
    )
    _print_row(rows[-1])
    if task.is_ood:
        # Cached in-dist coords: the disagreement we came for.
        cx, cy = cta_rect(task.cta_corner, 0, task.viewport_w, task.viewport_h).center
        rows.append(row(task.id, "ood-coord", 0, 1, FAIL_OOD_SHIFT, "no"))
        _print_row(rows[-1])
        print(f"  ood: in-dist click ({cx},{cy + HEADER_H}) misses the shifted CTA")

    desk = await policy_desktop(fork, task)
    rows.append(
        row(
            task.id,
            desk.policy,
            int(desk.success),
            int(desk.side_effect_clean),
            desk.reason,
            "yes" if desk.promoted else "no",
        )
    )
    _print_row(rows[-1])
    if desk.note:
        print(f"  note: {desk.note}")


async def run_live(*, shortest: bool = True) -> int:
    key = api_key()
    if not key:
        print("inconclusive: SOLARI_API_KEY is not set; live serial skipped")
        print("keyless tests: pytest")
        return 0

    # pytest must not create VMs unless someone opted in. A leftover key in
    # the shell is not enough; CI sets the key empty.
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("SOLARI_ARENA_LIVE") != "1":
        print("inconclusive: live skipped under pytest (set SOLARI_ARENA_LIVE=1 to run)")
        return 0

    from solari_browser import Solari
    from solari_sandbox import SandboxClient

    tasks = load_tasks(HERE / "tasks")
    if shortest:
        tasks = [t for t in tasks if not t.is_ood][:1] or tasks[:1]
    rows: List[dict] = []
    print("tasks:", ", ".join(t.id for t in tasks))
    print("policies: cdp (original) → vision (fork) → desktop (fork)  [serial]")
    print("base:", BASE_URL)

    sbx = None
    original = None
    solari = None
    first_release = None
    try:
        sbx = SandboxClient(api_key=key, base_url=BASE_URL)
        solari = Solari(api_key=key, base_url=BASE_URL)
        original = await boot_original(sbx)
        for note in original.notes:
            print(" ", note)
        print("preview:", original.preview)
        if original.stream_url:
            # streamUrl is a capability (docs: treat as secret). Do not print it.
            print("streamUrl: (rfb/vnc; not printed; never Playwright)")

        first = tasks[0]
        baseline_t = await read_oracle(original.handle, original.preview, first.oracle)
        baseline_s = await read_oracle(original.handle, original.preview, first.side_oracle)

        await _run_cdp(solari, original, tasks, rows)
        # CDP runs on the original. Reset claim JSON before snapshot so a
        # surprising hit cannot become the fork's baseline.
        from arena.runtime import reset_claim_files

        await reset_claim_files(original.handle)

        snap_id = await snapshot_original(original)
        print("snapshot:", snap_id)

        for i, task in enumerate(tasks):
            if i == 0:
                fork, first_release = await release_then_fork(sbx, original, snap_id)
                print(f"  fork_path={first_release}")
            else:
                fork = await _boot_fork_from_snap(sbx, original.kind, snap_id)
            print(f"fork for {task.id}: {fork.preview}")
            try:
                await _run_fork_policies(solari, fork, task, rows)
            finally:
                await end_vm(fork.handle)

        if first_release == "paused":
            try:
                await original.handle.resume()
                post_t = await read_oracle(original.handle, original.preview, first.oracle)
                post_s = await read_oracle(original.handle, original.preview, first.side_oracle)
                if original_leaked(
                    original_target=post_t,
                    original_side=post_s,
                    baseline_target=baseline_t,
                    baseline_side=baseline_s,
                ):
                    rows.append(row("original", "leak", 0, 0, FAIL_ORIGINAL_MUTATED, "no"))
                    _print_row(rows[-1])
                else:
                    print("original unchanged after fork writes (pause+resume)")
            except Exception as exc:
                print(f"  resume original failed ({type(exc).__name__}); leak check skipped")
        else:
            print(f"original {first_release}; leak check not applicable (no live original)")

        print("reason-code table")
        print("task                   policy     success side_effect reason                     promote")
        for r in rows:
            _print_row(r)
        print(json.dumps({"rows": rows, "fork_release": first_release, "kind": original.kind}, indent=2))
        return 0
    except RuntimeError as exc:
        if str(exc) == ABORT_CONCURRENCY:
            print("ABORT_CONCURRENCY: Free cap is 1 VM / 3 browsers. Kill a leftover session and retry.")
            return 2
        raise
    finally:
        # Always end the VM. close() alone leaves it billing until idle timeout.
        if original is not None and original.handle is not None:
            await end_vm(original.handle)
        if solari is not None:
            await solari.close()
        if sbx is not None:
            await sbx.aclose()


def main() -> int:
    if "--self-check" in sys.argv:
        from arena.geometry import canvas_center_misses_cta, ood_shift_misses_in_dist_click

        box = cta_rect("bottom-right", 0)
        assert canvas_center_misses_cta(box)
        assert ood_shift_misses_in_dist_click("bottom-right", 80)
        print("self-check ok")
        return 0
    return asyncio.run(run_live())


if __name__ == "__main__":
    raise SystemExit(main())
