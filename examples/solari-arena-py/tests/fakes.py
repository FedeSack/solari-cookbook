"""In-process stand-ins for Solari handles. No HTTP, no credits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class FakePlanError(Exception):
    def __init__(self) -> None:
        super().__init__("This feature requires a different plan")
        self.status = 402
        self.code = "FeatureRequiresPlan"
        self.name = "PlanError"


class FakeConcurrencyError(Exception):
    def __init__(self) -> None:
        super().__init__("Concurrency limit exceeded")
        self.status = 429
        self.code = "ConcurrencyLimitExceeded"
        self.name = "ConcurrencyLimitError"


class FakeNoCapacity(Exception):
    def __init__(self) -> None:
        super().__init__("No desktop host available")
        self.status = 503
        self.code = "NoCapacityError"
        self.name = "NoCapacityError"


class FakeGatewayError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.name = "GatewayError"


@dataclass
class FakeHealth:
    ready: bool = True
    display: bool = True
    vnc: bool = True


class FakeFiles:
    def __init__(self, store: Dict[str, bytes]) -> None:
        self.store = store

    async def mkdir(self, path: str) -> None:
        return None

    async def write(self, path: str, data, mode: Optional[int] = None) -> None:
        self.store[path] = data if isinstance(data, bytes) else str(data).encode("utf-8")

    async def read(self, path: str) -> bytes:
        return self.store[path]

    async def read_text(self, path: str) -> str:
        return self.store[path].decode("utf-8")


class FakeCommands:
    def __init__(self, log: List[tuple]) -> None:
        self.log = log

    async def run(self, cmd: str, **kwargs: Any) -> Any:
        self.log.append(("commands.run", cmd, kwargs))

        @dataclass
        class _R:
            exitCode: int = 0
            stdout: str = ""
            stderr: str = ""

        return _R()


class FakeHandle:
    def __init__(self, kind: str, sid: str, files: Dict[str, bytes], calls: List[tuple]) -> None:
        self.kind = kind
        self.id = sid
        self.sessionId = sid
        self.streamUrl = f"wss://api.getsolari.com/stream/{sid}" if kind == "desktop" else ""
        self._files = files
        self._calls = calls
        self.files = FakeFiles(files)
        self.commands = FakeCommands(calls)
        self.paused = False
        self.killed = False

    async def connect(self) -> None:
        self._calls.append(("connect", self.id))

    async def health(self) -> FakeHealth:
        return FakeHealth()

    async def preview_url(self, port: int) -> Dict[str, str]:
        self._calls.append(("preview_url", port))
        return {"url": f"http://127.0.0.1:{port}"}

    async def snapshot(self, name: Optional[str] = None) -> str:
        self._calls.append(("snapshot", name))
        if self.killed:
            raise FakeGatewayError(409, "NotSnapshottable", "gone")
        return "snap_fake_1"

    async def pause(self) -> None:
        self._calls.append(("pause", self.id))
        self.paused = True

    async def resume(self) -> None:
        self._calls.append(("resume", self.id))
        self.paused = False

    async def kill(self) -> None:
        self._calls.append(("kill", self.id))
        self.killed = True

    async def close(self) -> None:
        self._calls.append(("close", self.id))


class FakeSandboxClient:
    """Mirrors the subset of SandboxClient the runner calls."""

    def __init__(
        self,
        *,
        desktop_ok: bool = True,
        pause_then_fork_ok: bool = True,
        record_from_snapshot_ok: bool = False,
    ) -> None:
        self.desktop_ok = desktop_ok
        self.pause_then_fork_ok = pause_then_fork_ok
        self.record_from_snapshot_ok = record_from_snapshot_ok
        self.calls: List[tuple] = []
        self.live: List[FakeHandle] = []
        self.files: Dict[str, bytes] = {}
        self._seq = 0

    def _next(self, kind: str) -> FakeHandle:
        self._seq += 1
        h = FakeHandle(kind, f"{kind}_{self._seq}", self.files, self.calls)
        self.live.append(h)
        return h

    async def create_desktop(self, **kwargs: Any) -> FakeHandle:
        self.calls.append(("create_desktop", kwargs))
        if kwargs.get("record") and kwargs.get("from_snapshot"):
            if not self.record_from_snapshot_ok:
                raise FakeGatewayError(400, "RecordingRequiresGoldenBoot", "record+fromSnapshot")
        if kwargs.get("from_snapshot") and not self.pause_then_fork_ok and self._original_still_live():
            raise FakeConcurrencyError()
        if not self.desktop_ok and not kwargs.get("from_snapshot"):
            raise FakePlanError()
        return self._next("desktop")

    async def create(self, **kwargs: Any) -> FakeHandle:
        self.calls.append(("create", kwargs))
        if kwargs.get("from_snapshot") and not self.pause_then_fork_ok and self._original_still_live():
            raise FakeConcurrencyError()
        return self._next("sandbox")

    def _original_still_live(self) -> bool:
        # When pause_then_fork_ok is False, pause does not free the Free 1-VM slot.
        for h in self.live:
            if h.killed:
                continue
            if h.paused and self.pause_then_fork_ok:
                continue
            return True
        return False

    async def aclose(self) -> None:
        self.calls.append(("aclose",))
