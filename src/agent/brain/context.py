"""BrainContext — structured context assembled before every brain.decide() call."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.awareness.working import WorkingMemory
    from agent.awareness.world_context import WorldSnapshot
    from agent.introspection.self_model import SelfModel


@dataclass
class BrainContext:
    """Bundles self-model, world snapshot, and working memory for the brain."""

    self_model: SelfModel
    world: WorldSnapshot
    working: WorkingMemory
    # P2 — filled by episodic recall; empty in P1
    recall: list[dict[str, Any]] = field(default_factory=list)
    # P3 — filled by reflection; empty in P1
    negative_reflections: list[str] = field(default_factory=list)

    def render_system_prompt(self) -> str:
        """Render structured system prompt from self-model and world state."""
        parts = [self.self_model.render_for_prompt()]
        world_lines = self.world.render_for_prompt()
        if world_lines:
            parts.append(world_lines)
        return "\n\n".join(parts)

    def render_user_preamble(self) -> str:
        """Render user-facing preamble with working memory and recall context."""
        parts: list[str] = []

        history = self.working.render()
        if history:
            parts.append(history)

        if self.recall:
            lines = ["## Similar past tasks"]
            for ep in self.recall[:3]:
                outcome = ep.get("outcome", "?")
                summary = ep.get("summary", "")
                task = ep.get("task", "")
                lines.append(f"- [{outcome}] {task}: {summary}")
            parts.append("\n".join(lines))

        if self.negative_reflections:
            lines = ["## Lessons from past failures"]
            for r in self.negative_reflections[:3]:
                lines.append(f"- {r}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts)
