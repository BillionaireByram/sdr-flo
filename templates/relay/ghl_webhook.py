"""Map a GoHighLevel workflow webhook onto the relay.

The form submission is the opt-in. A customer reply is one turn.
This does not register or replace a Loop webhook.
"""

from __future__ import annotations


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def ghl_webhook_fields(payload: dict) -> dict:
    contact = payload.get("contact") if isinstance(payload.get("contact"), dict) else {}
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    contact_id = _text(payload.get("contact_id") or payload.get("contactId") or contact.get("id"))
    phone = _text(payload.get("phone") or contact.get("phone"))
    if isinstance(payload.get("message"), str):
        body = payload["message"].strip()
        message_id = _text(payload.get("message_id") or payload.get("messageId"))
    else:
        body = _text(message.get("body") or message.get("text") or payload.get("body") or payload.get("text"))
        message_id = _text(message.get("id") or payload.get("message_id") or payload.get("messageId"))
    if not message_id and contact_id and body:
        message_id = f"ghl:{contact_id}:{body[:80]}"
    return {"contactId": contact_id, "phone": phone, "text": body, "messageId": message_id}
