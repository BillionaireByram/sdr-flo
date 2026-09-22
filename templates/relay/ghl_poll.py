"""Read inbound GHL conversation messages on the relay host.

This stays off the public app. The app only asks the relay to pull.
"""

from __future__ import annotations

from typing import Callable


def parse_inbound_messages(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    nested = payload.get("messages")
    rows = nested.get("messages") if isinstance(nested, dict) else nested
    if not isinstance(rows, list):
        return []
    found = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("direction") or "").lower() != "inbound":
            continue
        message_id = str(row.get("id") or "").strip()
        body = str(row.get("body") or "").strip()
        if not message_id or not body:
            continue
        found.append({
            "id": message_id,
            "body": body,
            "occurredAt": str(row.get("dateAdded") or row.get("occurredAt") or ""),
        })
    return found


def fetch_inbound(ghl_get: Callable[[str], tuple[int, object]], conversation_id: str) -> list[dict]:
    status, payload = ghl_get(f"/conversations/{conversation_id}/messages?limit=20")
    if status != 200:
        raise RuntimeError("GHL inbound was not accepted")
    return parse_inbound_messages(payload)
