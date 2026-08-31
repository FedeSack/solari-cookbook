"""Live serial only when a key is present and SOLARI_ARENA_LIVE=1.

Without a key this skips and the rest of the suite still passes.
Never print the key.
"""

from __future__ import annotations

import os

import pytest


def test_live_shortest_or_skip():
    if not os.environ.get("SOLARI_API_KEY"):
        pytest.skip("inconclusive: no SOLARI_API_KEY; live skipped")
    if os.environ.get("SOLARI_ARENA_LIVE") != "1":
        pytest.skip("inconclusive: live skipped (set SOLARI_ARENA_LIVE=1 for the shortest serial)")

    # Gate, not a score. 0 = serial finished; 2 = ABORT_CONCURRENCY.
    # This path spends credits; CI must keep SOLARI_API_KEY empty.
    from main import run_live

    code = __import__("asyncio").run(run_live(shortest=True))
    assert code in (0, 2)
