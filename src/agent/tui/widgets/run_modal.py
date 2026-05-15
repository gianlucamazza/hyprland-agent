"""RunModal — modal screen to submit a new task to the daemon."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select

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
    AUTO_FOCUS = "#task-input"
    DEFAULT_CSS = """
    RunModal {
        align: center middle;
    }
    RunModal > Vertical {
        width: 72;
        height: auto;
        padding: 1 2;
        border: double $accent;
        background: $surface;
    }
    RunModal .row {
        height: auto;
        margin-bottom: 1;
    }
    RunModal .row > Label {
        width: 8;
        content-align: right middle;
        padding-top: 1;
    }
    RunModal #task-input, RunModal #brain-select {
        width: 1fr;
    }
    RunModal #btn-row {
        height: 3;
        align: right middle;
    }
    RunModal #btn-row Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(classes="row"):
                yield Label("Task:")
                yield Input(
                    placeholder="Natural-language task description", id="task-input"
                )
            with Horizontal(classes="row"):
                yield Label("Brain:")
                yield Select(
                    _brain_options(),
                    id="brain-select",
                    value="auto",
                )
            with Horizontal(id="btn-row"):
                yield Button("Plan", id="plan-btn")
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
        method = (
            RpcMethod.plan_task if event.button.id == "plan-btn" else RpcMethod.run_task
        )
        conn = self.app._conn  # type: ignore[attr-defined]
        try:
            result = await conn.request(
                method,
                {"task": task, "brain": brain},
            )
            self.dismiss(result.get("run_id"))
        except Exception as exc:
            self.notify(str(exc), severity="error")

    def action_cancel(self) -> None:
        self.dismiss(None)
