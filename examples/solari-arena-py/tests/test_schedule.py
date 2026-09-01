"""Dry-run schedule and cost ceiling. No API."""

from __future__ import annotations

import builtins

from arena.schedule import (
    FREE_BROWSER_USD_PER_HOUR,
    FREE_MONTHLY_CREDITS_USD,
    FREE_SANDBOX_1VCPU_2GB_USD_PER_HOUR,
    SHORTEST_STEPS,
    estimate_free_one_shot,
    format_dry_run,
)


def test_shortest_schedule_names_the_serial():
    blob = "\n".join(SHORTEST_STEPS)
    assert "policy CDP" in blob
    assert "from_snapshot" in blob
    assert "never record" in blob
    assert "policy vision" in blob
    assert "policy desktop" in blob
    assert "kill original" in blob


def test_estimate_uses_published_free_rates(monkeypatch):
    monkeypatch.delenv("SOLARI_ARENA_REPLAY", raising=False)
    env = estimate_free_one_shot(kind="desktop")
    assert env["monthly_credits_usd"] == FREE_MONTHLY_CREDITS_USD
    assert env["rates_usd_per_hour"]["browser"] == FREE_BROWSER_USD_PER_HOUR
    assert env["rates_usd_per_hour"]["sandbox_1vcpu_2gb"] == FREE_SANDBOX_1VCPU_2GB_USD_PER_HOUR
    assert env["from_snapshot_record"] is False
    assert env["desktop_record"] is False
    assert env["concurrent_vms"] == 1
    assert env["ceiling_usd"] > 0
    assert env["ceiling_usd"] < FREE_MONTHLY_CREDITS_USD


def test_replay_flag_does_not_record_on_fork(monkeypatch):
    monkeypatch.setenv("SOLARI_ARENA_REPLAY", "1")
    env = estimate_free_one_shot(kind="desktop")
    assert env["desktop_record"] is True
    assert env["browser_recording"] is True
    assert env["from_snapshot_record"] is False


def test_dry_run_text_and_no_sdk_import(monkeypatch, capsys):
    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name in {"solari_browser", "solari_sandbox", "solari_desktop"}:
            raise AssertionError(f"dry-run imported {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)
    from main import dry_run

    assert dry_run() == 0
    out = capsys.readouterr().out
    assert "no API" in out
    assert "create_desktop" in out
    assert "fromSnapshot=False" in out or "fromSnapshot=False" in out.replace(" ", "")
    assert "HALT_ILLEGIBLE" in out
    assert "ceiling USD" in out
