"""Tests for RPC dispatch table completeness and basic handler behavior."""

from __future__ import annotations

import pytest

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
