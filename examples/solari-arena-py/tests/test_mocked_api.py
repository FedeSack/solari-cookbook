"""Lifecycle against a fake Solari client. Never opens api.getsolari.com."""

from __future__ import annotations

import asyncio
import json
import os

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
    refuse_playwright_on_stream,
    release_then_fork,
)
from tests.fakes import FakeGatewayError, FakeSandboxClient

PENDING = json.dumps({"claimId": "CLM-1001", "status": "pending"}).encode()
SIDE = json.dumps({"claimId": "CLM-1002", "status": "pending"}).encode()
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


def test_record_true_with_from_snapshot_is_400():
    sbx = FakeSandboxClient()

    async def _go():
        with pytest.raises(FakeGatewayError) as exc:
            await sbx.create_desktop(from_snapshot="snap_x", record=True, resolution="1280x720")
        return exc.value

    err = asyncio.run(_go())
    assert err.status == 400
    assert err.code == "RecordingRequiresGoldenBoot"


def test_stream_url_is_not_a_playwright_target():
    assert (
        refuse_playwright_on_stream("wss://api.getsolari.com/stream/vm1")
        == ABORT_STREAM_NOT_PLAYWRIGHT
    )


def test_mocked_file_oracle_promote():
    sbx = FakeSandboxClient()
    sbx.files[f"{GUEST_ROOT}/data/CLM-1001.json"] = PENDING
    sbx.files[f"{GUEST_ROOT}/data/CLM-1002.json"] = SIDE
    # Fork write: only the target claim moves.
    after_t = json.loads(DONE)
    after_s = json.loads(SIDE)
    d = promote_iff(
        target_before=json.loads(PENDING),
        target_after=after_t,
        side_before=json.loads(SIDE),
        side_after=after_s,
        original_target=json.loads(PENDING),
        original_side=json.loads(SIDE),
        baseline_target=json.loads(PENDING),
        baseline_side=json.loads(SIDE),
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
