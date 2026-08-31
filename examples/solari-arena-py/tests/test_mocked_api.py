"""Lifecycle against a fake Solari client. Never opens api.getsolari.com."""

from __future__ import annotations

import asyncio
import builtins
import json
import os
from pathlib import Path

import pytest

from arena.promote import promote_iff
from arena.reasons import (
    ABORT_CONCURRENCY,
    ABORT_STREAM_NOT_PLAYWRIGHT,
    PASS_ORACLE,
)
from arena.runtime import (
    GUEST_ROOT,
    boot_original,
    end_vm,
    read_oracle,
    refuse_playwright_on_stream,
    release_then_fork,
    reset_claim_files,
)
from tests.fakes import FakeGatewayError, FakeSandboxClient

DONE = json.dumps({"claimId": "CLM-1001", "status": "processed"}).encode()


@pytest.fixture(autouse=True)
def _no_preview_fetch(monkeypatch):
    async def _skip(url: str, attempts: int = 20) -> None:
        return None

    monkeypatch.setattr("arena.runtime._wait_preview", _skip)


def test_run_live_without_key_is_inconclusive(capsys):
    monkey = os.environ.get("SOLARI_API_KEY")
    if monkey:
        pytest.skip("refusing to run even the key-present path in CI")
    from main import run_live

    code = asyncio.run(run_live())
    assert code == 0
    out = capsys.readouterr().out
    assert "inconclusive" in out
    assert "slr_live_" not in out


def test_run_live_refuses_under_pytest_even_with_a_key(monkeypatch, capsys):
    monkeypatch.setenv("SOLARI_API_KEY", "slr_live_TEST_NOT_A_REAL_KEY")
    monkeypatch.delenv("SOLARI_ARENA_LIVE", raising=False)

    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name in {"solari_browser", "solari_sandbox"}:
            raise AssertionError(f"must not import {name} without SOLARI_ARENA_LIVE=1")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)
    from main import run_live

    code = asyncio.run(run_live())
    assert code == 0
    out = capsys.readouterr().out
    assert "inconclusive" in out
    assert "live skipped under pytest" in out
    assert "slr_live_" not in out


def test_desktop_402_falls_back_to_sandbox():
    sbx = FakeSandboxClient(desktop_ok=False)

    async def _go():
        host = await boot_original(sbx)
        return host

    host = asyncio.run(_go())
    assert host.kind == "sandbox"
    assert any("402" in n or "fallback" in n for n in host.notes)
    assert any(c[0] == "create" for c in sbx.calls)
    assert not any(
        c[0] == "create_desktop" and c[1].get("from_snapshot") for c in sbx.calls
    )


def test_pause_then_from_snapshot_keeps_one_live_vm():
    sbx = FakeSandboxClient(desktop_ok=True, pause_then_fork_ok=True)

    async def _go():
        host = await boot_original(sbx)
        snap = await host.handle.snapshot("after-setup")
        fork, release = await release_then_fork(sbx, host, snap)
        return host, fork, release

    host, fork, release = asyncio.run(_go())
    assert release == "paused"
    assert host.handle.paused
    assert not host.handle.killed
    assert fork.handle.id != host.handle.id
    create_fork = [c for c in sbx.calls if c[0] == "create_desktop" and c[1].get("from_snapshot")]
    assert create_fork
    assert create_fork[0][1].get("record") is None


def test_pause_plus_fork_429_falls_back_to_kill_then_from_snapshot():
    sbx = FakeSandboxClient(desktop_ok=True, pause_then_fork_ok=False)

    async def _go():
        host = await boot_original(sbx)
        snap = await host.handle.snapshot("after-setup")
        fork, release = await release_then_fork(sbx, host, snap)
        return host, fork, release

    host, fork, release = asyncio.run(_go())
    assert release == "killed-after-429"
    assert host.handle.killed
    assert fork.handle.id != host.handle.id
    assert any("429" in n for n in host.notes)
    assert not any(c[0] == "close" for c in sbx.calls)


def test_record_true_with_from_snapshot_is_400():
    """API shape: the fake gateway rejects the combo. Production never sends it."""
    sbx = FakeSandboxClient()

    async def _go():
        with pytest.raises(FakeGatewayError) as exc:
            await sbx.create_desktop(from_snapshot="snap_x", record=True, resolution="1280x720")
        return exc.value

    err = asyncio.run(_go())
    assert err.status == 400
    assert err.code == "RecordingRequiresGoldenBoot"

    prod = FakeSandboxClient()

    async def _prod():
        host = await boot_original(prod)
        snap = await host.handle.snapshot("after-setup")
        return await release_then_fork(prod, host, snap)

    asyncio.run(_prod())
    forks = [c for c in prod.calls if c[0] == "create_desktop" and c[1].get("from_snapshot")]
    assert forks
    for call in forks:
        assert "record" not in call[1]


def test_stream_url_is_not_a_playwright_target():
    assert (
        refuse_playwright_on_stream("wss://api.getsolari.com/stream/vm1")
        == ABORT_STREAM_NOT_PLAYWRIGHT
    )


def test_mocked_file_oracle_promote():
    from arena.tasks import load_task

    task = load_task(Path(__file__).resolve().parents[1] / "tasks" / "process-claim.json")
    sbx = FakeSandboxClient()

    async def _go():
        host = await boot_original(sbx)
        before_t = await read_oracle(host.handle, host.preview, task.oracle)
        before_s = await read_oracle(host.handle, host.preview, task.side_oracle)
        await host.handle.files.write(f"{GUEST_ROOT}/data/CLM-1001.json", DONE)
        after_t = await read_oracle(host.handle, host.preview, task.oracle)
        after_s = await read_oracle(host.handle, host.preview, task.side_oracle)
        return before_t, before_s, after_t, after_s

    before_t, before_s, after_t, after_s = asyncio.run(_go())
    assert before_t["status"] == "pending"
    assert before_s["status"] == "pending"
    assert after_t["status"] == "processed"
    d = promote_iff(
        target_before=before_t,
        target_after=after_t,
        side_before=before_s,
        side_after=after_s,
        original_target=before_t,
        original_side=before_s,
        baseline_target=before_t,
        baseline_side=before_s,
    )
    assert d.promote and d.reason == PASS_ORACLE


def test_network_guard_blocks_solari_host():
    from tests.conftest import _blocked

    assert _blocked("https://api.getsolari.com/sandboxes")
    assert _blocked("https://preview.getsolari.com/x")
    assert not _blocked("http://127.0.0.1:8765/")


def test_map_concurrency_on_create():
    from arena.runtime import _map_create_error
    from tests.fakes import FakeConcurrencyError

    assert _map_create_error(FakeConcurrencyError()) == ABORT_CONCURRENCY


def test_boot_original_does_not_record_by_default(monkeypatch):
    monkeypatch.delenv("SOLARI_ARENA_REPLAY", raising=False)
    sbx = FakeSandboxClient()
    asyncio.run(boot_original(sbx))
    creates = [c for c in sbx.calls if c[0] == "create_desktop"]
    assert creates
    assert "record" not in creates[0][1]


def test_boot_original_records_only_when_opted_in(monkeypatch):
    monkeypatch.setenv("SOLARI_ARENA_REPLAY", "1")
    sbx = FakeSandboxClient()
    asyncio.run(boot_original(sbx))
    creates = [c for c in sbx.calls if c[0] == "create_desktop"]
    assert creates[0][1].get("record") is True


def test_end_vm_retries_kill_and_never_closes():
    class Dead:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def kill(self) -> None:
            self.calls.append("kill")
            raise RuntimeError("still billed")

        async def close(self) -> None:
            self.calls.append("close")
            raise AssertionError("close is not teardown")

    dead = Dead()
    asyncio.run(end_vm(dead))
    assert dead.calls == ["kill", "kill"]


def test_end_vm_succeeds_on_second_kill():
    class Flaky:
        def __init__(self) -> None:
            self.n = 0
            self.calls: list[str] = []

        async def kill(self) -> None:
            self.calls.append("kill")
            self.n += 1
            if self.n == 1:
                raise RuntimeError("transient")

        async def close(self) -> None:
            self.calls.append("close")

    handle = Flaky()
    asyncio.run(end_vm(handle))
    assert handle.calls == ["kill", "kill"]


def test_reset_claim_files_rewrites_pending_from_portal_data():
    sbx = FakeSandboxClient()

    async def _go():
        host = await boot_original(sbx)
        await host.handle.files.write(f"{GUEST_ROOT}/data/CLM-1001.json", DONE)
        await reset_claim_files(host.handle)
        return json.loads(await host.handle.files.read_text(f"{GUEST_ROOT}/data/CLM-1001.json"))

    claim = asyncio.run(_go())
    assert claim["status"] == "pending"
    assert claim["claimId"] == "CLM-1001"


def test_write_portal_skips_pycache(monkeypatch, tmp_path):
    from arena import runtime

    junk = tmp_path / "__pycache__" / "x.pyc"
    junk.parent.mkdir()
    junk.write_bytes(b"nope")
    (tmp_path / "server.py").write_text("print(1)\n")
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(runtime, "PORTAL_DIR", tmp_path)
    sbx = FakeSandboxClient()
    asyncio.run(boot_original(sbx))
    keys = list(sbx.files)
    assert any(k.endswith("server.py") for k in keys)
    assert not any("__pycache__" in k or k.endswith(".pyc") for k in keys)


def test_wait_desktop_ready_raises_if_never_ready(monkeypatch):
    import arena.runtime as rt
    from arena.runtime import _wait_desktop_ready

    class Never:
        async def health(self):
            class H:
                ready = False

            return H()

    async def _fast(_s):
        return None

    monkeypatch.setattr(rt.asyncio, "sleep", _fast)
    with pytest.raises(RuntimeError, match="never reported ready"):
        asyncio.run(_wait_desktop_ready(Never()))


def test_chrome_probe_uses_sh_not_a_command_binary():
    from arena.policies import chrome_probe_argv

    cmd, args = chrome_probe_argv("google-chrome")
    assert cmd == "sh"
    assert args == ["-c", "command -v google-chrome"]
    with pytest.raises(ValueError, match="unexpected"):
        chrome_probe_argv("rm")


def test_playwright_preview_refuses_stream_url():
    from arena.policies import refuse_playwright_preview

    with pytest.raises(RuntimeError, match=ABORT_STREAM_NOT_PLAYWRIGHT):
        refuse_playwright_preview("wss://api.getsolari.com/stream/vm1")
    refuse_playwright_preview("http://127.0.0.1:8765/")
