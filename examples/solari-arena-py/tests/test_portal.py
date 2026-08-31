"""Local portal + FILE/HTTP oracle. Still no Solari key."""

from __future__ import annotations

import json
import socket
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import pytest

from conftest import start_portal

_PENDING_1001 = {
    "claimId": "CLM-1001",
    "status": "pending",
    "member": "SYNTHETIC-A",
    "amountUsd": 120.0,
    "watermark": "SYNTHETIC",
}
_PENDING_1002 = {
    "claimId": "CLM-1002",
    "status": "pending",
    "member": "SYNTHETIC-B",
    "amountUsd": 88.5,
    "watermark": "SYNTHETIC",
}
_DATA = Path(__file__).resolve().parents[1] / "portal" / "data"


def _reset_claims() -> None:
    (_DATA / "CLM-1001.json").write_text(json.dumps(_PENDING_1001, indent=2) + "\n")
    (_DATA / "CLM-1002.json").write_text(json.dumps(_PENDING_1002, indent=2) + "\n")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def portal():
    _reset_claims()
    port = _free_port()
    httpd, thread = start_portal(port)
    base = f"http://127.0.0.1:{port}"
    yield base
    httpd.shutdown()
    thread.join(timeout=2)
    _reset_claims()


def test_login_is_real_dom_and_required(portal):
    html = urlopen(portal + "/", timeout=3).read().decode("utf-8")
    assert 'id="username"' in html
    assert 'id="password"' in html
    assert 'id="login-submit"' in html
    assert "SYNTHETIC" in html
    # Worklist without a cookie bounces home.
    with urlopen(portal + "/worklist.html", timeout=3) as resp:
        # urllib follows the 302 to /
        body = resp.read().decode("utf-8")
    assert "Sign in" in body


def test_file_and_http_oracle_agree(portal):
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    login = Request(
        portal + "/login?next=/worklist.html?claimId=CLM-1001",
        data=urlencode({"username": "clerk", "password": "synthetic"}).encode(),
        method="POST",
    )
    opener.open(login, timeout=3)

    before = json.loads(opener.open(portal + "/api/claims/CLM-1001", timeout=3).read())
    side_before = json.loads(opener.open(portal + "/api/claims/CLM-1002", timeout=3).read())
    assert before["status"] == "pending"
    assert side_before["status"] == "pending"

    req = Request(
        portal + "/api/claims/CLM-1001",
        data=b'{"status":"processed"}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    after = json.loads(opener.open(req, timeout=3).read())
    side_after = json.loads(opener.open(portal + "/api/claims/CLM-1002", timeout=3).read())
    assert after["status"] == "processed"
    assert side_after == side_before

    from arena.oracle import score_oracle
    from arena.reasons import PASS_ORACLE

    v = score_oracle(
        target_before=before, target_after=after, side_before=side_before, side_after=side_after
    )
    assert v.reason == PASS_ORACLE


def test_pdf_is_synthetic(portal):
    data = urlopen(portal + "/eob.pdf", timeout=3).read()
    assert data.startswith(b"%PDF")
    assert b"SYNTHETIC" in data
    assert b"PHI" in data
