"""One-shot live schedule and a Free-plan cost ceiling.

Rates are copied from https://docs.getsolari.com/pricing (retrieved
2026-09-01). They go stale. Dry-run does not call the API to refresh them.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .runtime import CPU, MEM_MB, TIMEOUT_MS

# Published Free rates. Not a live quote.
FREE_BROWSER_USD_PER_HOUR = 0.15
FREE_SANDBOX_1VCPU_2GB_USD_PER_HOUR = 0.086
FREE_DESKTOP_SCREEN_USD_PER_HOUR = 0.02
FREE_MONTHLY_CREDITS_USD = 3.0

# Ceiling, not a promise. Each VM we create is admitted with TIMEOUT_MS.
# Shortest serial: original then fork (never concurrent). Two browser
# sessions, one at a time, each given two minutes in this estimate.
CEILING_BROWSER_SESSIONS = 2
CEILING_BROWSER_MINUTES_EACH = 2.0


SHORTEST_STEPS: List[str] = [
    "1. create_desktop (sandbox on 402). 1 vCPU / 2 GiB. timeout_ms=300000. record only if SOLARI_ARENA_REPLAY=1",
    "2. files.write portal, commands.run server background=True, preview_url",
    "3. launch browser (recording only if REPLAY=1, stealth=False). policy CDP on original. browser.close",
    "4. reset claim JSON from portal/data. snapshot. record is illegal on the next create",
    "5. pause original (kill if pause fails) so the Free 1-VM slot is free",
    "6. create_desktop(from_snapshot=...) or create(from_snapshot=...). never record",
    "7. launch browser. policy vision on the fork. browser.close",
    "8. policy desktop mouse on the same fork (skip if kind=sandbox; no fake GUI)",
    "9. kill fork. resume original if paused (FAIL_ORIGINAL_MUTATED if files drifted). kill original",
]


def replay_opted_in() -> bool:
    return os.environ.get("SOLARI_ARENA_REPLAY") == "1"


def estimate_free_one_shot(*, kind: str = "desktop", replay: Optional[bool] = None) -> Dict[str, Any]:
    """Resource envelope plus a dollar ceiling from published Free rates.

    kind=desktop includes the $0.02/h live screen. kind=sandbox does not.
    replay does not add an hourly line in the public table; it is the same
    session clock plus a 1-day replay blob.
    """
    if replay is None:
        replay = replay_opted_in()
    vm_minutes = 2.0 * (TIMEOUT_MS / 60_000)  # original + fork, serial
    browser_minutes = CEILING_BROWSER_SESSIONS * CEILING_BROWSER_MINUTES_EACH
    sandbox_hour = FREE_SANDBOX_1VCPU_2GB_USD_PER_HOUR
    vm_hour = sandbox_hour + (FREE_DESKTOP_SCREEN_USD_PER_HOUR if kind == "desktop" else 0.0)
    vm_usd = vm_hour * (vm_minutes / 60.0)
    browser_usd = FREE_BROWSER_USD_PER_HOUR * (browser_minutes / 60.0)
    ceiling = round(vm_usd + browser_usd, 4)
    return {
        "plan": "Free",
        "monthly_credits_usd": FREE_MONTHLY_CREDITS_USD,
        "source": "https://docs.getsolari.com/pricing",
        "source_retrieved": "2026-09-01",
        "kind": kind,
        "cpu": CPU,
        "mem_mb": MEM_MB,
        "timeout_ms": TIMEOUT_MS,
        "concurrent_vms": 1,
        "concurrent_browsers": 1,
        "desktop_record": replay and kind == "desktop",
        "browser_recording": replay,
        "from_snapshot_record": False,
        "stealth": False,
        "ceiling_vm_minutes": vm_minutes,
        "ceiling_browser_minutes": browser_minutes,
        "rates_usd_per_hour": {
            "browser": FREE_BROWSER_USD_PER_HOUR,
            "sandbox_1vcpu_2gb": FREE_SANDBOX_1VCPU_2GB_USD_PER_HOUR,
            "desktop_screen": FREE_DESKTOP_SCREEN_USD_PER_HOUR if kind == "desktop" else 0.0,
        },
        "ceiling_usd": ceiling,
        "note": (
            "ceiling assumes both VMs live their full timeout and each browser "
            "session lasts 2 minutes. Actual one-shot should be cheaper. "
            "Rates stale independently of this repo."
        ),
    }


def format_dry_run(*, kind: str = "desktop") -> str:
    env = estimate_free_one_shot(kind=kind)
    lines = [
        "solari-arena-py dry-run (no API)",
        "one-shot live serial, in-dist task only",
        "",
        "schedule",
        *SHORTEST_STEPS,
        "",
        "Free-plan envelope",
        f"  concurrent: {env['concurrent_vms']} VM + {env['concurrent_browsers']} browser",
        f"  machine: {env['cpu']} vCPU / {env['mem_mb']} MiB  timeout_ms={env['timeout_ms']}",
        f"  record: desktop={env['desktop_record']} browser={env['browser_recording']} "
        f"fromSnapshot={env['from_snapshot_record']}",
        f"  stealth: {env['stealth']}",
        "",
        "estimated ceiling (published Free rates, not a live quote)",
        f"  source: {env['source']} ({env['source_retrieved']})",
        f"  monthly credits: ${env['monthly_credits_usd']:.2f}",
        f"  VM minutes (original+fork serial): {env['ceiling_vm_minutes']:.0f}",
        f"  browser minutes (2 sessions): {env['ceiling_browser_minutes']:.0f}",
        f"  ceiling USD ({kind}): ${env['ceiling_usd']:.4f}",
        f"  {env['note']}",
    ]
    return "\n".join(lines) + "\n"
