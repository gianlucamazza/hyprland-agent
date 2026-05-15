"""Shared daemon application state."""

from __future__ import annotations

import time

from agent.config import AgentConfig, load_config
from agent.daemon.audit_log import AuditLog
from agent.daemon.pubsub import PubSub
from agent.daemon.run_executor import RunExecutor
from agent.daemon.store import RunStore
from agent.memory.embedder import FastEmbedder
from agent.memory.episodic import EpisodicMemory
from agent.memory.ingest_consumer import EpisodicIngestor
from agent.schemas import Rule


class AppState:
    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config: AgentConfig = config or load_config()
        self.store = RunStore()
        self.pubsub = PubSub()
        self.audit = AuditLog(enabled=self.config.audit_log)
        self.executor = RunExecutor(self.store, self.pubsub, self.audit)
        self.rules: list[Rule] = []
        self.start_time: float = 0.0

        self.embedder = FastEmbedder(model_name=self.config.memory.embedder_model)
        self.episodic = EpisodicMemory(self.store, self.embedder)
        self.ingestor: EpisodicIngestor | None = None

    async def open(self) -> None:
        self.start_time = time.time()
        await self.store.open()
        await self.audit.open()
        self.executor.app_state = self
        if self.config.memory.enabled:
            self.ingestor = EpisodicIngestor(self.pubsub, self.episodic)
            await self.ingestor.start()

    async def close(self) -> None:
        if self.ingestor is not None:
            await self.ingestor.stop()
        await self.executor.close()
        await self.audit.close()
        await self.store.close()
