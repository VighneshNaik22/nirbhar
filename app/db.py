from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.config import settings


def _ensure_parent(path: str) -> None:
    directory = Path(path).resolve().parent
    directory.mkdir(parents=True, exist_ok=True)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=True)


def get_connection() -> sqlite3.Connection:
    _ensure_parent(settings.DATABASE_PATH)
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None) -> None:
    database_path = db_path or settings.DATABASE_PATH
    _ensure_parent(database_path)
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                zone TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                sensor_type TEXT,
                sensor_value REAL,
                severity_hint INTEGER NOT NULL,
                reporter_role TEXT,
                timestamp TEXT NOT NULL,
                incident_id TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                actor TEXT NOT NULL,
                event_type TEXT NOT NULL,
                incident_id TEXT,
                payload_json TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                zone TEXT NOT NULL,
                category TEXT NOT NULL,
                confidence TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                recommendation_json TEXT DEFAULT NULL
            )
            """
        )

        conn.execute("PRAGMA table_info(incidents)")
        columns = [row[1] for row in conn.execute("PRAGMA table_info(incidents)").fetchall()]
        if "recommendation_json" not in columns:
            conn.execute("ALTER TABLE incidents ADD COLUMN recommendation_json TEXT DEFAULT NULL")

        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS audit_log_no_update
            BEFORE UPDATE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only');
            END;
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
            BEFORE DELETE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only');
            END;
            """
        )

        conn.commit()


def append_audit_event(
    *,
    actor: str,
    event_type: str,
    payload: dict,
    incident_id: str | None = None,
) -> dict:
    with sqlite3.connect(settings.DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        prev_row = conn.execute(
            "SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev_hash = prev_row["hash"] if prev_row else "GENESIS"
        ts = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        record = {
            "ts": ts,
            "actor": actor,
            "event_type": event_type,
            "incident_id": incident_id,
            "payload": payload,
        }
        payload_json = _canonical_json(payload)
        digest = hashlib.sha256(f"{prev_hash}{payload_json}".encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT INTO audit_log(ts, actor, event_type, incident_id, payload_json, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, actor, event_type, incident_id, payload_json, prev_hash, digest),
        )
        conn.commit()
        return {"id": conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"], "hash": digest, "prev_hash": prev_hash, "ts": ts}


def verify_audit_chain() -> dict:
    with sqlite3.connect(settings.DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, ts, actor, event_type, incident_id, payload_json, prev_hash, hash FROM audit_log ORDER BY id ASC"
        ).fetchall()

    expected_prev = "GENESIS"
    for row in rows:
        payload_json = row["payload_json"]
        expected_hash = hashlib.sha256(f"{expected_prev}{payload_json}".encode("utf-8")).hexdigest()
        if row["hash"] != expected_hash or row["prev_hash"] != expected_prev:
            return {"status": "tampered", "details": f"Audit chain mismatch at id {row['id']}"}
        expected_prev = row["hash"]
    return {"status": "intact", "entries": len(rows)}


def reset_database() -> None:
    if os.path.exists(settings.DATABASE_PATH):
        os.remove(settings.DATABASE_PATH)
    init_db()
