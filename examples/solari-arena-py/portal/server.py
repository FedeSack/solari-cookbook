#!/usr/bin/env python3
"""Synthetic clinic portal.

`python -m http.server` is GET-only. The FILE/HTTP oracle needs POST to
mutate claim JSON, so this is the stdlib server plus two routes. Same
hosting pattern as sandbox-port-preview: write files, bind a port, mint
a preview URL.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
COOKIE = "clinic_session=clerk"
USER = "clerk"
PASSWORD = "synthetic"

MINIMAL_PDF = (
    b"%PDF-1.1\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 73>>stream\n"
    b"BT /F1 16 Tf 72 720 Td (SYNTHETIC EOB -- NO PHI) Tj ET\n"
    b"endstream\nendobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF\n"
)


def _claim_path(claim_id: str) -> Path:
    if "/" in claim_id or ".." in claim_id or not claim_id.startswith("CLM-"):
        raise ValueError("refusing claim id")
    return DATA / f"{claim_id}.json"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("portal: " + (fmt % args) + "\n")

    def _authed(self) -> bool:
        cookie = self.headers.get("Cookie") or ""
        return COOKIE.split("=", 1)[0] + "=" in cookie and "clerk" in cookie

    def _send(
        self, code: int, body: bytes, content_type: str, extra: Optional[List[Tuple[str, str]]] = None
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra or []:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self) -> None:  # noqa: N802  # stdlib name
        parsed = urlparse(self.path)
        if parsed.path == "/eob.pdf":
            pdf = (ROOT / "eob.pdf")
            body = pdf.read_bytes() if pdf.exists() else MINIMAL_PDF
            self._send(200, body, "application/pdf")
            return
        if parsed.path.startswith("/api/claims/"):
            claim_id = parsed.path.rsplit("/", 1)[-1]
            try:
                path = _claim_path(claim_id)
            except ValueError:
                self._send(400, b'{"error":"bad claim"}', "application/json")
                return
            if not path.exists():
                self._send(404, b'{"error":"missing"}', "application/json")
                return
            self._send(200, path.read_bytes(), "application/json")
            return
        if parsed.path in ("/worklist.html", "/worklist"):
            if not self._authed():
                loc = "/" + (("?" + parsed.query) if parsed.query else "")
                self._send(302, b"", "text/plain", [("Location", loc)])
                return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802  # stdlib name
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            raw = self._read_body().decode("utf-8")
            form = parse_qs(raw)
            user = (form.get("username") or [""])[0]
            pw = (form.get("password") or [""])[0]
            qs = parse_qs(parsed.query)
            nxt = (qs.get("next") or ["/worklist.html"])[0]
            if user != USER or pw != PASSWORD:
                self._send(401, b"bad credentials", "text/plain")
                return
            if not nxt.startswith("/"):
                nxt = "/worklist.html"
            self._send(302, b"", "text/plain", [("Location", nxt), ("Set-Cookie", COOKIE + "; Path=/")])
            return
        if parsed.path.startswith("/api/claims/"):
            if not self._authed():
                self._send(401, b'{"error":"auth"}', "application/json")
                return
            claim_id = parsed.path.rsplit("/", 1)[-1]
            try:
                path = _claim_path(claim_id)
            except ValueError:
                self._send(400, b'{"error":"bad claim"}', "application/json")
                return
            if not path.exists():
                self._send(404, b'{"error":"missing"}', "application/json")
                return
            claim = json.loads(path.read_text(encoding="utf-8"))
            extra = {}
            raw = self._read_body()
            if raw:
                try:
                    extra = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    extra = {}
            claim["status"] = extra.get("status") or "processed"
            claim["processedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            path.write_text(json.dumps(claim, indent=2) + "\n", encoding="utf-8")
            self._send(200, json.dumps(claim).encode("utf-8"), "application/json")
            return
        self._send(404, b'{"error":"nope"}', "application/json")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "8765"))
    DATA.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"synthetic clinic on :{port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
