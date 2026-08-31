"""Live Solari is a later one-shot after merge — not part of this test job.

These tests exist so a leftover key in the environment cannot spend credits.
"""

from __future__ import annotations

import os

import pytest


def test_live_is_not_this_job():
    # Even if someone exported a key, pytest must not create VMs.
    if os.environ.get("SOLARI_API_KEY"):
        assert os.environ.get("SOLARI_ARENA_LIVE") != "1"
    pytest.skip("inconclusive: live serial is a later one-shot after merge, not this job")
