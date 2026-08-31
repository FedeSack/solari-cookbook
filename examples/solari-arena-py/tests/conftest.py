from __future__ import annotations

import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PORTAL = ROOT / "portal"
if str(PORTAL) not in sys.path:
    sys.path.insert(0, str(PORTAL))

# Budget lock: pytest must never touch api.getsolari.com.
_BLOCKED = ("api.getsolari.com", "preview.getsolari.com")


def _blocked(url: object) -> bool:
    text = str(url).lower()
    return any(host in text for host in _BLOCKED)


def pytest_configure(config) -> None:
    import urllib.request

    real_urlopen = urllib.request.urlopen

    def guarded_urlopen(url, *args, **kwargs):  # noqa: ANN001
        if _blocked(url):
            raise URLError("blocked: tests must not call Solari (budget lock)")
        return real_urlopen(url, *args, **kwargs)

    urllib.request.urlopen = guarded_urlopen

    try:
        import httpx
    except ImportError:
        return

    real_request = httpx.AsyncClient.request

    async def guarded_request(self, method, url, *args, **kwargs):  # noqa: ANN001
        if _blocked(url):
            raise RuntimeError("blocked: tests must not call Solari (budget lock)")
        return await real_request(self, method, url, *args, **kwargs)

    httpx.AsyncClient.request = guarded_request


def start_portal(port: int):
    import server as clinic

    httpd = ThreadingHTTPServer(("127.0.0.1", port), clinic.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread
