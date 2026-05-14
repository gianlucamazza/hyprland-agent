"""RunList — DataTable showing recent runs; updates live from Topic.runs events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.message import Message
from textual.widgets import DataTable

from agent.ipc.protocol import RpcMethod

if TYPE_CHECKING:
    from agent.client.connection import DaemonConnection
    from agent.tui.app import RunMsg

_STATUS_STYLE = {
    "running": "yellow",
    "completed": "green",
    "errored": "red",
    "aborted": "dim",
}


class RunList(DataTable):
    BORDER_TITLE = "Runs  (↑↓ to navigate)"

    class RunSelected(Message):
        def __init__(self, run_id: str) -> None:
            super().__init__()
            self.run_id = run_id

    def on_mount(self) -> None:
        self.add_column("ID", key="run_id", width=8)
        self.add_column("Kind", key="kind", width=4)
        self.add_column("Status", key="status", width=10)
        self.add_column("Brain", key="brain", width=8)
        self.add_column("Task", key="task")
        self.cursor_type = "row"

    async def refresh_runs(self, conn: DaemonConnection) -> None:
        result = await conn.request(RpcMethod.list_runs, {"limit": 20})
        self.clear()
        for r in reversed(result.get("runs", [])):
            self._add_run(r)

    def _add_run(self, r: dict[str, Any]) -> None:
        run_id = r["run_id"]
        status = r.get("status", "?")
        style = _STATUS_STYLE.get(status, "")
        self.add_row(
            run_id[:8],
            r.get("kind", "run"),
            f"[{style}]{status}[/{style}]" if style else status,
            r.get("brain", "?"),
            r.get("task", "")[:60],
            key=run_id,
        )

    def on_run_msg(self, msg: RunMsg) -> None:
        payload = msg.payload
        kind = payload.get("kind", "")
        run_id = payload.get("run_id", "")
        if kind in ("run_started", "plan_started"):
            self._add_run(
                {
                    "run_id": run_id,
                    "kind": payload.get("entry_kind", "run"),
                    "status": "running",
                    "brain": payload.get("brain", "?"),
                    "task": payload.get("task", ""),
                }
            )
        elif kind in (
            "run_completed",
            "run_aborted",
            "run_errored",
            "plan_completed",
            "plan_aborted",
            "plan_errored",
        ):
            _map = {
                "run_completed": "completed",
                "run_aborted": "aborted",
                "run_errored": "errored",
                "plan_completed": "completed",
                "plan_aborted": "aborted",
                "plan_errored": "errored",
            }
            new_status = _map[kind]
            style = _STATUS_STYLE.get(new_status, "")
            cell_val = f"[{style}]{new_status}[/{style}]" if style else new_status
            try:
                self.update_cell(run_id, "status", cell_val)
            except Exception:
                pass

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key and event.row_key.value:
            self.post_message(self.RunSelected(str(event.row_key.value)))
