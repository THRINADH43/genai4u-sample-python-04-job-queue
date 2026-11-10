"""Jobs are stored in SQLite. Each thread opens its own connection; a lock guards claiming."""

import json
import sqlite3
import threading
import time
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,          -- queued | running | done | failed
    result TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


class JobStore:
    def __init__(self, path):
        self.path = path
        self._claim_lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(SCHEMA)
            # a job that was running when the server stopped is queued again
            conn.execute("UPDATE jobs SET status='queued' WHERE status='running'")

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, kind, payload):
        job_id = uuid.uuid4().hex
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id, kind, payload, status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', ?, ?)",
                (job_id, kind, json.dumps(payload), now, now),
            )
        return job_id

    def get(self, job_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        job = dict(row)
        job["payload"] = json.loads(job["payload"])
        job["result"] = json.loads(job["result"]) if job["result"] else None
        return job

    def claim_next(self):
        """Marks the oldest queued job as running and returns it, or None. Only one thread can
        claim at a time, so two workers never get the same job."""
        with self._claim_lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE jobs SET status='running', updated_at=? WHERE id=?", (time.time(), row["id"])
            )
        return self.get(row["id"])

    def finish(self, job_id, result=None, error=None):
        status = "failed" if error else "done"
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status=?, result=?, error=?, updated_at=? WHERE id=?",
                (status, json.dumps(result) if result is not None else None, error, time.time(), job_id),
            )
