"""Shared daemon application state."""

from __future__ import annotations

from agent.daemon.audit_log import AuditLog
from agent.daemon.pubsub import PubSub
from agent.daemon.run_executor import RunExecutor
from agent.daemon.store import RunStore
from agent.schemas import Rule


class AppState:
    def __init__(self) -> None:
        self.store = RunStore()
        self.pubsub = PubSub()
        self.audit = AuditLog()
        self.executor = RunExecutor(self.store, self.pubsub, self.audit)
        self.rules: list[Rule] = []
        self.start_time: float = 0.0

    async def open(self) -> None:
        import time

        self.start_time = time.time()
        await self.store.open()
        await self.audit.open()

    async def close(self) -> None:
        await self.executor.close()
        await self.audit.close()
        await self.store.close()
