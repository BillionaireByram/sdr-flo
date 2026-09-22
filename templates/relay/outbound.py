"""Durable outbound attempts.

A local row does not prove delivery. A second send is allowed only when no
provider id was stored. Once an id exists, the caller must read it back
before the attempt is accepted.
"""

from __future__ import annotations

import sqlite3
import time


def ensure_outbox(con: sqlite3.Connection) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS outbox("
        "dedupe_key TEXT PRIMARY KEY, contact TEXT, kind TEXT, body TEXT, "
        "status TEXT, provider_id TEXT, created_at INTEGER)"
    )


def begin_outbound(con: sqlite3.Connection, dedupe_key: str, contact: str, kind: str, body: str) -> dict:
    ensure_outbox(con)
    row = con.execute(
        "SELECT status, provider_id, body FROM outbox WHERE dedupe_key=?",
        (dedupe_key,),
    ).fetchone()
    if row:
        status, provider_id, stored = row
        if provider_id:
            return {"action": "readback", "provider_id": provider_id, "body": stored, "status": status}
        return {"action": "blocked", "provider_id": "", "body": stored, "status": status}
    con.execute(
        "INSERT INTO outbox VALUES(?,?,?,?, 'pending', '', ?)",
        (dedupe_key, contact, kind, body, int(time.time() * 1000)),
    )
    con.commit()
    return {"action": "send", "provider_id": "", "body": body, "status": "pending"}


def remember_provider_id(con: sqlite3.Connection, dedupe_key: str, provider_id: str) -> None:
    con.execute("UPDATE outbox SET provider_id=? WHERE dedupe_key=?", (provider_id, dedupe_key))
    con.commit()


def mark_accepted(con: sqlite3.Connection, dedupe_key: str) -> None:
    con.execute("UPDATE outbox SET status='accepted' WHERE dedupe_key=?", (dedupe_key,))
    con.commit()
