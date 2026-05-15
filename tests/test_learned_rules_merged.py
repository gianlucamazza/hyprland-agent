"""watcher_service.load_rules merges rules.yaml and learned_rules.yaml."""

import asyncio
from unittest.mock import patch

import yaml


def test_load_rules_merges_learned(tmp_path):
    rules_yaml = tmp_path / "rules.yaml"
    learned_yaml = tmp_path / "learned_rules.yaml"

    rules_yaml.write_text(
        yaml.dump(
            {
                "rules": [
                    {
                        "on": "openwindow",
                        "match": {"class": "firefox"},
                        "actions": [{"log": "base"}],
                    }
                ]
            }
        )
    )
    learned_yaml.write_text(
        yaml.dump(
            {
                "rules": [
                    {
                        "on": "openwindow",
                        "match": {"class": "foot"},
                        "actions": [{"log": "learned"}],
                    }
                ]
            }
        )
    )

    from agent.daemon import watcher_service

    with (
        patch.object(watcher_service, "_RULES_PATH", rules_yaml),
        patch.object(watcher_service, "_LEARNED_RULES_PATH", learned_yaml),
    ):
        rules = asyncio.run(watcher_service.load_rules())

    classes = {r.match.app_class for r in rules}
    assert "firefox" in classes
    assert "foot" in classes


def test_load_rules_dedup(tmp_path):
    rules_yaml = tmp_path / "rules.yaml"
    learned_yaml = tmp_path / "learned_rules.yaml"

    rule = {
        "on": "openwindow",
        "match": {"class": "firefox"},
        "actions": [{"log": "dup"}],
    }
    rules_yaml.write_text(yaml.dump({"rules": [rule]}))
    learned_yaml.write_text(yaml.dump({"rules": [rule]}))  # same rule

    from agent.daemon import watcher_service

    with (
        patch.object(watcher_service, "_RULES_PATH", rules_yaml),
        patch.object(watcher_service, "_LEARNED_RULES_PATH", learned_yaml),
    ):
        rules = asyncio.run(watcher_service.load_rules())

    assert len(rules) == 1
