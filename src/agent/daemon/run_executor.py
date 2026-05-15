"""Task queue, lifecycle management, and RunContext for agent runs."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent.daemon.audit_log import AuditLog
from agent.daemon.pubsub import PubSub
from agent.daemon.store import RunStore
from agent.ipc.protocol import Topic
from agent.schemas import RunEventRecord, RunKind, RunStatus, RunSummary

log = logging.getLogger(__name__)


@dataclass
class RunContext:
    """Injected into orchestrator.run() to decouple it from storage."""

    run_id: str
    _emit_fn: Callable[[str, dict[str, Any]], Awaitable[None]] = field(repr=False)

    async def emit(self, kind: str, payload: dict[str, Any] | None = None) -> None:
        await self._emit_fn(kind, payload or {})


class RunExecutor:
    """Manages concurrent agent runs: submit, cancel, track lifecycle."""

    def __init__(self, store: RunStore, pubsub: PubSub, audit: AuditLog) -> None:
        self._store = store
        self._pubsub = pubsub
        self._audit = audit
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._seq: dict[str, int] = {}
        self.app_state: Any = None  # set by AppState.open() after construction

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit(self, task: str, brain_name: str) -> str:
        """Start a run asynchronously. Returns the run_id immediately."""
        return await self._submit(RunKind.run, task, brain_name)

    async def submit_plan(self, task: str, brain_name: str) -> str:
        """Start a planning task asynchronously. Returns the run_id immediately."""
        return await self._submit(RunKind.plan, task, brain_name)

    async def _submit(self, kind: RunKind, task: str, brain_name: str) -> str:
        from agent.brain.router import get_brain

        run_id = str(uuid.uuid4())
        summary = RunSummary(
            run_id=run_id,
            kind=kind,
            task=task,
            brain=brain_name,
            status=RunStatus.running,
            started_at=time.time(),
        )
        await self._store.insert_run(summary)
        self._seq[run_id] = 0

        brain = get_brain(brain_name)
        ctx = RunContext(run_id=run_id, _emit_fn=self._make_emit(run_id))

        t = asyncio.create_task(self._run_task(run_id, kind, task, brain, ctx))
        self._tasks[run_id] = t
        t.add_done_callback(lambda _: self._tasks.pop(run_id, None))

        await self._publish(
            run_id,
            f"{kind.value}_started",
            {"entry_kind": kind.value, "task": task, "brain": brain_name},
        )
        log.info(
            "%s %s started (task=%r brain=%s)",
            kind.value.capitalize(),
            run_id,
            task,
            brain_name,
        )
        return run_id

    async def cancel(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def active_run_ids(self) -> list[str]:
        return [rid for rid, t in self._tasks.items() if not t.done()]

    async def close(self) -> None:
        """Cancel all running tasks and wait for them to finish."""
        for task in list(self._tasks.values()):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _make_emit(
        self, run_id: str
    ) -> Callable[[str, dict[str, Any]], Awaitable[None]]:
        async def _emit(kind: str, payload: dict[str, Any]) -> None:
            seq = self._seq.get(run_id, 0)
            self._seq[run_id] = seq + 1
            event = RunEventRecord(seq=seq, ts=time.time(), kind=kind, payload=payload)
            await self._store.append_event(run_id, event)
            await self._audit.write(
                {"run_id": run_id, "seq": seq, "kind": kind, **payload}
            )
            await self._publish(run_id, kind, payload)

        return _emit

    async def _publish(self, run_id: str, kind: str, payload: dict[str, Any]) -> None:
        await self._pubsub.publish(
            Topic.runs,
            {"run_id": run_id, "kind": kind, **payload},
        )

    async def _run_task(
        self,
        run_id: str,
        kind: RunKind,
        task: str,
        brain: Any,
        ctx: RunContext,
    ) -> None:
        from agent.learning.outcome import derive_from_status
        from agent.orchestrator import plan as _plan
        from agent.orchestrator import run as _run

        _RUN_TIMEOUT = 300.0  # 5 minutes hard cap
        orchestrate = _plan if kind == RunKind.plan else _run
        t_start = time.time()

        final_status = RunStatus.errored
        try:
            await asyncio.wait_for(
                orchestrate(task, brain, ctx=ctx, app_state=self.app_state),
                timeout=_RUN_TIMEOUT,
            )
            final_status = RunStatus.completed
            await self._store.update_run_status(run_id, RunStatus.completed)
            await self._publish(run_id, f"{kind.value}_completed", {})
            log.info("%s %s completed", kind.value.capitalize(), run_id)
        except asyncio.TimeoutError:
            final_status = RunStatus.errored
            msg = f"{kind.value.capitalize()} timed out after {int(_RUN_TIMEOUT)}s"
            await self._store.update_run_status(run_id, RunStatus.errored, error=msg)
            await self._publish(run_id, f"{kind.value}_errored", {"error": msg})
            log.error("%s %s timed out", kind.value.capitalize(), run_id)
        except asyncio.CancelledError:
            final_status = RunStatus.aborted
            await self._store.update_run_status(run_id, RunStatus.aborted)
            await self._publish(run_id, f"{kind.value}_aborted", {})
            log.info("%s %s aborted", kind.value.capitalize(), run_id)
            raise
        except Exception as exc:
            final_status = RunStatus.errored
            await self._store.update_run_status(
                run_id, RunStatus.errored, error=str(exc)
            )
            await self._publish(run_id, f"{kind.value}_errored", {"error": str(exc)})
            log.error("%s %s errored: %s", kind.value.capitalize(), run_id, exc)
        finally:
            duration_s = time.time() - t_start
            await self._store.update_run_metrics(run_id, duration_s=duration_s)
            outcome, score = derive_from_status(final_status)
            await self._store.upsert_run_outcome(run_id, outcome, score, "derived")
            self._seq.pop(run_id, None)
