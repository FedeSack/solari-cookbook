"""AST contracts that would have caught the PR #1 billing and record bugs."""

from __future__ import annotations

import ast
import inspect

import main as arena_main
from arena import runtime


def _attr_calls(fn, name: str) -> int:
    tree = ast.parse(inspect.getsource(fn))
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == name:
                n += 1
    return n


def _kw_values(fn, keyword: str) -> list:
    tree = ast.parse(inspect.getsource(fn))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == keyword:
                    found.append(kw.value)
    return found


def test_end_vm_calls_kill_never_close():
    assert _attr_calls(runtime.end_vm, "kill") >= 1
    assert _attr_calls(runtime.end_vm, "close") == 0


def test_release_then_fork_kill_on_429_never_close():
    assert _attr_calls(runtime.release_then_fork, "close") == 0
    src = inspect.getsource(runtime.release_then_fork)
    assert "end_vm" in src
    assert "from_snapshot" in src


def test_fork_create_does_not_pass_record_keyword():
    for fn in (runtime.release_then_fork, arena_main._boot_fork_from_snap):
        for node in _kw_values(fn, "record"):
            raise AssertionError(f"{fn.__name__} passes record= {ast.dump(node)}")


def test_read_oracle_rejects_http():
    src = inspect.getsource(runtime.read_oracle)
    assert "read_claim_http" not in src
    assert "must be file" in src
