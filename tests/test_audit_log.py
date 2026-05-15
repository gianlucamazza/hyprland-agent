"""Tests for daemon/audit_log.py JSONL writer."""

from __future__ import annotations

import json

import pytest

from agent.daemon.audit_log import AuditLog


class TestAuditLogDisabled:
    @pytest.mark.asyncio
    async def test_disabled_open_is_noop(self, tmp_path):
        log = AuditLog(enabled=False, directory=tmp_path / "audit")
        await log.open()
        assert not (tmp_path / "audit").exists()

    @pytest.mark.asyncio
    async def test_disabled_write_is_noop(self, tmp_path):
        log = AuditLog(enabled=False, directory=tmp_path / "audit")
        await log.open()
        await log.write({"run_id": "abc", "kind": "test"})
        assert not (tmp_path / "audit").exists()

    @pytest.mark.asyncio
    async def test_disabled_close_is_noop(self, tmp_path):
        log = AuditLog(enabled=False, directory=tmp_path / "audit")
        await log.open()
        await log.close()


class TestAuditLogEnabled:
    @pytest.mark.asyncio
    async def test_open_creates_directory(self, tmp_path):
        audit_dir = tmp_path / "audit"
        log = AuditLog(enabled=True, directory=audit_dir)
        await log.open()
        assert audit_dir.exists()

    @pytest.mark.asyncio
    async def test_open_sets_path_after_open(self, tmp_path):
        audit_dir = tmp_path / "audit"
        log = AuditLog(enabled=True, directory=audit_dir)
        await log.open()
        assert log._path is not None
        assert log._path.suffix == ".jsonl"

    @pytest.mark.asyncio
    async def test_write_appends_valid_json(self, tmp_path):
        audit_dir = tmp_path / "audit"
        log = AuditLog(enabled=True, directory=audit_dir)
        await log.open()
        await log.write({"run_id": "abc123", "kind": "action", "seq": 0})
        await log.write({"run_id": "abc123", "kind": "result", "seq": 1})

        files = list(audit_dir.glob("*.jsonl"))
        lines = files[0].read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["run_id"] == "abc123"
        assert json.loads(lines[1])["kind"] == "result"

    @pytest.mark.asyncio
    async def test_write_before_open_is_noop(self, tmp_path):
        audit_dir = tmp_path / "audit"
        log = AuditLog(enabled=True, directory=audit_dir)
        await log.write({"run_id": "x"})
        assert not audit_dir.exists()

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, tmp_path):
        log = AuditLog(enabled=True, directory=tmp_path / "audit")
        await log.open()
        await log.close()
        await log.close()
