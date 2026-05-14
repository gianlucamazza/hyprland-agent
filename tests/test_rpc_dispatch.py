"""Tests for RPC dispatch table completeness and basic handler behavior."""

from __future__ import annotations

import pytest

from agent.daemon import rpc
from agent.daemon.rpc import _DISPATCH
from agent.ipc.protocol import RpcMethod


def test_all_methods_have_handlers() -> None:
    """Every RpcMethod enum value must have a handler in _DISPATCH."""
    missing = [m for m in RpcMethod if m not in _DISPATCH]
    assert missing == [], f"No handler for: {missing}"


def test_no_extra_handlers() -> None:
    """Every key in _DISPATCH must be a valid RpcMethod."""
    invalid = [k for k in _DISPATCH if not isinstance(k, RpcMethod)]
    assert invalid == []


def test_all_handlers_are_callable() -> None:
    for method, handler in _DISPATCH.items():
        assert callable(handler), f"Handler for {method} is not callable"


@pytest.mark.asyncio
async def test_daemon_status_uses_package_version(monkeypatch: pytest.MonkeyPatch) -> None:
    class Executor:
        async def active_run_ids(self) -> list[str]:
            return []

    class State:
        executor = Executor()
        start_time = 1.0
        rules: list[object] = []

    monkeypatch.setattr(rpc, "_APP_VERSION", "9.9.9")

    result = await rpc._daemon_status(State(), {})

    assert result["version"] == "9.9.9"
