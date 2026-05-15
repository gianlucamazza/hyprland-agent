"""Episodic memory: ingest run trajectories and recall similar past episodes."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.daemon.store import RunStore
    from agent.memory.embedder import FastEmbedder

log = logging.getLogger(__name__)


@dataclass
class Episode:
    run_id: str
    task: str
    outcome: str
    summary: str
    context_class: str | None = None
    distance: float | None = None

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "outcome": self.outcome,
            "summary": self.summary,
        }


class EpisodicMemory:
    def __init__(self, store: RunStore, embedder: FastEmbedder) -> None:
        self._store = store
        self._embedder = embedder

    async def ingest(self, run_id: str) -> None:
        """Ingest a completed run into episodic memory."""
        try:
            record = await self._store.get_run(run_id)
            if record is None:
                return
            task = record.task
            events = record.events

            # Build action sequence for summary
            action_kinds: list[str] = []
            context_class: str | None = None
            blocked_count = 0
            rejected_count = 0

            for ev in events:
                if ev.kind == "action":
                    action_kinds.append(ev.payload.get("kind", "?"))
                elif ev.kind == "action_result":
                    if ev.payload.get("blocked"):
                        blocked_count += 1
                    if ev.payload.get("rejected"):
                        rejected_count += 1
                elif ev.kind == "state":
                    active = ev.payload.get("active")
                    if active and context_class is None:
                        context_class = active.get("class")

            summary_parts = [f"{len(action_kinds)} actions: {', '.join(action_kinds[:8])}"]
            if blocked_count:
                summary_parts.append(f"{blocked_count} blocked")
            if rejected_count:
                summary_parts.append(f"{rejected_count} rejected")
            summary = "; ".join(summary_parts)

            # Get outcome from run_outcomes table (via store analytics or use status)
            outcome = record.status.value  # fallback
            try:
                analytics = await self._store.list_analytics(days=9999)
                # outcomes per run_id not directly available; use status mapping
            except Exception as exc:
                log.debug("analytics fetch failed during ingest: %s", exc)
            # Map status to outcome for episodic use
            _STATUS_TO_OUTCOME = {
                "completed": "success",
                "aborted": "failure",
                "errored": "failure",
            }
            outcome = _STATUS_TO_OUTCOME.get(record.status.value, record.status.value)

            actions_json = json.dumps([k for k in action_kinds])

            # Embed and persist
            try:
                text_to_embed = f"{task} | {summary}"
                embeddings = await self._embedder.embed([text_to_embed])
                emb = embeddings[0]
            except Exception as exc:
                log.warning("Embedding failed for run %s: %s", run_id, exc)
                emb = None

            await self._store.insert_episode(
                run_id=run_id,
                task=task,
                outcome=outcome,
                summary=summary,
                context_class=context_class,
                actions_json=actions_json,
            )
            if emb is not None:
                await self._store.insert_episode_vec(run_id, emb)

            log.debug("Ingested episode for run %s (outcome=%s)", run_id, outcome)
        except Exception as exc:
            log.warning("Failed to ingest episode for run %s: %s", run_id, exc)

    async def recall(
        self,
        task: str,
        k: int = 3,
        filter_failure: bool = True,
    ) -> list[Episode]:
        """Return up to *k* episodes semantically similar to *task*."""
        try:
            embeddings = await self._embedder.embed([task])
            emb = embeddings[0]
        except Exception as exc:
            log.warning("Embedding failed for recall: %s", exc)
            return []

        exclude = "failure" if filter_failure else None
        try:
            rows = await self._store.query_episodes_by_vec(emb, k=k, exclude_outcome=exclude)
        except Exception as exc:
            log.warning("Episode recall failed: %s", exc)
            return []

        return [
            Episode(
                run_id=r["run_id"],
                task=r["task"],
                outcome=r["outcome"],
                summary=r["summary"],
                context_class=r.get("context_class"),
                distance=r.get("dist"),
            )
            for r in rows
        ]
