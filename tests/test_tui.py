"""Tests for the Textual TUI — smoke and layout snapshot."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.tui.app import AgentApp, ErrorScreen


# ── Smoke: daemon unavailable ────────────────────────────────────────────────


async def test_tui_shows_error_screen_when_daemon_down(tmp_path: Path) -> None:
    """AgentApp must show ErrorScreen (not crash) when socket doesn't exist."""
    app = AgentApp(socket_path=tmp_path / "no.sock")
    async with app.run_test(headless=True, size=(80, 24)) as pilot:
        await pilot.pause(0.2)
        assert isinstance(app.screen, ErrorScreen)


async def test_tui_error_screen_has_error_widget(tmp_path: Path) -> None:
    """ErrorScreen must contain the #error-msg widget."""
    app = AgentApp(socket_path=tmp_path / "no.sock")
    async with app.run_test(headless=True, size=(80, 24)) as pilot:
        await pilot.pause(0.2)
        # widget exists ↔ we are on ErrorScreen showing the error message
        assert app.screen.query_one("#error-msg") is not None


# ── Binding presence ─────────────────────────────────────────────────────────


def test_tui_bindings_present() -> None:
    app = AgentApp(socket_path=Path("/nonexistent"))
    keys = {b.key for b in app.BINDINGS}
    assert "ctrl+r" in keys
    assert "ctrl+k" in keys
    assert "ctrl+l" in keys
    assert "ctrl+q" in keys


# ── Import-graph: tui must not import daemon ──────────────────────────────────


def test_tui_does_not_import_daemon() -> None:
    import subprocess, sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import agent.tui.app;"
                "import sys;"
                "bad = [k for k in sys.modules if k.startswith('agent.daemon')];"
                "print(bad)"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]", f"daemon modules imported: {result.stdout.strip()}"


# ── Snapshot: ErrorScreen layout ─────────────────────────────────────────────


def test_tui_error_screen_snapshot(snap_compare) -> None:
    """Snapshot the ErrorScreen layout (appears when daemon is down).

    Uses a fixed path so the snapshot is deterministic across runs.
    """
    app = AgentApp(socket_path=Path("/run/user/0/hyprland-agent-snap-test.sock"))
    assert snap_compare(app, run_before=_wait_for_error_screen)


async def _wait_for_error_screen(pilot) -> None:
    await pilot.pause(0.3)


