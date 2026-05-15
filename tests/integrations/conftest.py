"""Shared fixtures for integration tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from agent.tools._proc import ProcResult


@dataclass
class FakeProcCall:
    argv: tuple[str, ...]
    result: ProcResult


class FakeProc:
    """Collects calls and returns canned ProcResult values."""

    def __init__(self, default: ProcResult | None = None) -> None:
        self.calls: list[FakeProcCall] = []
        self._responses: dict[str, ProcResult] = {}
        self._default = default or ProcResult(returncode=0)

    def register(self, binary: str, result: ProcResult) -> None:
        self._responses[binary] = result

    async def __call__(
        self,
        argv: Sequence[str],
        *,
        timeout: float = 10.0,
        capture_stdout: bool = False,
        stdin_data: bytes | None = None,
        env: dict | None = None,
    ) -> ProcResult:
        self.calls.append(FakeProcCall(argv=tuple(argv), result=ProcResult(0)))
        binary = argv[0] if argv else ""
        return self._responses.get(binary, self._default)


@pytest.fixture
def fake_proc(monkeypatch: pytest.MonkeyPatch) -> FakeProc:
    """Monkeypatch agent.tools._proc.run with a FakeProc instance."""
    fp = FakeProc()
    monkeypatch.setattr("agent.tools._proc.run", fp)
    return fp


@pytest.fixture
def mock_app_state() -> MagicMock:
    """Minimal AppState mock for integration tests."""
    state = MagicMock()
    state.config.integrations.enabled = ()
    state.config.integrations.mako_app_name = "hyprland-agent"
    state.config.integrations.binary_overrides = {}
    return state
