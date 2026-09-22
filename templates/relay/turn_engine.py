"""Client-agnostic consent, qualification, and booking cycle.

The model phrases the conversation. This module decides whether a tool may run.
It does not contain a client persona, offer, or calendar id.
"""

from __future__ import annotations

import copy
import re
from typing import Callable

from ghl_calendar import CalendarReceiptError, require_appointment_receipt


OPT_OUT_REPLY = "You are opted out. We will not message again."
OPT_OUT_RE = re.compile(r"^(stop|stopall|unsubscribe|quit|end)\b", re.I)
CANCEL_RE = re.compile(r"^cancel[.! ]*$", re.I)
OPT_OUT_PHRASE_RE = re.compile(
    r"\b(do not message|don't message|do not text|don't text|opt out)\b",
    re.I,
)
DEFAULT_REQUIRED = ("project", "location", "timeline", "intent")


def fresh_state() -> dict:
    return {
        "stage": "open",
        "profile": {},
        "offered": [],
        "appointment_id": "",
        "booked_slot": "",
        "handled_events": [],
        "sent_keys": [],
    }


def is_opt_out(text: str | None) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    return bool(OPT_OUT_RE.match(raw) or CANCEL_RE.match(raw) or OPT_OUT_PHRASE_RE.search(raw))


def missing_required(profile: dict | None, required: tuple[str, ...] = DEFAULT_REQUIRED) -> list[str]:
    source = profile or {}
    return [name for name in required if not str(source.get(name) or "").strip()]


def match_slot(text: str | None, offered: list[str]) -> str | None:
    raw = (text or "").strip()
    numbered = re.match(r"^([1-9])\b", raw)
    if numbered:
        index = int(numbered.group(1)) - 1
        if 0 <= index < len(offered):
            return offered[index]
        return None
    return next((slot for slot in offered if slot == raw), None)


def booking_instructions(required: tuple[str, ...] = DEFAULT_REQUIRED) -> str:
    fields = ", ".join(required)
    return (
        "Calendar tools are available. Return JSON with reply, actions, and profile. "
        f"Fill profile keys {fields} from the lead's own words. "
        'Use {"tool":"offer_slots"} only when those keys are filled and the lead wants a time. '
        'Use {"tool":"book","slot":"<exact offered slot>"} only when the lead picks one offered slot. '
        "Never invent a time, a price, or a guarantee. Do not add a reply-STOP sentence."
    )


def run_turn(
    *,
    state: dict | None,
    event_id: str,
    text: str,
    brain: Callable[[str, dict, list[str]], dict],
    slots_fn: Callable[[], list[str]],
    book_fn: Callable[[str], dict],
    required: tuple[str, ...] = DEFAULT_REQUIRED,
    in_area: tuple[str, ...] = (),
    out_of_area: tuple[str, ...] = (),
    tools_enabled: bool = True,
    appointment_request: Callable[[str], dict] | None = None,
) -> tuple[dict, dict]:
    current = copy.deepcopy(state or fresh_state())
    event_id = (event_id or "").strip()
    if event_id and event_id in current["handled_events"]:
        return current, _effect(send=False, duplicate=True)

    if current.get("stage") == "opted_out" or is_opt_out(text):
        return _opt_out(current, event_id)

    if current.get("stage") in ("booked", "handoff"):
        _mark(current, event_id, sent=False)
        return current, _effect(send=False)

    brain_out = brain(text, dict(current.get("profile") or {}), list(current.get("offered") or []))
    if not isinstance(brain_out, dict):
        brain_out = {}
    current["profile"] = _merge_profile(current.get("profile") or {}, brain_out.get("profile"))
    reply = str(brain_out.get("reply") or "").strip()
    tool = _tool(brain_out.get("actions"))
    if not tools_enabled:
        tool = None

    area = _area(text, current["profile"], in_area, out_of_area)
    if area == "out":
        current["stage"] = "handoff"
        _mark(current, event_id, sent=True)
        return current, _effect(send=True, reply="That location is outside the service area. A person will take it from here.", handoff=True)
    if area == "unclear":
        tool = None
        reply = reply or "Which location should I use?"

    missing = missing_required(current["profile"], required)
    if tool and tool["tool"] == "book":
        return _book(current, event_id, text, reply, tool, missing, slots_fn, book_fn, appointment_request)
    if tool and tool["tool"] == "offer_slots":
        return _offer(current, event_id, reply, missing, slots_fn)

    _mark(current, event_id, sent=bool(reply))
    return current, _effect(send=bool(reply), reply=reply or None)


def _book(current, event_id, text, reply, tool, missing, slots_fn, book_fn, appointment_request):
    chosen = match_slot(text, list(current.get("offered") or []))
    requested = str(tool.get("slot") or "").strip()
    if missing:
        _mark(current, event_id, sent=True)
        return current, _effect(send=True, reply=reply or f"I still need {missing[0]} before I can book.")
    if not chosen or (requested and requested != chosen):
        _mark(current, event_id, sent=True)
        message = "Reply with the number of one offered time." if not chosen else "That time was not one of the open slots I offered."
        return current, _effect(send=True, reply=message)
    try:
        live = list(slots_fn() or [])
    except CalendarReceiptError:
        current["stage"] = "handoff"
        _mark(current, event_id, sent=True)
        return current, _effect(send=True, reply="I could not read open times, so I did not book. A person will take it from here.", handoff=True)
    if chosen not in live:
        current["offered"] = []
        _mark(current, event_id, sent=True)
        return current, _effect(send=True, reply="That time is no longer open. I will not book it.")
    request = appointment_request(chosen) if appointment_request else {"startTime": chosen}
    try:
        payload = book_fn(chosen)
        appointment_id = require_appointment_receipt(payload, request)
    except CalendarReceiptError:
        current["stage"] = "handoff"
        _mark(current, event_id, sent=True)
        return current, _effect(send=True, reply="I could not confirm the booking with the calendar. A person will take it from here.", handoff=True)
    current["appointment_id"] = appointment_id
    current["booked_slot"] = chosen
    current["stage"] = "booked"
    current["offered"] = []
    _mark(current, event_id, sent=True)
    return current, _effect(send=True, reply=f"Booked {chosen}. Appointment {appointment_id}.", booked=True, appointment_id=appointment_id)


def _offer(current, event_id, reply, missing, slots_fn):
    if missing:
        _mark(current, event_id, sent=True)
        return current, _effect(send=True, reply=reply or f"What is the {missing[0]}?")
    try:
        slots = list(slots_fn() or [])[:3]
    except CalendarReceiptError:
        current["stage"] = "handoff"
        _mark(current, event_id, sent=True)
        return current, _effect(send=True, reply="I could not read open times. A person will take it from here.", handoff=True)
    if not slots:
        current["stage"] = "handoff"
        _mark(current, event_id, sent=True)
        return current, _effect(send=True, reply="You qualify, but there is no open slot to offer. A person will take it from here.", handoff=True)
    current["offered"] = slots
    current["stage"] = "offering"
    listing = " ".join(f"{index + 1}) {slot}" for index, slot in enumerate(slots))
    _mark(current, event_id, sent=True)
    return current, _effect(send=True, reply=f"Here are the open times. Reply with a number. {listing}")


def _opt_out(current, event_id):
    first = current.get("stage") != "opted_out"
    current["stage"] = "opted_out"
    current["offered"] = []
    _mark(current, event_id, sent=first)
    return current, _effect(send=first, reply=OPT_OUT_REPLY if first else None, opt_out=True)


def _mark(current, event_id, sent: bool) -> None:
    if not event_id:
        return
    if event_id not in current["handled_events"]:
        current["handled_events"].append(event_id)
    if sent and event_id not in current["sent_keys"]:
        current["sent_keys"].append(event_id)


def _merge_profile(profile: dict, update: object) -> dict:
    merged = dict(profile)
    if not isinstance(update, dict):
        return merged
    for key, value in update.items():
        if str(key).startswith("_"):
            continue
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged


def _tool(actions: object) -> dict | None:
    if not isinstance(actions, list):
        return None
    for action in actions:
        if isinstance(action, dict) and action.get("tool") in ("offer_slots", "book"):
            return action
    return None


def _area(text: str, profile: dict, in_area: tuple[str, ...], out_of_area: tuple[str, ...]) -> str:
    blob = f"{text or ''} {profile.get('location') or ''}".lower()
    inside = [item.lower() for item in in_area if item]
    outside = [item.lower() for item in out_of_area if item]
    hit_out = any(item in blob for item in outside)
    hit_in = any(item in blob for item in inside)
    if hit_out and hit_in:
        return "unclear"
    if hit_out:
        return "out"
    if inside and not hit_in:
        return "unclear" if not str(profile.get("location") or "").strip() else "out"
    return "ok"


def _effect(**kwargs) -> dict:
    effect = {
        "send": False,
        "reply": None,
        "duplicate": False,
        "booked": False,
        "appointment_id": "",
        "opt_out": False,
        "handoff": False,
    }
    effect.update(kwargs)
    return effect
