"""Server-side demo grants for the SDR relay.

The public app never sees the signing secret. A code is
`expiry_ms.hmac` and can be consumed once. Provider calls stay behind
the live flag.
"""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
import time
from base64 import urlsafe_b64encode


def mint_demo_access(secret: str, expires_at_ms: int) -> str:
    mac = hmac.new(secret.encode(), str(expires_at_ms).encode(), hashlib.sha256).digest()
    return f"{expires_at_ms}.{urlsafe_b64encode(mac).decode().rstrip('=')}"


def ensure_grant_tables(con: sqlite3.Connection) -> None:
    con.execute("CREATE TABLE IF NOT EXISTS used_grants(code_hash TEXT PRIMARY KEY, used_at INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS rate_events(rate_key TEXT, ts INTEGER)")


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _valid(code: str, secret: str, now_ms: int) -> tuple[bool, int, str]:
    key = secret.strip()
    if not key:
        return False, 503, "Demo access is not configured. Nothing was sent."
    expires_raw, _, mac = (code or "").strip().partition(".")
    if not expires_raw.isdigit() or not mac:
        return False, 401, "Demo access was rejected. Nothing was sent."
    expires_at = int(expires_raw)
    if now_ms > expires_at:
        return False, 403, "Demo access has expired. Nothing was sent."
    expected = mint_demo_access(key, expires_at).split(".", 1)[1]
    if not hmac.compare_digest(mac, expected):
        return False, 401, "Demo access was rejected. Nothing was sent."
    return True, 200, ""


def allow_rate(con: sqlite3.Connection, rate_key: str, now_ms: int, limit: int = 5, window_ms: int = 600_000) -> bool:
    ensure_grant_tables(con)
    cutoff = now_ms - window_ms
    con.execute("DELETE FROM rate_events WHERE ts < ?", (cutoff,))
    count = con.execute("SELECT COUNT(*) FROM rate_events WHERE rate_key=?", (rate_key,)).fetchone()[0]
    if count >= limit:
        con.commit()
        return False
    con.execute("INSERT INTO rate_events VALUES(?,?)", (rate_key, now_ms))
    con.commit()
    return True


def peek_grant(con: sqlite3.Connection, code: str, secret: str, rate_key: str, live: bool, now_ms: int | None = None) -> dict:
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    ensure_grant_tables(con)
    if not allow_rate(con, rate_key or "relay", now_ms):
        return {"ok": False, "httpStatus": 429, "sent": False, "message": "Too many demo attempts. Nothing was sent."}
    valid, status, message = _valid(code, secret, now_ms)
    if not valid:
        return {"ok": False, "httpStatus": status, "sent": False, "message": message}
    if not live:
        return {"ok": False, "httpStatus": 503, "sent": False, "message": "The relay is not live. Nothing was sent."}
    digest = _code_hash(code.strip())
    existing = con.execute("SELECT 1 FROM used_grants WHERE code_hash=?", (digest,)).fetchone()
    if existing:
        return {"ok": False, "httpStatus": 409, "sent": False, "message": "This demo access code was already used. Nothing was sent."}
    return {"ok": True, "httpStatus": 200, "sent": False, "message": "", "code_hash": digest}


def commit_grant(con: sqlite3.Connection, code: str, now_ms: int | None = None) -> None:
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    ensure_grant_tables(con)
    digest = _code_hash(code.strip())
    con.execute("INSERT OR IGNORE INTO used_grants VALUES(?,?)", (digest, now_ms))
    con.commit()


def consume_grant(con: sqlite3.Connection, code: str, secret: str, rate_key: str, live: bool, now_ms: int | None = None) -> dict:
    peeked = peek_grant(con, code, secret, rate_key, live, now_ms)
    if peeked.get("ok"):
        commit_grant(con, code, now_ms)
    return peeked
