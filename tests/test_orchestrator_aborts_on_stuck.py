"""Tests that orchestrator raises StuckError when loop detector fires."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from agent.awareness.meta_cognition import StuckError
from agent.schemas import Action, ActionKind, ScreenState


def _make_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (100, 80)).save(buf, format="PNG")
    return buf.getvalue()


def _make_state() -> ScreenState:
    return ScreenState(
        screenshot_png=_make_png(),
        width=100,
        height=80,
        active_window=None,
        windows=[],
    )


class _StuckBrain:
    """Returns the same click action every time → triggers loop detector."""

    async def decide(self, state, task, ctx):
        return [
            Action(kind=ActionKind.click, params={"x": 50, "y": 50}),
            Action(kind=ActionKind.click, params={"x": 50, "y": 50}),
            Action(kind=ActionKind.click, params={"x": 50, "y": 50}),
        ]


async def test_orchestrator_raises_stuck_error() -> None:
    from agent.orchestrator import run as _run

    state = _make_state()
    brain = _StuckBrain()

    with (
        patch("agent.orchestrator._build_state", return_value=(state, True)),
        patch(
            "agent.orchestrator._assemble_brain_context",
            return_value=MagicMock(
                working=MagicMock(record=lambda *a, **kw: None),
                render_system_prompt=MagicMock(return_value=""),
                render_user_preamble=MagicMock(return_value=""),
            ),
        ),
        patch(
            "agent.orchestrator._execute_action",
            new_callable=AsyncMock,
            return_value=MagicMock(
                dispatch_response=None,
                blocked=None,
                rejected=None,
                stdout=None,
                stderr=None,
                pre_hash=None,
                model_dump=lambda: {},
            ),
        ),
        patch(
            "agent.tools.screen.full", new_callable=AsyncMock, return_value=_make_png()
        ),
        patch("agent.safety.killswitch.is_stopped", return_value=False),
    ):
        with pytest.raises(StuckError):
            await _run("click repeatedly", brain)


async def test_orchestrator_no_stuck_with_varied_actions() -> None:
    from agent.orchestrator import run as _run
    from agent.schemas import ActionKind

    class _VarBrain:
        async def decide(self, state, task, ctx):
            return [
                Action(kind=ActionKind.click, params={"x": 10, "y": 10}),
                Action(kind=ActionKind.click, params={"x": 20, "y": 20}),
                Action(kind=ActionKind.dispatch, params={"cmd": "workspace 2"}),
            ]

    with (
        patch("agent.orchestrator._build_state", return_value=(_make_state(), True)),
        patch(
            "agent.orchestrator._assemble_brain_context",
            return_value=MagicMock(
                working=MagicMock(record=lambda *a, **kw: None),
            ),
        ),
        patch(
            "agent.orchestrator._execute_action",
            new_callable=AsyncMock,
            return_value=MagicMock(
                dispatch_response=None,
                blocked=None,
                rejected=None,
                stdout=None,
                stderr=None,
                pre_hash=None,
                model_dump=lambda: {},
            ),
        ),
        patch(
            "agent.tools.screen.full", new_callable=AsyncMock, return_value=_make_png()
        ),
        patch("agent.safety.killswitch.is_stopped", return_value=False),
    ):
        # Should complete without raising StuckError
        await _run("varied task", _VarBrain())
