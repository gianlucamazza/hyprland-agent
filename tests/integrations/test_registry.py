"""Tests for IntegrationRegistry — discovery, versioning, degraded state."""

from __future__ import annotations

import importlib.metadata
from unittest.mock import MagicMock, patch

import pytest

from agent.integrations import (
    CapabilitySpec,
    IntegrationRegistry,
)
from agent.schemas import Action, ActionKind, ActionResult


class _GoodIntegration:
    name = "good"

    def capabilities(self) -> list[CapabilitySpec]:
        return [CapabilitySpec(name="test.good")]

    async def setup(self, state) -> None:
        pass

    async def teardown(self) -> None:
        pass

    async def handle(self, action: Action) -> ActionResult | None:
        return None


class _BadSetupIntegration:
    name = "bad_setup"

    def capabilities(self) -> list[CapabilitySpec]:
        return [CapabilitySpec(name="test.bad")]

    async def setup(self, state) -> None:
        raise RuntimeError("setup failed intentionally")

    async def teardown(self) -> None:
        pass

    async def handle(self, action: Action) -> ActionResult | None:
        return None


class _WrongVersionIntegration:
    name = "wrong_version"

    def capabilities(self) -> list[CapabilitySpec]:
        return [CapabilitySpec(name="test.wrong", api_version="99.0")]

    async def setup(self, state) -> None:
        pass

    async def teardown(self) -> None:
        pass

    async def handle(self, action: Action) -> ActionResult | None:
        return None


def _make_ep(name: str, cls) -> MagicMock:
    ep = MagicMock(spec=importlib.metadata.EntryPoint)
    ep.name = name
    ep.load.return_value = cls
    return ep


@pytest.mark.asyncio
async def test_good_integration_loads():
    registry = IntegrationRegistry()
    eps = [_make_ep("good", _GoodIntegration)]
    with patch("importlib.metadata.entry_points", return_value=eps):
        await registry.load(MagicMock())
    assert registry.status()["good"] == "ready"


@pytest.mark.asyncio
async def test_bad_setup_degraded():
    registry = IntegrationRegistry()
    eps = [_make_ep("bad_setup", _BadSetupIntegration)]
    with patch("importlib.metadata.entry_points", return_value=eps):
        await registry.load(MagicMock())
    assert registry.status()["bad_setup"] == "degraded"


@pytest.mark.asyncio
async def test_wrong_api_version_skipped():
    registry = IntegrationRegistry()
    eps = [_make_ep("wrong_version", _WrongVersionIntegration)]
    with patch("importlib.metadata.entry_points", return_value=eps):
        await registry.load(MagicMock())
    assert registry.status().get("wrong_version") == "missing"


@pytest.mark.asyncio
async def test_enabled_filter():
    registry = IntegrationRegistry()
    eps = [
        _make_ep("good", _GoodIntegration),
        _make_ep("bad_setup", _BadSetupIntegration),
    ]
    with patch("importlib.metadata.entry_points", return_value=eps):
        await registry.load(MagicMock(), enabled=("good",))
    assert "good" in registry.status()
    assert "bad_setup" not in registry.status()


@pytest.mark.asyncio
async def test_daemon_boots_without_integrations():
    """Registry with no loaded integrations returns empty status and no-op handle."""
    registry = IntegrationRegistry()
    assert registry.status() == {}
    action = Action(kind=ActionKind.notify, params={"message": "hi"})
    result = await registry.handle(action)
    assert result is None


@pytest.mark.asyncio
async def test_teardown_called():
    registry = IntegrationRegistry()
    torn_down: list[str] = []

    class _TeardownIntegration:
        name = "td"

        def capabilities(self):
            return [CapabilitySpec(name="test.td")]

        async def setup(self, state):
            pass

        async def teardown(self):
            torn_down.append("td")

        async def handle(self, action):
            return None

    eps = [_make_ep("td", _TeardownIntegration)]
    with patch("importlib.metadata.entry_points", return_value=eps):
        await registry.load(MagicMock())
    await registry.teardown()
    assert torn_down == ["td"]
