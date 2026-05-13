"""SQLite-backed run storage with in-memory LRU cache."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

from agent.schemas import RunEventRecord, RunRecord, RunStatus, RunSummary

if TYPE_CHECKING:
    pass

_DB_PATH = Path.home() / ".cache" / "hyprland-agent" / "runs.db"

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    task       TEXT NOT NULL,
    brain      TEXT NOT NULL,
    dry_run    INTEGER NOT NULL,
    status     TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at   REAL
);

CREATE TABLE IF NOT EXISTS run_events (
    run_id       TEXT NOT NULL REFERENCES runs(run_id),
    seq          INTEGER NOT NULL,
    ts           REAL NOT NULL,
    kind         TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
"""

_LRU_CAPACITY = 16


class RunStore:
    """Thread-safe async wrapper around SQLite with a LRU detail cache."""

    def __init__(self, path: Path = _DB_PATH) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._lru: OrderedDict[str, RunRecord] = OrderedDict()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        await self._run_sync(self._init_db)

    def _init_db(self, conn: sqlite3.Connection) -> None:
        conn.executescript(_SCHEMA)

    async def close(self) -> None:
        pass  # connections are per-call; nothing to close

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def insert_run(self, run: RunSummary) -> None:
        async with self._lock:
            await self._run_sync(self._do_insert_run, run)

    def _do_insert_run(self, conn: sqlite3.Connection, run: RunSummary) -> None:
        conn.execute(
            "INSERT INTO runs (run_id, task, brain, dry_run, status, started_at, ended_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run.run_id,
                run.task,
                run.brain,
                int(run.dry_run),
                run.status.value,
                run.started_at,
                run.ended_at,
            ),
        )
        conn.commit()

    async def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        ended_at: float | None = None,
    ) -> None:
        async with self._lock:
            ended = ended_at if ended_at is not None else time.time()
            await self._run_sync(self._do_update_status, run_id, status.value, ended)
            self._lru.pop(run_id, None)  # invalidate cache entry

    def _do_update_status(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        status: str,
        ended_at: float,
    ) -> None:
        conn.execute(
            "UPDATE runs SET status=?, ended_at=? WHERE run_id=?",
            (status, ended_at, run_id),
        )
        conn.commit()

    async def append_event(self, run_id: str, event: RunEventRecord) -> None:
        async with self._lock:
            await self._run_sync(self._do_append_event, run_id, event)
            self._lru.pop(run_id, None)  # invalidate so next get_run reads fresh

    def _do_append_event(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        event: RunEventRecord,
    ) -> None:
        conn.execute(
            "INSERT INTO run_events (run_id, seq, ts, kind, payload_json)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                event.seq,
                event.ts,
                event.kind,
                json.dumps(event.payload),
            ),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def list_runs(self, limit: int = 50) -> list[RunSummary]:
        rows = await self._run_sync(self._do_list_runs, limit)
        return [self._row_to_summary(r) for r in rows]

    def _do_list_runs(self, conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT run_id, task, brain, dry_run, status, started_at, ended_at"
            " FROM runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    async def get_run(self, run_id: str) -> RunRecord | None:
        if run_id in self._lru:
            self._lru.move_to_end(run_id)
            return self._lru[run_id]
        row_data = await self._run_sync(self._do_get_run, run_id)
        if row_data is None:
            return None
        summary_row, event_rows = row_data
        record = RunRecord(
            **self._row_to_summary(summary_row).model_dump(),
            events=[self._row_to_event(r) for r in event_rows],
        )
        self._lru[run_id] = record
        if len(self._lru) > _LRU_CAPACITY:
            self._lru.popitem(last=False)
        return record

    def _do_get_run(
        self,
        conn: sqlite3.Connection,
        run_id: str,
    ) -> tuple[sqlite3.Row, list[sqlite3.Row]] | None:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT run_id, task, brain, dry_run, status, started_at, ended_at"
            " FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        events = conn.execute(
            "SELECT seq, ts, kind, payload_json FROM run_events"
            " WHERE run_id=? ORDER BY seq",
            (run_id,),
        ).fetchall()
        return row, events

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_summary(row: sqlite3.Row) -> RunSummary:
        return RunSummary(
            run_id=row["run_id"],
            task=row["task"],
            brain=row["brain"],
            dry_run=bool(row["dry_run"]),
            status=RunStatus(row["status"]),
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> RunEventRecord:
        return RunEventRecord(
            seq=row["seq"],
            ts=row["ts"],
            kind=row["kind"],
            payload=json.loads(row["payload_json"]),
        )

    async def _run_sync(self, fn, *args):
        """Execute *fn(conn, *args)* in a thread executor."""
        path = str(self._path)

        def _call():
            with sqlite3.connect(path) as conn:
                return fn(conn, *args)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _call)
