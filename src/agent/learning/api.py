"""Learning API facade: context injection + proposal management."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from agent.awareness.world_context import WorldSnapshot
    from agent.brain.context import BrainContext
    from agent.daemon.state import AppState
    from agent.daemon.store import RunStore
    from agent.introspection.self_model import SelfModel
    from agent.memory.episodic import EpisodicMemory

log = logging.getLogger(__name__)

_LEARNED_RULES_PATH = Path.home() / ".config" / "hyprland-agent" / "learned_rules.yaml"
_ALLOWLIST_PATH = Path.home() / ".config" / "hyprland-agent" / "allowlist.yaml"


async def inject_context(
    state: AppState,
    task: str,
    self_model: SelfModel,
    world: WorldSnapshot,
) -> BrainContext:
    """Build a BrainContext enriched with episodic recall and reflections."""
    from agent.awareness.working import WorkingMemory
    from agent.brain.context import BrainContext

    recall: list[dict] = []
    negative_reflections: list[str] = []

    episodic: EpisodicMemory | None = getattr(state, "episodic", None)
    if episodic is not None:
        try:
            mem_cfg = getattr(state.config, "memory", None)
            k = mem_cfg.recall_k if mem_cfg is not None else 3
            episodes = await episodic.recall(task, k=k)
            recall = [ep.to_dict() for ep in episodes]
        except Exception as exc:
            log.warning("Episodic recall failed: %s", exc)

    store = getattr(state, "store", None)
    if store is not None:
        try:
            rows = await store.list_recent_reflections(polarity="negative", limit=20)
            negative_reflections = [r["text"] for r in rows[:3]]
        except Exception as exc:
            log.warning("Reflection fetch failed: %s", exc)

    return BrainContext(
        self_model=self_model,
        world=world,
        working=WorkingMemory(),
        recall=recall,
        negative_reflections=negative_reflections,
    )


async def list_proposals(
    kind: str,
    status: str | None,
    store: RunStore,
) -> list[dict[str, Any]]:
    """Return proposals of the given kind, optionally filtered by status."""
    kind = kind.lower()
    if kind == "skill":
        default_status = "draft"
        rows = await store.list_skills(status=status or default_status)
        return [
            {
                "id": r["skill_id"],
                "name": r["name"],
                "description": r["description"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    elif kind == "rule":
        default_status = "proposed"
        rows = await store.list_learned_rules(status=status or default_status)
        return [
            {
                "id": r["rule_id"],
                "confidence": r["confidence"],
                "hit_count": r["hit_count"],
                "status": r["status"],
                "proposed_at": r["proposed_at"],
                "yaml": r["yaml"],
            }
            for r in rows
        ]
    elif kind == "allowlist":
        default_status = "pending"
        rows = await store.list_allowlist_proposals(status=status or default_status)
        return [
            {
                "id": r["proposal_id"],
                "app_class": r["app_class"],
                "title_pat": r["title_pat"],
                "hit_count": r["hit_count"],
                "last_seen": r["last_seen"],
                "status": r["status"],
            }
            for r in rows
        ]
    else:
        raise ValueError(
            f"Unknown proposal kind: {kind!r} — expected skill|rule|allowlist"
        )


async def approve(
    kind: str,
    proposal_id: str,
    store: RunStore,
) -> dict[str, Any]:
    """Approve a learning proposal. Side effects depend on kind."""
    kind = kind.lower()
    if kind == "skill":
        await store.update_skill_status(proposal_id, "approved")
        return {"ok": True, "kind": "skill", "id": proposal_id, "status": "approved"}

    elif kind == "rule":
        rows = await store.list_learned_rules(status=None)
        rule = next((r for r in rows if r["rule_id"] == proposal_id), None)
        if rule is None:
            raise KeyError(f"rule {proposal_id!r} not found")

        _append_learned_rule(rule["yaml"])
        await store.update_learned_rule_status(proposal_id, "approved")
        return {"ok": True, "kind": "rule", "id": proposal_id, "status": "approved"}

    elif kind == "allowlist":
        rows = await store.list_allowlist_proposals(status=None)
        prop = next(
            (r for r in rows if str(r["proposal_id"]) == str(proposal_id)), None
        )
        if prop is None:
            raise KeyError(f"allowlist proposal {proposal_id!r} not found")

        _append_allowlist_entry(prop["app_class"], prop["title_pat"])
        await store.update_allowlist_proposal_status(int(proposal_id), "approved")
        return {
            "ok": True,
            "kind": "allowlist",
            "id": proposal_id,
            "status": "approved",
        }
    else:
        raise ValueError(f"Unknown kind: {kind!r}")


async def reject(
    kind: str,
    proposal_id: str,
    store: RunStore,
    reason: str | None = None,
) -> dict[str, Any]:
    """Reject a learning proposal."""
    kind = kind.lower()
    if kind == "skill":
        await store.update_skill_status(proposal_id, "rejected")
    elif kind == "rule":
        await store.update_learned_rule_status(proposal_id, "rejected")
    elif kind == "allowlist":
        await store.update_allowlist_proposal_status(int(proposal_id), "rejected")
    else:
        raise ValueError(f"Unknown kind: {kind!r}")
    return {"ok": True, "kind": kind, "id": proposal_id, "status": "rejected"}


async def explain(
    kind: str,
    proposal_id: str,
    store: RunStore,
) -> dict[str, Any]:
    """Return a human-readable explanation of a proposal."""
    kind = kind.lower()
    if kind == "skill":
        rows = await store.list_skills(status=None)
        skill = next((r for r in rows if r["skill_id"] == proposal_id), None)
        if skill is None:
            raise KeyError(f"skill {proposal_id!r} not found")
        return {
            "kind": "skill",
            "id": proposal_id,
            "name": skill["name"],
            "description": skill["description"],
            "actions": skill["actions_json"],
            "status": skill["status"],
        }
    elif kind == "rule":
        rows = await store.list_learned_rules(status=None)
        rule = next((r for r in rows if r["rule_id"] == proposal_id), None)
        if rule is None:
            raise KeyError(f"rule {proposal_id!r} not found")
        return {
            "kind": "rule",
            "id": proposal_id,
            "confidence": rule["confidence"],
            "hit_count": rule["hit_count"],
            "yaml": rule["yaml"],
            "status": rule["status"],
        }
    elif kind == "allowlist":
        rows = await store.list_allowlist_proposals(status=None)
        prop = next(
            (r for r in rows if str(r["proposal_id"]) == str(proposal_id)), None
        )
        if prop is None:
            raise KeyError(f"allowlist proposal {proposal_id!r} not found")
        return {
            "kind": "allowlist",
            "id": proposal_id,
            "app_class": prop["app_class"],
            "title_pat": prop["title_pat"],
            "hit_count": prop["hit_count"],
            "status": prop["status"],
        }
    else:
        raise ValueError(f"Unknown kind: {kind!r}")


def _append_learned_rule(rule_yaml: str) -> None:
    """Append a rule block to learned_rules.yaml (create if missing)."""
    _LEARNED_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _LEARNED_RULES_PATH.exists():
        existing = yaml.safe_load(_LEARNED_RULES_PATH.read_text()) or {}
    else:
        existing = {}
    existing_rules: list = existing.get("rules", [])

    new_rules = (yaml.safe_load(rule_yaml) or {}).get("rules", [])
    existing_rules.extend(new_rules)
    _LEARNED_RULES_PATH.write_text(
        yaml.dump({"rules": existing_rules}, default_flow_style=False)
    )


def _append_allowlist_entry(app_class: str, title_pat: str) -> None:
    """Append an entry to allowlist.yaml (create if missing)."""
    _ALLOWLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _ALLOWLIST_PATH.exists():
        existing = yaml.safe_load(_ALLOWLIST_PATH.read_text()) or {}
    else:
        existing = {}
    allow: list = existing.get("allow", [])
    entry = {"class": app_class, "title": title_pat}
    if entry not in allow:
        allow.append(entry)
    _ALLOWLIST_PATH.write_text(yaml.dump({"allow": allow}, default_flow_style=False))
