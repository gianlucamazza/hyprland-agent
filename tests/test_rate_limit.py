"""Tests for RateLimiter and sanitize_command."""

from __future__ import annotations

import time
from collections import deque

import pytest

from agent.safety.rate_limit import RateLimiter, sanitize_command

# ── RateLimiter ────────────────────────────────────────────────────────────────


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_first_action(self) -> None:
        limiter = RateLimiter()
        assert await limiter.check("type_text") is True

    @pytest.mark.asyncio
    async def test_blocks_when_exceeded(self) -> None:
        limiter = RateLimiter(limits={"test_kind": (2, 60)})
        assert await limiter.check("test_kind") is True
        assert await limiter.check("test_kind") is True
        assert await limiter.check("test_kind") is False

    @pytest.mark.asyncio
    async def test_allows_after_window_expiry(self) -> None:
        limiter = RateLimiter(limits={"fast": (1, 0.05)})
        assert await limiter.check("fast") is True
        assert await limiter.check("fast") is False
        time.sleep(0.06)
        assert await limiter.check("fast") is True

    @pytest.mark.asyncio
    async def test_fallback_limit(self) -> None:
        limiter = RateLimiter(limits={})
        for _ in range(60):
            assert await limiter.check("unknown_kind") is True
        assert await limiter.check("unknown_kind") is False

    @pytest.mark.asyncio
    async def test_different_kinds_independent(self) -> None:
        limiter = RateLimiter(limits={"a": (1, 60), "b": (1, 60)})
        assert await limiter.check("a") is True
        assert await limiter.check("b") is True
        assert await limiter.check("a") is False
        assert await limiter.check("b") is False

    @pytest.mark.asyncio
    async def test_reset_clears_buckets(self) -> None:
        limiter = RateLimiter(limits={"x": (1, 60)})
        assert await limiter.check("x") is True
        assert await limiter.check("x") is False
        await limiter.reset()
        assert await limiter.check("x") is True

    @pytest.mark.asyncio
    async def test_reconfigure_replaces_limits_and_clears(self) -> None:
        from agent.config import RateLimitConfig

        limiter = RateLimiter(limits={"a": (1, 60)})
        assert await limiter.check("a") is True
        assert await limiter.check("a") is False

        cfg = RateLimitConfig(
            gui_actions_per_minute=99, terminal_commands_per_minute=99, other_actions_per_minute=99
        )
        await limiter.reconfigure(cfg)
        # "a" is not in GUI or terminal kinds, so it uses the new "other" limit
        for _ in range(99):
            assert await limiter.check("a") is True
        assert await limiter.check("a") is False

    @pytest.mark.asyncio
    async def test_from_config_creates_limiter(self) -> None:
        from agent.config import RateLimitConfig

        cfg = RateLimitConfig(
            gui_actions_per_minute=5, terminal_commands_per_minute=2, other_actions_per_minute=3
        )
        limiter = RateLimiter.from_config(cfg)
        # type_text is a GUI kind, limit 5/min
        for _ in range(5):
            assert await limiter.check("type_text") is True
        assert await limiter.check("type_text") is False
        # unknown kind uses "other" limit (3/min)
        await limiter.reset()
        for _ in range(3):
            assert await limiter.check("other_kind") is True
        assert await limiter.check("other_kind") is False

    @pytest.mark.asyncio
    async def test_from_config_none_uses_defaults(self) -> None:
        limiter = RateLimiter.from_config(None)
        assert await limiter.check("type_text") is True

    def test_thread_safety(self) -> None:
        import concurrent.futures

        limiter = RateLimiter(limits={"shared": (1000, 60)})

        async def _check() -> bool:
            return await limiter.check("shared")

        def _run() -> bool:
            import asyncio

            return asyncio.run(_check())

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: _run(), range(100)))
        assert sum(results) == 100  # all should pass within limit

    @pytest.mark.asyncio
    async def test_internal_buckets_are_deques(self) -> None:
        limiter = RateLimiter()
        await limiter.check("x")
        assert isinstance(limiter._buckets["x"], deque)  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_reconfigure_after_use_does_not_raise(self) -> None:
        from agent.config import RateLimitConfig

        limiter = RateLimiter()
        await limiter.check("type_text")
        cfg = RateLimitConfig()
        await limiter.reconfigure(cfg)
        assert await limiter.check("type_text") is True


# ── sanitize_command ──────────────────────────────────────────────────────────


class TestSanitizeCommand:
    def test_safe_command(self) -> None:
        ok, reason = sanitize_command("ls -la")
        assert ok is True
        assert reason == ""

    def test_pipe_to_agent_blocked(self) -> None:
        ok, reason = sanitize_command("echo hello | agent run something")
        assert ok is False
        assert "blocked pattern" in reason

    def test_pipe_to_hyprland_agent_blocked(self) -> None:
        ok, _ = sanitize_command("do_stuff | hyprland-agent")
        assert ok is False

    def test_backgrounding_blocked(self) -> None:
        ok, _ = sanitize_command("nohup longtask &")
        assert ok is False

    def test_backgrounding_no_spaces_blocked(self) -> None:
        ok, _ = sanitize_command("longtask&")
        assert ok is False

    def test_rm_force_root_blocked(self) -> None:
        ok, _ = sanitize_command("rm -rf /")
        assert ok is False

    def test_rm_subdir_allowed(self) -> None:
        ok, _ = sanitize_command("rm -rf /var/log")
        assert ok is True

    def test_rm_safe_path_allowed(self) -> None:
        ok, _ = sanitize_command("rm -rf /tmp/build")
        assert ok is True

    def test_mkfs_blocked(self) -> None:
        ok, _ = sanitize_command("mkfs.ext4 /dev/sda1")
        assert ok is False

    def test_mkfs_blocked_bare(self) -> None:
        ok, _ = sanitize_command("mkfs /dev/nvme0n1")
        assert ok is False

    def test_dd_block_device_blocked(self) -> None:
        ok, _ = sanitize_command("dd if=/dev/zero of=/dev/sda")
        assert ok is False

    def test_dd_safe_file_allowed(self) -> None:
        ok, _ = sanitize_command("dd if=/dev/zero of=/tmp/out.bin bs=1M count=1")
        assert ok is True

    def test_empty_string(self) -> None:
        ok, _ = sanitize_command("")
        assert ok is True

    def test_whitespace_only(self) -> None:
        ok, _ = sanitize_command("   ")
        assert ok is True

    def test_multiple_dangerous_patterns_returns_first_blocked(self) -> None:
        ok, reason = sanitize_command("rm -rf / | agent watcher")
        assert ok is False
        assert "blocked pattern" in reason
