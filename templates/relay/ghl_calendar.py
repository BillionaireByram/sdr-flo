"""GHL calendar tools for the SDR relay.

Contract source, checked 2026-09-22:
- OpenAPI `apps/calendars.json` SlotsSchema: each date key holds
  `{ "slots": ["ISO-8601", ...] }`. `traceId` is not a day.
- Get Free Slots: `GET /calendars/:calendarId/free-slots` with millisecond
  `startDate` and `endDate`, range at most 31 days. Version enum in that
  file is `2021-04-15`.
- Create appointment: `POST /calendars/events/appointments`.
  AppointmentSchemaResponse requires `id`, `calendarId`, `locationId`,
  and `contactId`.
- A read-only live GET with Version `2021-07-28` returned the same shape:
  date keys, `slots` arrays of ISO strings, plus `traceId`.

No client id, persona, or credential belongs in this module.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote


class CalendarReceiptError(Exception):
    pass


GHL_VERSION = "2021-04-15"
REQUIRED_RECEIPT_FIELDS = ("id", "calendarId", "locationId", "contactId")


def free_slots_path(calendar_id: str, start_ms: int, end_ms: int, timezone: str = "") -> str:
    if not calendar_id.strip():
        raise CalendarReceiptError("calendar id is required")
    if end_ms < start_ms or (end_ms - start_ms) > 31 * 86_400_000:
        raise CalendarReceiptError("free-slot range must be within 31 days")
    path = f"/calendars/{calendar_id}/free-slots?startDate={int(start_ms)}&endDate={int(end_ms)}"
    if timezone.strip():
        path += "&timezone=" + quote(timezone.strip())
    return path


def parse_free_slots(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        raise CalendarReceiptError("free-slot payload is not an object")
    found: list[str] = []
    for day, value in payload.items():
        if day == "traceId":
            continue
        if not isinstance(value, dict) or not isinstance(value.get("slots"), list):
            raise CalendarReceiptError("free-slot day is missing a slots array")
        for slot in value["slots"]:
            if not isinstance(slot, str) or "T" not in slot.strip():
                raise CalendarReceiptError("free-slot item is not an ISO string")
            found.append(slot.strip())
    return found


def appointment_body(
    *,
    calendar_id: str,
    location_id: str,
    contact_id: str,
    start_time: str,
    slot_minutes: int = 30,
    title: str = "Consultation",
    notify: bool = False,
) -> dict:
    if slot_minutes <= 0:
        raise CalendarReceiptError("slot minutes must be positive")
    start = datetime.fromisoformat(start_time)
    end = (start + timedelta(minutes=slot_minutes)).isoformat()
    return {
        "calendarId": calendar_id,
        "locationId": location_id,
        "contactId": contact_id,
        "startTime": start_time,
        "endTime": end,
        "title": title,
        "appointmentStatus": "confirmed",
        "toNotify": bool(notify),
    }


def require_appointment_receipt(payload: object, request: dict) -> str:
    if not isinstance(payload, dict):
        raise CalendarReceiptError("appointment receipt is not an object")
    missing = [key for key in REQUIRED_RECEIPT_FIELDS if not _text(payload.get(key))]
    if missing:
        raise CalendarReceiptError("appointment receipt missing " + ",".join(missing))
    for key in ("calendarId", "locationId", "contactId", "startTime"):
        if key in request and payload.get(key) != request[key]:
            raise CalendarReceiptError(f"appointment receipt {key} does not match the request")
    return _text(payload.get("id"))


def _text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()
