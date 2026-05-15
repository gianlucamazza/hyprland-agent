"""Tests for the Textual TUI — smoke and layout snapshot."""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.widgets import Input

from agent.tui.app import AgentApp, ErrorScreen
from agent.tui.widgets.run_modal import RunModal

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
    import subprocess
    import sys

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


# ── RunModal: input accepts typed text ───────────────────────────────────────


class _ModalHost(App[None]):
    """Minimal host that immediately pushes RunModal without a daemon."""

    async def on_mount(self) -> None:
        await self.push_screen(RunModal())


async def test_run_modal_input_accepts_text() -> None:
    """RunModal #task-input must display characters as the user types."""
    app = _ModalHost()
    async with app.run_test(headless=True, size=(80, 24)) as pilot:
        await pilot.pause(0.2)
        assert isinstance(app.screen, RunModal), "RunModal should be the active screen"
        inp = app.screen.query_one("#task-input", Input)
        assert app.screen.focused is inp, "focus should land on #task-input via AUTO_FOCUS"
        await pilot.press("h", "e", "l", "l", "o")
        await pilot.pause(0.05)
        assert inp.value == "hello", f"expected 'hello', got {inp.value!r}"
