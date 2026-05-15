"""Rule miner: discovers recurring action patterns and proposes rules."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from agent.daemon.store import RunStore

log = logging.getLogger(__name__)

_HIT_THRESHOLD = 3
_SUCCESS_RATE_THRESHOLD = 0.8


class RuleMiner:
    def __init__(self, store: RunStore) -> None:
        self._store = store

    async def mine(self, window_days: int = 7) -> int:
        """Mine rule candidates from recent successful runs. Returns proposals count."""
        cutoff = time.time() - window_days * 86400
        try:
            return await self._store._run_sync(self._do_mine, cutoff)
        except Exception as exc:
            log.warning("Rule mining failed: %s", exc)
            return 0

    def _do_mine(self, conn, cutoff: float) -> int:
        import sqlite3

        conn.row_factory = sqlite3.Row
        # Get successful run IDs in window
        rows = conn.execute(
            "SELECT r.run_id, r.task, e.context_class"
            " FROM runs r"
            " JOIN run_outcomes o ON o.run_id = r.run_id"
            " LEFT JOIN episodes e ON e.run_id = r.run_id"
            " WHERE o.outcome = 'success' AND r.started_at >= ?"
            " ORDER BY r.started_at DESC",
            (cutoff,),
        ).fetchall()

        # Count (context_class, action_sequence) pairs across runs
        counter: Counter[tuple[str, str]] = Counter()
        run_ids_map: dict[tuple[str, str], list[str]] = {}
        for row in rows:
            run_id = row["run_id"]
            context_class = row["context_class"] or "any"
            events = conn.execute(
                "SELECT kind, payload_json FROM run_events"
                " WHERE run_id=? AND kind='action' ORDER BY seq",
                (run_id,),
            ).fetchall()
            action_kinds = [
                json.loads(e["payload_json"]).get("kind", "?") for e in events
            ]
            if not action_kinds:
                continue
            key = (context_class, json.dumps(action_kinds))
            counter[key] += 1
            run_ids_map.setdefault(key, []).append(run_id)

        proposed = 0
        for (context_class, actions_json), count in counter.items():
            if count < _HIT_THRESHOLD:
                continue
            action_kinds = json.loads(actions_json)
            rule_yaml = yaml.dump(
                {
                    "rules": [
                        {
                            "on": "openwindow",
                            "match": {"class": context_class},
                            "actions": [
                                {"log": f"auto: {', '.join(action_kinds[:3])}"}
                            ],
                        }
                    ]
                },
                default_flow_style=False,
            )
            rule_id = hashlib.md5(
                f"{context_class}|{actions_json}".encode()
            ).hexdigest()
            source_runs = json.dumps(run_ids_map[(context_class, actions_json)][:5])
            conn.execute(
                "INSERT OR IGNORE INTO learned_rules"
                " (rule_id, yaml, confidence, source_runs, status, proposed_at)"
                " VALUES (?,?,?,?,'proposed',?)",
                (rule_id, rule_yaml, min(1.0, count / 10), source_runs, time.time()),
            )
            proposed += 1

        conn.commit()
        return proposed
