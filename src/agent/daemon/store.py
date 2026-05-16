"""SQLite-backed run storage with in-memory LRU cache."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent.config import CACHE_DIR
from agent.schemas import RunEventRecord, RunKind, RunRecord, RunStatus, RunSummary

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_LATEST_SCHEMA_VERSION = 5  # increment when a new migration is added

_DB_PATH = CACHE_DIR / "runs.db"

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS runs (
    run_id     TEXT PRIMARY KEY,
    kind       TEXT NOT NULL DEFAULT 'run',
    task       TEXT NOT NULL,
    brain      TEXT NOT NULL,
    status     TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at   REAL,
    error_text TEXT
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


def _load_vec0(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension into *conn*. Raises on failure."""
    import sqlite_vec

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


class RunStore:
    """Thread-safe async wrapper around SQLite with a LRU detail cache."""

    def __init__(self, path: Path = _DB_PATH) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._lru: OrderedDict[str, RunRecord] = OrderedDict()
        self._vec_ok: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        await self._run_sync(self._init_db)

    def _init_db(self, conn: sqlite3.Connection) -> None:
        # Load vec0 extension first so v3 virtual table can be created
        try:
            _load_vec0(conn)
            self._vec_ok = True
        except Exception as exc:
            log.warning("sqlite-vec unavailable, episodic memory disabled: %s", exc)
            self._vec_ok = False
        conn.executescript(_SCHEMA)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        legacy_col = "dry" + "_run"
        if "error_text" not in cols:
            conn.execute("ALTER TABLE runs ADD COLUMN error_text TEXT")
            cols.add("error_text")
        if "kind" not in cols:
            conn.execute("ALTER TABLE runs ADD COLUMN kind TEXT NOT NULL DEFAULT 'run'")
            cols.add("kind")
        if legacy_col in cols:
            self._rebuild_runs_table(conn)
        conn.commit()
        user_ver = conn.execute("PRAGMA user_version").fetchone()[0]
        if user_ver < 2:
            self._apply_v2_migration(conn)
        if user_ver < 3:
            self._apply_v3_migration(conn)
        if user_ver < 4:
            self._apply_v4_migration(conn)
        if user_ver < 5:
            self._apply_v5_migration(conn)

    def _apply_v2_migration(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        for col, typedef in [
            ("iterations", "INTEGER"),
            ("action_count", "INTEGER"),
            ("duration_s", "REAL"),
        ]:
            if col not in cols:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {typedef}")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS run_outcomes (
                run_id     TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
                outcome    TEXT NOT NULL,
                score      REAL,
                source     TEXT NOT NULL,
                rationale  TEXT,
                decided_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                kind        TEXT NOT NULL,
                comment     TEXT,
                created_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_feedback_run ON feedback(run_id);

            CREATE TABLE IF NOT EXISTS action_outcomes (
                run_id            TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                seq               INTEGER NOT NULL,
                action_kind       TEXT NOT NULL,
                params_json       TEXT NOT NULL,
                result_kind       TEXT NOT NULL,
                stdout            TEXT,
                stderr            TEXT,
                returncode        INTEGER,
                dispatch_response TEXT,
                pre_state_hash    TEXT,
                post_state_hash   TEXT,
                duration_ms       INTEGER,
                PRIMARY KEY (run_id, seq)
            );
            CREATE INDEX IF NOT EXISTS idx_action_outcomes_kind
                ON action_outcomes(action_kind, result_kind);
        """)
        conn.execute("PRAGMA user_version=2")
        conn.commit()

    def _apply_v3_migration(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodes (
                run_id          TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
                task            TEXT NOT NULL,
                task_normalized TEXT NOT NULL,
                outcome         TEXT NOT NULL,
                summary         TEXT NOT NULL,
                context_class   TEXT,
                actions_json    TEXT NOT NULL,
                created_at      REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_outcome
                ON episodes(outcome, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_episodes_context
                ON episodes(context_class);

            CREATE TABLE IF NOT EXISTS reflections (
                reflection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id        TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                polarity      TEXT NOT NULL,
                text          TEXT NOT NULL,
                generated_by  TEXT NOT NULL,
                created_at    REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_reflections_run ON reflections(run_id);
        """)
        if self._vec_ok:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS episode_vecs USING vec0("
                "run_id TEXT PRIMARY KEY,"
                "embedding FLOAT[1024]"
                ")"
            )
        conn.execute("PRAGMA user_version=3")
        conn.commit()

    def _rebuild_runs_table(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE runs_new (
                run_id     TEXT PRIMARY KEY,
                kind       TEXT NOT NULL DEFAULT 'run',
                task       TEXT NOT NULL,
                brain      TEXT NOT NULL,
                status     TEXT NOT NULL,
                started_at REAL NOT NULL,
                ended_at   REAL,
                error_text TEXT
            );
            INSERT INTO runs_new (run_id, kind, task, brain, status, started_at, ended_at, error_text)
            SELECT run_id, COALESCE(kind, 'run'), task, brain, status, started_at, ended_at, error_text
            FROM runs;
            DROP TABLE runs;
            ALTER TABLE runs_new RENAME TO runs;
            CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
            """
        )

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
            "INSERT INTO runs (run_id, kind, task, brain, status, started_at, ended_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run.run_id,
                run.kind.value,
                run.task,
                run.brain,
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
        error: str | None = None,
    ) -> None:
        async with self._lock:
            ended = ended_at if ended_at is not None else time.time()
            await self._run_sync(self._do_update_status, run_id, status.value, ended, error)
            self._lru.pop(run_id, None)  # invalidate cache entry

    def _do_update_status(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        status: str,
        ended_at: float,
        error: str | None,
    ) -> None:
        conn.execute(
            "UPDATE runs SET status=?, ended_at=?, error_text=? WHERE run_id=?",
            (status, ended_at, error, run_id),
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
            "INSERT INTO run_events (run_id, seq, ts, kind, payload_json) VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                event.seq,
                event.ts,
                event.kind,
                json.dumps(event.payload),
            ),
        )
        conn.commit()

    async def update_run_metrics(
        self,
        run_id: str,
        *,
        iterations: int | None = None,
        action_count: int | None = None,
        duration_s: float | None = None,
    ) -> None:
        if iterations is None and action_count is None and duration_s is None:
            return
        async with self._lock:
            await self._run_sync(
                self._do_update_metrics, run_id, iterations, action_count, duration_s
            )
            self._lru.pop(run_id, None)

    def _do_update_metrics(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        iterations: int | None,
        action_count: int | None,
        duration_s: float | None,
    ) -> None:
        sets: list[str] = []
        vals: list[Any] = []
        if iterations is not None:
            sets.append("iterations=?")
            vals.append(iterations)
        if action_count is not None:
            sets.append("action_count=?")
            vals.append(action_count)
        if duration_s is not None:
            sets.append("duration_s=?")
            vals.append(duration_s)
        vals.append(run_id)
        conn.execute(f"UPDATE runs SET {', '.join(sets)} WHERE run_id=?", vals)
        conn.commit()

    async def upsert_run_outcome(
        self,
        run_id: str,
        outcome: str,
        score: float,
        source: str,
        rationale: str | None = None,
    ) -> None:
        async with self._lock:
            await self._run_sync(self._do_upsert_outcome, run_id, outcome, score, source, rationale)

    def _do_upsert_outcome(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        outcome: str,
        score: float,
        source: str,
        rationale: str | None,
    ) -> None:
        conn.execute(
            "INSERT INTO run_outcomes (run_id, outcome, score, source, rationale, decided_at)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(run_id) DO UPDATE SET"
            "   outcome=excluded.outcome, score=excluded.score,"
            "   source=excluded.source, rationale=excluded.rationale,"
            "   decided_at=excluded.decided_at",
            (run_id, outcome, score, source, rationale, time.time()),
        )
        conn.commit()

    async def insert_feedback(
        self,
        run_id: str,
        kind: str,
        comment: str | None = None,
    ) -> int:
        async with self._lock:
            return await self._run_sync(self._do_insert_feedback, run_id, kind, comment)

    def _do_insert_feedback(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        kind: str,
        comment: str | None,
    ) -> int:
        cur = conn.execute(
            "INSERT INTO feedback (run_id, kind, comment, created_at) VALUES (?, ?, ?, ?)",
            (run_id, kind, comment, time.time()),
        )
        conn.commit()
        return cur.lastrowid or 0

    async def list_analytics(self, days: int = 7) -> dict:
        import time as _time

        cutoff = _time.time() - days * 86400
        return await self._run_sync(self._do_analytics, cutoff, days)

    def _do_analytics(self, conn: sqlite3.Connection, cutoff: float, days: int) -> dict:
        conn.row_factory = sqlite3.Row
        outcome_rows = conn.execute(
            "SELECT o.outcome, COUNT(*) AS cnt"
            " FROM run_outcomes o JOIN runs r ON r.run_id = o.run_id"
            " WHERE r.started_at >= ? GROUP BY o.outcome ORDER BY cnt DESC",
            (cutoff,),
        ).fetchall()
        outcomes = {r["outcome"]: r["cnt"] for r in outcome_rows}

        failure_rows = conn.execute(
            "SELECT r.task, COUNT(*) AS cnt"
            " FROM run_outcomes o JOIN runs r ON r.run_id = o.run_id"
            " WHERE o.outcome = 'failure' AND r.started_at >= ?"
            " GROUP BY r.task ORDER BY cnt DESC LIMIT 10",
            (cutoff,),
        ).fetchall()
        top_failures = [{"task": r["task"], "count": r["cnt"]} for r in failure_rows]

        total = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE started_at >= ?", (cutoff,)
        ).fetchone()[0]

        return {
            "days": days,
            "total_runs": total,
            "outcomes": outcomes,
            "top_failure_tasks": top_failures,
        }

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def list_runs(self, limit: int = 50) -> list[RunSummary]:
        rows = await self._run_sync(self._do_list_runs, limit)
        return [self._row_to_summary(r) for r in rows]

    def _do_list_runs(self, conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT run_id, kind, task, brain, status, started_at, ended_at, error_text"
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
            "SELECT run_id, kind, task, brain, status, started_at, ended_at, error_text"
            " FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        events = conn.execute(
            "SELECT seq, ts, kind, payload_json FROM run_events WHERE run_id=? ORDER BY seq",
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
            kind=RunKind(row["kind"]),
            task=row["task"],
            brain=row["brain"],
            status=RunStatus(row["status"]),
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            error=row["error_text"],
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> RunEventRecord:
        return RunEventRecord(
            seq=row["seq"],
            ts=row["ts"],
            kind=row["kind"],
            payload=json.loads(row["payload_json"]),
        )

    # ------------------------------------------------------------------
    # Episodic memory
    # ------------------------------------------------------------------

    async def insert_episode(
        self,
        run_id: str,
        task: str,
        outcome: str,
        summary: str,
        context_class: str | None,
        actions_json: str,
    ) -> None:
        async with self._lock:
            await self._run_sync(
                self._do_insert_episode,
                run_id,
                task,
                outcome,
                summary,
                context_class,
                actions_json,
            )

    def _do_insert_episode(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        task: str,
        outcome: str,
        summary: str,
        context_class: str | None,
        actions_json: str,
    ) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO episodes"
            " (run_id, task, task_normalized, outcome, summary, context_class,"
            "  actions_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                task,
                task.lower().strip(),
                outcome,
                summary,
                context_class,
                actions_json,
                time.time(),
            ),
        )
        conn.commit()

    async def insert_episode_vec(self, run_id: str, embedding: list[float]) -> None:
        if not self._vec_ok:
            return
        async with self._lock:
            await self._run_vec_sync(self._do_insert_episode_vec, run_id, embedding)

    def _do_insert_episode_vec(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        embedding: list[float],
    ) -> None:
        import struct

        blob = struct.pack(f"{len(embedding)}f", *embedding)
        conn.execute(
            "INSERT OR REPLACE INTO episode_vecs (run_id, embedding) VALUES (?, ?)",
            (run_id, blob),
        )
        conn.commit()

    async def query_episodes_by_vec(
        self,
        embedding: list[float],
        k: int = 3,
        exclude_outcome: str | None = None,
    ) -> list[dict]:
        if not self._vec_ok:
            return []
        return await self._run_vec_sync(
            self._do_query_episodes_by_vec, embedding, k, exclude_outcome
        )

    def _do_query_episodes_by_vec(
        self,
        conn: sqlite3.Connection,
        embedding: list[float],
        k: int,
        exclude_outcome: str | None,
    ) -> list[dict]:
        import struct

        blob = struct.pack(f"{len(embedding)}f", *embedding)
        sql = (
            "SELECT e.run_id, e.task, e.outcome, e.summary, e.context_class,"
            "       vec_distance_cosine(ev.embedding, ?) AS dist"
            " FROM episode_vecs ev"
            " JOIN episodes e ON e.run_id = ev.run_id"
        )
        params: list = [blob]
        if exclude_outcome:
            sql += " WHERE e.outcome != ?"
            params.append(exclude_outcome)
        sql += " ORDER BY dist LIMIT ?"
        params.append(k)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    async def get_episode(self, run_id: str) -> dict | None:
        """Return a single episode row by run_id, or None if not found."""
        async with self._lock:
            return await self._run_sync(self._do_get_episode, run_id)

    def _do_get_episode(self, conn: sqlite3.Connection, run_id: str) -> dict | None:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT run_id, task, outcome, summary, context_class, actions_json, created_at"
            " FROM episodes WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return dict(row) if row else None

    async def insert_reflection(
        self,
        run_id: str,
        polarity: str,
        text: str,
        generated_by: str,
    ) -> None:
        async with self._lock:
            await self._run_sync(self._do_insert_reflection, run_id, polarity, text, generated_by)

    def _do_insert_reflection(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        polarity: str,
        text: str,
        generated_by: str,
    ) -> None:
        conn.execute(
            "INSERT INTO reflections (run_id, polarity, text, generated_by, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (run_id, polarity, text, generated_by, time.time()),
        )
        conn.commit()

    async def list_recent_reflections(
        self, polarity: str = "negative", limit: int = 20
    ) -> list[dict]:
        return await self._run_sync(self._do_list_recent_reflections, polarity, limit)

    def _do_list_recent_reflections(
        self,
        conn: sqlite3.Connection,
        polarity: str,
        limit: int,
    ) -> list[dict]:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT run_id, polarity, text, generated_by, created_at"
            " FROM reflections WHERE polarity=? ORDER BY created_at DESC LIMIT ?",
            (polarity, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def _apply_v4_migration(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS skills (
                skill_id      TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                description   TEXT NOT NULL,
                actions_json  TEXT NOT NULL,
                params_schema TEXT,
                source_run_id TEXT REFERENCES runs(run_id),
                created_at    REAL NOT NULL,
                last_used_at  REAL,
                status        TEXT NOT NULL DEFAULT 'draft'
            );
            CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);

            CREATE TABLE IF NOT EXISTS skill_outcomes (
                skill_id TEXT NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
                run_id   TEXT NOT NULL REFERENCES runs(run_id)    ON DELETE CASCADE,
                outcome  TEXT NOT NULL,
                ts       REAL NOT NULL,
                PRIMARY KEY (skill_id, run_id)
            );

            CREATE TABLE IF NOT EXISTS learned_rules (
                rule_id      TEXT PRIMARY KEY,
                yaml         TEXT NOT NULL,
                confidence   REAL NOT NULL,
                hit_count    INTEGER NOT NULL DEFAULT 0,
                source_runs  TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'proposed',
                proposed_at  REAL NOT NULL,
                decided_at   REAL
            );
            CREATE INDEX IF NOT EXISTS idx_learned_rules_status ON learned_rules(status);

            CREATE TABLE IF NOT EXISTS allowlist_proposals (
                proposal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_class   TEXT NOT NULL,
                title_pat   TEXT NOT NULL DEFAULT '*',
                hit_count   INTEGER NOT NULL DEFAULT 1,
                last_seen   REAL NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending'
            );
            CREATE UNIQUE INDEX IF NOT EXISTS uq_allowlist_proposal
                ON allowlist_proposals(app_class, title_pat);
        """)
        if self._vec_ok:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS skill_vecs USING vec0("
                "skill_id TEXT PRIMARY KEY,"
                "embedding FLOAT[1024]"
                ")"
            )
        conn.execute("PRAGMA user_version=4")
        conn.commit()

    def _apply_v5_migration(self, conn: sqlite3.Connection) -> None:
        """Add decay_score and last_accessed_at columns for memory decay."""
        for table in ("episodes", "reflections"):
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if "decay_score" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN decay_score REAL DEFAULT 1.0")
            if "last_accessed_at" not in cols:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN last_accessed_at REAL DEFAULT (strftime('%s','now'))"
                )
        cols = {row[1] for row in conn.execute("PRAGMA table_info(skills)").fetchall()}
        if "decay_score" not in cols:
            conn.execute("ALTER TABLE skills ADD COLUMN decay_score REAL DEFAULT 1.0")
        conn.execute("PRAGMA user_version=5")
        conn.commit()

    # ------------------------------------------------------------------
    # Memory decay (v5)
    # ------------------------------------------------------------------

    async def prune_decayed(
        self,
        threshold: float = 0.1,
        half_life_days: int = 90,
    ) -> dict[str, int]:
        """Delete memory records whose decay_score has fallen below *threshold*.

        Before pruning, scores are recalculated using a simple exponential
        decay formula::

            score = 1.0 * 0.5 ** (elapsed_days / half_life_days)

        Returns a dict of ``{table: deleted_count}``.
        """
        return await self._run_sync(self._do_prune_decayed, threshold, half_life_days)

    def _do_prune_decayed(
        self,
        conn: sqlite3.Connection,
        threshold: float,
        half_life_days: int,
    ) -> dict[str, int]:
        half_life_s = half_life_days * 86400
        now = time.time()
        result: dict[str, int] = {}

        for table in ("episodes", "reflections", "skills"):
            ref_col = "created_at" if table != "skills" else "created_at"
            conn.execute(
                f"""
                UPDATE {table}
                SET decay_score = POW(0.5, (? - COALESCE(last_accessed_at, {ref_col}, ?)) / ?)
                WHERE 1=1
                """,
                (now, now, half_life_s),
            )
            deleted = conn.execute(
                f"DELETE FROM {table} WHERE decay_score < ?", (threshold,)
            ).rowcount
            result[table] = deleted

        conn.commit()
        return result

    async def touch_memory(self, table: str, row_id_col: str, row_id: str) -> None:
        """Update ``last_accessed_at`` for a memory row to prevent decay."""
        await self._run_sync(
            lambda conn: conn.execute(
                f"UPDATE {table} SET last_accessed_at=strftime('%s','now'), decay_score=1.0 WHERE {row_id_col}=?",
                (row_id,),
            )
        )

    # ------------------------------------------------------------------
    # Skill library (P4)
    # ------------------------------------------------------------------

    async def insert_skill(
        self,
        skill_id: str,
        name: str,
        description: str,
        actions_json: str,
        source_run_id: str | None = None,
    ) -> None:
        async with self._lock:
            await self._run_sync(
                self._do_insert_skill,
                skill_id,
                name,
                description,
                actions_json,
                source_run_id,
            )

    def _do_insert_skill(
        self,
        conn: sqlite3.Connection,
        skill_id: str,
        name: str,
        description: str,
        actions_json: str,
        source_run_id: str | None,
    ) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO skills"
            " (skill_id, name, description, actions_json, source_run_id, created_at, status)"
            " VALUES (?, ?, ?, ?, ?, ?, 'draft')",
            (skill_id, name, description, actions_json, source_run_id, time.time()),
        )
        conn.commit()

    async def insert_skill_vec(self, skill_id: str, embedding: list[float]) -> None:
        if not self._vec_ok:
            return
        async with self._lock:
            await self._run_vec_sync(self._do_insert_skill_vec, skill_id, embedding)

    def _do_insert_skill_vec(
        self, conn: sqlite3.Connection, skill_id: str, embedding: list[float]
    ) -> None:
        import struct

        blob = struct.pack(f"{len(embedding)}f", *embedding)
        conn.execute(
            "INSERT OR REPLACE INTO skill_vecs (skill_id, embedding) VALUES (?, ?)",
            (skill_id, blob),
        )
        conn.commit()

    async def update_skill_status(self, skill_id: str, status: str) -> None:
        async with self._lock:
            await self._run_sync(self._do_update_skill_status, skill_id, status)

    def _do_update_skill_status(self, conn: sqlite3.Connection, skill_id: str, status: str) -> None:
        conn.execute("UPDATE skills SET status=? WHERE skill_id=?", (status, skill_id))
        conn.commit()

    async def record_skill_outcome(self, skill_id: str, run_id: str, outcome: str) -> None:
        async with self._lock:
            await self._run_sync(self._do_record_skill_outcome, skill_id, run_id, outcome)

    def _do_record_skill_outcome(
        self, conn: sqlite3.Connection, skill_id: str, run_id: str, outcome: str
    ) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO skill_outcomes (skill_id, run_id, outcome, ts) VALUES (?,?,?,?)",
            (skill_id, run_id, outcome, time.time()),
        )
        conn.commit()

    async def list_skills(self, status: str | None = None, limit: int = 50) -> list[dict]:
        return await self._run_sync(self._do_list_skills, status, limit)

    def _do_list_skills(
        self, conn: sqlite3.Connection, status: str | None, limit: int
    ) -> list[dict]:
        conn.row_factory = sqlite3.Row
        if status:
            rows = conn.execute(
                "SELECT * FROM skills WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM skills ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    async def query_skills_by_vec(
        self, embedding: list[float], k: int = 5, status: str = "approved"
    ) -> list[dict]:
        if not self._vec_ok:
            return []
        return await self._run_vec_sync(self._do_query_skills_by_vec, embedding, k, status)

    def _do_query_skills_by_vec(
        self, conn: sqlite3.Connection, embedding: list[float], k: int, status: str
    ) -> list[dict]:
        import struct

        blob = struct.pack(f"{len(embedding)}f", *embedding)
        sql = (
            "SELECT s.*, vec_distance_cosine(sv.embedding, ?) AS dist"
            " FROM skill_vecs sv"
            " JOIN skills s ON s.skill_id = sv.skill_id"
            " WHERE s.status = ?"
            " ORDER BY dist LIMIT ?"
        )
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, (blob, status, k)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Learned rules (P4)
    # ------------------------------------------------------------------

    async def insert_learned_rule(
        self, rule_id: str, yaml_str: str, confidence: float, source_runs: str
    ) -> None:
        async with self._lock:
            await self._run_sync(
                self._do_insert_learned_rule, rule_id, yaml_str, confidence, source_runs
            )

    def _do_insert_learned_rule(
        self,
        conn: sqlite3.Connection,
        rule_id: str,
        yaml_str: str,
        confidence: float,
        source_runs: str,
    ) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO learned_rules"
            " (rule_id, yaml, confidence, source_runs, status, proposed_at)"
            " VALUES (?,?,?,?,'proposed',?)",
            (rule_id, yaml_str, confidence, source_runs, time.time()),
        )
        conn.commit()

    async def list_learned_rules(self, status: str | None = None) -> list[dict]:
        return await self._run_sync(self._do_list_learned_rules, status)

    def _do_list_learned_rules(self, conn: sqlite3.Connection, status: str | None) -> list[dict]:
        conn.row_factory = sqlite3.Row
        if status:
            rows = conn.execute(
                "SELECT * FROM learned_rules WHERE status=? ORDER BY proposed_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM learned_rules ORDER BY proposed_at DESC").fetchall()
        return [dict(r) for r in rows]

    async def update_learned_rule_status(self, rule_id: str, status: str) -> None:
        async with self._lock:
            await self._run_sync(self._do_update_rule_status, rule_id, status)

    def _do_update_rule_status(self, conn: sqlite3.Connection, rule_id: str, status: str) -> None:
        conn.execute(
            "UPDATE learned_rules SET status=?, decided_at=? WHERE rule_id=?",
            (status, time.time(), rule_id),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Allowlist proposals (P4)
    # ------------------------------------------------------------------

    async def upsert_allowlist_proposal(self, app_class: str, title_pat: str) -> None:
        async with self._lock:
            await self._run_sync(self._do_upsert_allowlist_proposal, app_class, title_pat)

    def _do_upsert_allowlist_proposal(
        self, conn: sqlite3.Connection, app_class: str, title_pat: str
    ) -> None:
        conn.execute(
            "INSERT INTO allowlist_proposals (app_class, title_pat, hit_count, last_seen, status)"
            " VALUES (?, ?, 1, ?, 'pending')"
            " ON CONFLICT(app_class, title_pat) DO UPDATE SET"
            "   hit_count = hit_count + 1,"
            "   last_seen = excluded.last_seen"
            "   WHERE status = 'pending'",
            (app_class, title_pat, time.time()),
        )
        conn.commit()

    async def list_allowlist_proposals(self, status: str | None = "pending") -> list[dict]:
        return await self._run_sync(self._do_list_allowlist_proposals, status)

    def _do_list_allowlist_proposals(
        self, conn: sqlite3.Connection, status: str | None
    ) -> list[dict]:
        conn.row_factory = sqlite3.Row
        if status is None:
            rows = conn.execute(
                "SELECT * FROM allowlist_proposals ORDER BY hit_count DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM allowlist_proposals WHERE status=? ORDER BY hit_count DESC",
                (status,),
            ).fetchall()
        return [dict(r) for r in rows]

    async def update_allowlist_proposal_status(self, proposal_id: int, status: str) -> None:
        async with self._lock:
            await self._run_sync(self._do_update_allowlist_proposal_status, proposal_id, status)

    def _do_update_allowlist_proposal_status(
        self, conn: sqlite3.Connection, proposal_id: int, status: str
    ) -> None:
        conn.execute(
            "UPDATE allowlist_proposals SET status=? WHERE proposal_id=?",
            (status, proposal_id),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_sync(self, fn, *args):
        """Execute *fn(conn, *args)* in a thread executor."""
        path = str(self._path)

        def _call():
            with sqlite3.connect(path) as conn:
                return fn(conn, *args)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _call)

    async def _run_vec_sync(self, fn, *args):
        """Like _run_sync but loads vec0 extension before calling *fn*."""
        path = str(self._path)

        def _call():
            with sqlite3.connect(path) as conn:
                _load_vec0(conn)
                return fn(conn, *args)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _call)
