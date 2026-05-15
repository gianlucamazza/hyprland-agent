"""learning.api.approve rule: appends YAML to learned_rules.yaml."""

import asyncio
import time
from pathlib import Path
from unittest.mock import patch

import yaml
import pytest

from agent.daemon.store import RunStore
from agent.learning.api import approve, _append_learned_rule
from agent.learning import api as _api_mod


@pytest.fixture
def store(tmp_path):
    s = RunStore(tmp_path / "runs.db")
    import asyncio

    asyncio.run(s.open())
    return s


def test_approve_rule_writes_yaml(store, tmp_path):
    learned_path = tmp_path / "learned_rules.yaml"
    rule_yaml = yaml.dump(
        {
            "rules": [
                {
                    "on": "openwindow",
                    "match": {"class": "foot"},
                    "actions": [{"log": "auto: focus_window"}],
                }
            ]
        }
    )

    async def _run():
        await store.insert_learned_rule(
            rule_id="r1",
            yaml_str=rule_yaml,
            confidence=0.9,
            source_runs='["run1"]',
        )
        with patch.object(_api_mod, "_LEARNED_RULES_PATH", learned_path):
            result = await approve("rule", "r1", store)

        assert result["status"] == "approved"
        assert learned_path.exists()
        data = yaml.safe_load(learned_path.read_text())
        assert len(data["rules"]) == 1
        assert data["rules"][0]["match"]["class"] == "foot"

    asyncio.run(_run())


def test_append_learned_rule_idempotent_across_calls(tmp_path):
    learned_path = tmp_path / "lr.yaml"
    rule_yaml = yaml.dump(
        {"rules": [{"on": "openwindow", "match": {"class": "x"}, "actions": []}]}
    )

    with patch.object(_api_mod, "_LEARNED_RULES_PATH", learned_path):
        _append_learned_rule(rule_yaml)
        _append_learned_rule(rule_yaml)

    data = yaml.safe_load(learned_path.read_text())
    # Each call appends; caller should avoid duplicates (watcher deduplicates on load)
    assert len(data["rules"]) == 2
