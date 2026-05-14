"""RunModal — modal screen to submit a new task to the daemon."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Switch

from agent.ipc.protocol import RpcMethod

_LABELS = {
    "claude": "Claude",
    "openai": "OpenAI",
    "moonshot": "Kimi",
    "groq": "Groq",
    "together": "Together",
    "zai": "Z.AI",
    "qwen": "Qwen",
}


def _brain_options() -> list[tuple[str, str]]:
    try:
        from agent.brain.router import selectable_providers

        providers = selectable_providers()
    except Exception:
        providers = ["claude", "openai", "moonshot", "groq", "together", "zai", "qwen"]
    return [("Auto", "auto"), *[(_LABELS[p], p) for p in providers]]


class RunModal(ModalScreen[str | None]):
    """Modal that collects task params and submits run_task RPC.

    Dismisses with run_id on success, or None on cancel.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    RunModal {
        align: center middle;
    }
    RunModal > Grid {
        grid-size: 2;
        grid-gutter: 1 2;
        padding: 1 2;
        width: 70;
        height: 16;
        border: double $accent;
        background: $surface;
    }
    RunModal Label {
        height: 1;
        content-align: right middle;
    }
    RunModal #btn-row {
        column-span: 2;
        layout: horizontal;
        align: right middle;
        height: 3;
    }
    RunModal Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Grid():
            yield Label("Task:")
            yield Input(placeholder="Natural-language task description", id="task-input")
            yield Label("Brain:")
            yield Select(
                _brain_options(),
                id="brain-select",
                value="auto",
            )
            yield Label("Dry run:")
            yield Switch(id="dry-run", value=False)
            with Grid(id="btn-row"):
                yield Button("Run", variant="primary", id="run-btn")
                yield Button("Cancel", id="cancel-btn")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        task = self.query_one("#task-input", Input).value.strip()
        if not task:
            self.query_one("#task-input", Input).focus()
            return
        brain_val = self.query_one("#brain-select", Select).value
        brain = str(brain_val) if brain_val is not Select.BLANK else "auto"
        dry_run = self.query_one("#dry-run", Switch).value
        conn = self.app._conn  # type: ignore[attr-defined]
        try:
            result = await conn.request(
                RpcMethod.run_task,
                {"task": task, "brain": brain, "dry_run": dry_run},
            )
            self.dismiss(result.get("run_id"))
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_cancel(self) -> None:
        self.dismiss(None)
