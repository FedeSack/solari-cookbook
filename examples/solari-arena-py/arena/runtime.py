"""VM lifecycle: host the portal, snapshot, fork under the Free 1-VM cap.

DesktopClient.create() has no from_snapshot; forks go through
SandboxClient.create_desktop(from_snapshot=...). record=True on that
path is 400 RecordingRequiresGoldenBoot; record the golden boot or a
browser replay instead.

GET /sessions/:id is a *browser* session view, not VM health. Desktops
use desktop.health() after X11 is up, same as desktop-computer-use-py.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import urlopen

from .geometry import VIEWPORT_H, VIEWPORT_W, looks_like_stream_url
from .oracle import parse_claim_json
from .reasons import ABORT_CONCURRENCY, ABORT_STREAM_NOT_PLAYWRIGHT
from .tasks import Task

BASE_URL = "https://api.getsolari.com"
GUEST_ROOT = "/tmp/clinic"
PORT = 8765
HERE = Path(__file__).resolve().parent.parent
PORTAL_DIR = HERE / "portal"

# Free-plan shape the runner actually respects: 3 browsers + 1 VM, serial.
CPU = 1
MEM_MB = 2048
TIMEOUT_MS = 5 * 60_000


@dataclass
class Host:
    kind: str  # "desktop" | "sandbox"
    handle: Any
    preview: str
    stream_url: str = ""
    fork_path: str = ""
    notes: List[str] = field(default_factory=list)


def api_key() -> Optional[str]:
    # Never print or log this.
    key = os.environ.get("SOLARI_API_KEY")
    return key if key else None


def _map_create_error(exc: BaseException) -> Optional[str]:
    name = type(exc).__name__
    status = getattr(exc, "status", None)
    code = getattr(exc, "code", None)
    if name == "ConcurrencyLimitError" or code == "ConcurrencyLimitExceeded" or status == 429:
        return ABORT_CONCURRENCY
    return None


async def _wait_preview(url: str, attempts: int = 20) -> None:
    last = None
    for _ in range(attempts):
        try:
            with urlopen(url, timeout=3) as resp:  # noqa: S310  # preview we minted
                if 200 <= resp.status < 500:
                    return
                last = resp.status
        except Exception as exc:  # noqa: BLE001  # poll until it exists
            last = exc
        await asyncio.sleep(1)
    raise RuntimeError(f"preview never came up ({last}): {url}")


async def _write_portal(vm: Any) -> None:
    # files.write at runtime. Free has no custom templates.
    mkdir = getattr(vm.files, "mkdir", None)
    if mkdir is not None:
        try:
            await mkdir(GUEST_ROOT)
            await mkdir(f"{GUEST_ROOT}/data")
        except Exception:
            pass
    for path in sorted(PORTAL_DIR.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        rel = path.relative_to(PORTAL_DIR).as_posix()
        dest = f"{GUEST_ROOT}/{rel}"
        await vm.files.write(dest, path.read_bytes())


async def reset_claim_files(vm: Any) -> None:
    """Rewrite pending claim JSON so a CDP miss (or hit) cannot poison the snapshot."""
    data = PORTAL_DIR / "data"
    for src in sorted(data.glob("CLM-*.json")):
        await vm.files.write(f"{GUEST_ROOT}/data/{src.name}", src.read_bytes())


async def _start_server(vm: Any) -> None:
    # commands.run waits for exit unless background=True. Same bite as
    # sandbox-port-preview: a foreground server would sit until idle timeout.
    await vm.commands.run(
        "python3",
        args=[f"{GUEST_ROOT}/server.py", str(PORT)],
        cwd=GUEST_ROOT,
        background=True,
    )


async def _wait_desktop_ready(desktop: Any) -> None:
    for _ in range(30):
        health = await desktop.health()
        if getattr(health, "ready", False):
            return
        await asyncio.sleep(1)
    raise RuntimeError("desktop.health() never reported ready (not GET /sessions/:id)")


async def end_vm(vm: Any) -> None:
    """kill() ends the VM. close() only drops the local channel and must not
    be used as a fallback; that leaves the guest billed until idle timeout.
    """
    if vm is None:
        return
    last: Optional[BaseException] = None
    for _ in range(2):
        try:
            await vm.kill()
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
    sys.stderr.write(f"end_vm: kill failed ({type(last).__name__}); VM may still be billed\n")


async def read_claim_file(vm: Any, claim_id: str) -> dict:
    text = await vm.files.read_text(f"{GUEST_ROOT}/data/{claim_id}.json")
    return parse_claim_json(text)


async def read_claim_http(preview: str, spec_path: str) -> dict:
    if spec_path.startswith("http"):
        url = spec_path
    else:
        url = preview.rstrip("/") + "/" + spec_path.lstrip("/")
    with urlopen(url, timeout=5) as resp:  # noqa: S310
        return parse_claim_json(resp.read().decode("utf-8"))


async def read_oracle(vm: Any, preview: str, spec) -> dict:
    if spec.type == "http":
        return await read_claim_http(preview, spec.path)
    return await read_claim_file(vm, spec.claim_id)


async def boot_original(sbx: Any) -> Host:
    """Golden boot. Desktop may 402 on Free; fall back to sandbox, no fake GUI."""
    notes: List[str] = []
    handle = None
    kind = "desktop"
    try:
        # record=True is legal on a golden boot and 400 with fromSnapshot.
        # Default off: recording is extra spend. Opt in with SOLARI_ARENA_REPLAY=1.
        record = os.environ.get("SOLARI_ARENA_REPLAY") == "1"
        handle = await sbx.create_desktop(
            template="default",
            resolution=f"{VIEWPORT_W}x{VIEWPORT_H}",
            cpu=CPU,
            mem_mb=MEM_MB,
            timeout_ms=TIMEOUT_MS,
            **({"record": True} if record else {}),
        )
        notes.append("desktop golden boot" + (" (record=true)" if record else ""))
    except Exception as exc:
        abort = _map_create_error(exc)
        if abort:
            raise RuntimeError(abort) from exc
        status = getattr(exc, "status", None)
        code = getattr(exc, "code", None)
        if status == 402 or code == "FeatureRequiresPlan" or type(exc).__name__ == "PlanError":
            notes.append(f"desktop 402 {type(exc).__name__}: fallback to sandbox+browsers, no fake GUI")
            kind = "sandbox"
            handle = await sbx.create(
                template="base",
                cpu=CPU,
                mem_mb=MEM_MB,
                timeout_ms=TIMEOUT_MS,
            )
        else:
            # Capacity is retryable; concurrency is not.
            if type(exc).__name__ == "NoCapacityError" or status == 503:
                notes.append("503 NoCapacityError on desktop; retrying once")
                await asyncio.sleep(2)
                try:
                    handle = await sbx.create_desktop(
                        template="default",
                        resolution=f"{VIEWPORT_W}x{VIEWPORT_H}",
                        cpu=CPU,
                        mem_mb=MEM_MB,
                        timeout_ms=TIMEOUT_MS,
                    )
                except Exception as exc2:
                    abort = _map_create_error(exc2)
                    if abort:
                        raise RuntimeError(abort) from exc2
                    notes.append("desktop still unavailable; sandbox fallback")
                    kind = "sandbox"
                    handle = await sbx.create(
                        template="base",
                        cpu=CPU,
                        mem_mb=MEM_MB,
                        timeout_ms=TIMEOUT_MS,
                    )
            else:
                raise

    assert handle is not None
    await handle.connect()
    if kind == "desktop":
        await _wait_desktop_ready(handle)
        stream = getattr(handle, "streamUrl", "") or ""
        if looks_like_stream_url(stream):
            notes.append("streamUrl is RFB/VNC; never Playwright against it")
    else:
        stream = ""

    await _write_portal(handle)
    await _start_server(handle)
    preview = await handle.preview_url(PORT)
    url = preview["url"] if isinstance(preview, dict) else str(preview)
    await _wait_preview(url)
    return Host(kind=kind, handle=handle, preview=url, stream_url=stream, notes=notes)


async def snapshot_original(host: Host) -> str:
    # POST /sandboxes/:id/snapshots via the SDK hook.
    return await host.handle.snapshot("arena-after-login-setup")


async def release_then_fork(sbx: Any, host: Host, snap_id: str) -> Tuple[Host, str]:
    """Free is 1 concurrent VM. Do not keep original + fork live.

    Hypothesis: pause frees the slot and we can resume later to assert the
    original files did not change. If pause+fromSnapshot hits 429, kill
    the original and boot the fork (then we cannot check the original).
    """
    original = host.handle
    release = "paused"
    try:
        await original.pause()
        host.notes.append("paused original to free the 1-VM slot")
    except Exception as exc:
        host.notes.append(f"pause failed ({type(exc).__name__}); killing original")
        await end_vm(original)
        release = "killed"

    async def _create_fork() -> Any:
        if host.kind == "desktop":
            return await sbx.create_desktop(
                from_snapshot=snap_id,
                resolution=f"{VIEWPORT_W}x{VIEWPORT_H}",
                cpu=CPU,
                mem_mb=MEM_MB,
                timeout_ms=TIMEOUT_MS,
                # record=True here is 400 RecordingRequiresGoldenBoot
            )
        return await sbx.create(
            from_snapshot=snap_id,
            cpu=CPU,
            mem_mb=MEM_MB,
            timeout_ms=TIMEOUT_MS,
        )

    try:
        fork = await _create_fork()
    except Exception as exc:
        abort = _map_create_error(exc)
        if abort and release == "paused":
            host.notes.append("pause+fromSnapshot hit 429; kill-then-fromSnapshot")
            await end_vm(original)
            release = "killed-after-429"
            try:
                fork = await _create_fork()
            except Exception as exc2:
                abort2 = _map_create_error(exc2) or abort
                raise RuntimeError(abort2) from exc2
        elif abort:
            raise RuntimeError(abort) from exc
        else:
            raise

    await fork.connect()
    if host.kind == "desktop":
        await _wait_desktop_ready(fork)
    preview = await fork.preview_url(PORT)
    url = preview["url"] if isinstance(preview, dict) else str(preview)
    await _wait_preview(url)
    stream = getattr(fork, "streamUrl", "") or ""
    return (
        Host(kind=host.kind, handle=fork, preview=url, stream_url=stream, fork_path=release, notes=list(host.notes)),
        release,
    )


def refuse_playwright_on_stream(stream_url: str) -> Optional[str]:
    if looks_like_stream_url(stream_url):
        return ABORT_STREAM_NOT_PLAYWRIGHT
    return None


async def maybe_poll_browser_replay(solari: Any, session_id: str) -> Optional[int]:
    """Replay upload is async after release. Poll ~30s, same as the recording example.

    Retention is documented as 1 day. We only check that something landed.
    """
    from solari_browser.errors import SolariError

    for attempt in range(1, 11):
        await asyncio.sleep(3)
        try:
            blob = await solari.sessions.download_replay(session_id)
        except SolariError as err:
            if getattr(err, "status", None) == 404:
                continue
            raise
        return len(blob)
    return None


def task_url(preview: str, task: Task, path: str = "/") -> str:
    return f"{preview.rstrip('/')}{path}?{task.worklist_query()}"


def row(
    task_id: str,
    policy: str,
    success: int,
    side_clean: int,
    reason: str,
    promoted: str,
) -> Dict[str, Any]:
    return {
        "task": task_id,
        "policy": policy,
        "success": success,
        "side_effect_clean": side_clean,
        "reason": reason,
        "promoted": promoted,
    }
