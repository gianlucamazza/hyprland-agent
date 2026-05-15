"""Learning API facade: assembles BrainContext with episodic recall."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.awareness.world_context import WorldSnapshot
    from agent.brain.context import BrainContext
    from agent.daemon.state import AppState
    from agent.introspection.self_model import SelfModel
    from agent.memory.episodic import EpisodicMemory

log = logging.getLogger(__name__)


async def inject_context(
    state: AppState,
    task: str,
    self_model: SelfModel,
    world: WorldSnapshot,
) -> BrainContext:
    """Build a BrainContext enriched with episodic recall.

    Falls back to an empty recall list if episodic memory is unavailable.
    """
    from agent.awareness.working import WorkingMemory
    from agent.brain.context import BrainContext

    recall: list[dict] = []

    episodic: EpisodicMemory | None = getattr(state, "episodic", None)
    if episodic is not None:
        try:
            k = getattr(state.config, "memory", None)
            k = k.recall_k if k is not None else 3
            episodes = await episodic.recall(task, k=k)
            recall = [ep.to_dict() for ep in episodes]
        except Exception as exc:
            log.warning("Episodic recall failed: %s", exc)

    return BrainContext(
        self_model=self_model,
        world=world,
        working=WorkingMemory(),
        recall=recall,
    )
