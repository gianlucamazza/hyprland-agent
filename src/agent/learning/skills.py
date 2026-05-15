"""Skill library: extract reusable action sequences from successful runs."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.daemon.store import RunStore
    from agent.memory.embedder import FastEmbedder

log = logging.getLogger(__name__)

_BORING_KINDS = {"screenshot"}


class SkillLibrary:
    def __init__(self, store: RunStore, embedder: FastEmbedder) -> None:
        self._store = store
        self._embedder = embedder

    async def extract_candidate(self, run_id: str) -> str | None:
        """Extract a skill draft from a successful run. Returns skill_id or None."""
        try:
            record = await self._store.get_run(run_id)
            if record is None:
                return None

            action_kinds = [
                ev.payload.get("kind", "?")
                for ev in record.events
                if ev.kind == "action" and ev.payload.get("kind") not in _BORING_KINDS
            ]
            if not action_kinds:
                return None

            task = record.task
            name = f"{task[:40]} ({', '.join(action_kinds[:3])})"
            description = (
                f"Sequence of {len(action_kinds)} action(s) for: {task}. "
                f"Steps: {', '.join(action_kinds)}."
            )
            actions_json = json.dumps(action_kinds)
            skill_id = hashlib.md5(f"{task}|{actions_json}".encode()).hexdigest()

            await self._store.insert_skill(
                skill_id=skill_id,
                name=name,
                description=description,
                actions_json=actions_json,
                source_run_id=run_id,
            )

            try:
                embs = await self._embedder.embed([f"{task} {description}"])
                await self._store.insert_skill_vec(skill_id, embs[0])
            except Exception as exc:
                log.debug("Skill embedding failed: %s", exc)

            log.debug("Extracted skill %s from run %s", skill_id, run_id)
            return skill_id
        except Exception as exc:
            log.warning("Skill extraction failed for run %s: %s", run_id, exc)
            return None

    async def rank_for_task(self, task: str, k: int = 5) -> list[dict]:
        """Return up to *k* approved skills ranked by similarity to *task*."""
        try:
            embs = await self._embedder.embed([task])
            return await self._store.query_skills_by_vec(
                embs[0], k=k, status="approved"
            )
        except Exception as exc:
            log.warning("Skill ranking failed: %s", exc)
            return []

    async def record_use(self, skill_id: str, run_id: str, outcome: str) -> None:
        await self._store.record_skill_outcome(skill_id, run_id, outcome)
