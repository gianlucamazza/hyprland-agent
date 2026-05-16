"""SAFETY: approved skills cannot bypass the allowlist / _ALWAYS_DENY."""

from agent.safety.allowlist import _ALWAYS_DENY, is_allowed
from agent.schemas import Window


def _window(cls: str, title: str = "test") -> Window:
    return Window(
        address="0x1",
        app_class=cls,
        title=title,
        workspace_id=1,
        at=(0, 0),
        size=(100, 100),
        floating=False,
        hidden=False,
        pid=1,
        monitor=0,
    )


def test_always_deny_not_overridable_by_any_class():
    """_ALWAYS_DENY members are blocked regardless of allowlist state."""
    for cls in _ALWAYS_DENY:
        w = _window(cls)
        assert is_allowed(w) is False, f"{cls} should be denied"


def test_allowlist_empty_denies_all():
    """Empty allowlist → deny all (safe default is maintained)."""
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmpdir:
        fake_path = Path(tmpdir) / "allowlist.yaml"
        # file doesn't exist → _load_rules returns []
        with patch("agent.safety.allowlist._CONFIG_PATH", fake_path):
            w = _window("someapp")
            assert is_allowed(w) is False


def test_skill_approval_does_not_modify_is_allowed(tmp_path):
    """Approving a skill in the DB does NOT call is_allowed differently."""
    import asyncio

    from agent.daemon.store import RunStore
    from agent.learning.api import approve

    store = RunStore(tmp_path / "runs.db")

    asyncio.run(store.open())

    async def _run():
        await store.insert_skill("sk1", "bad skill", "desc", '["focus_window"]', None)
        await approve("skill", "sk1", store)

    asyncio.run(_run())

    # After approval, keepassxc is still blocked
    w = _window("keepassxc")
    assert is_allowed(w) is False


def test_is_binary_allowed_defaults():
    """Default binary allowlist permits known binaries."""
    from agent.safety.allowlist import _DEFAULT_BINARY_ALLOWLIST, is_binary_allowed

    for name in _DEFAULT_BINARY_ALLOWLIST:
        assert is_binary_allowed(name) is True
    assert is_binary_allowed("unknown-binary") is False


def test_is_binary_allowed_yaml_override(tmp_path, monkeypatch):
    """YAML binaries list overrides the default set."""
    import yaml

    from agent.safety.allowlist import is_binary_allowed

    fake_path = tmp_path / "allowlist.yaml"
    fake_path.write_text(yaml.dump({"binaries": ["my-custom-bin"]}))
    monkeypatch.setattr("agent.safety.allowlist._CONFIG_PATH", fake_path)

    assert is_binary_allowed("my-custom-bin") is True
    assert is_binary_allowed("notify-send") is False


def test_is_binary_allowed_missing_file_falls_back(tmp_path, monkeypatch):
    """Missing allowlist.yaml falls back to the hardcoded default."""
    from agent.safety.allowlist import is_binary_allowed

    fake_path = tmp_path / "nonexistent.yaml"
    assert not fake_path.exists()
    monkeypatch.setattr("agent.safety.allowlist._CONFIG_PATH", fake_path)

    assert is_binary_allowed("wl-copy") is True
    assert is_binary_allowed("nope") is False


def test_is_binary_allowed_empty_yaml_binaries_falls_back(tmp_path, monkeypatch):
    """YAML with ``binaries:`` key set to null falls back to defaults."""
    import yaml

    from agent.safety.allowlist import is_binary_allowed

    fake_path = tmp_path / "allowlist.yaml"
    fake_path.write_text(yaml.dump({"binaries": None}))
    monkeypatch.setattr("agent.safety.allowlist._CONFIG_PATH", fake_path)

    assert is_binary_allowed("wl-copy") is True
    assert is_binary_allowed("nope") is False
