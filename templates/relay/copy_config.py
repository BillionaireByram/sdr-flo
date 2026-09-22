"""Client copy for the relay. Defaults stay generic. A client file may override them."""

from __future__ import annotations

import json
from pathlib import Path


GENERIC = {
    "opener": "This is a demo conversation, not a signed customer. What kind of project is this?",
    "slot_offer": "Here are the open times. Reply with the number you want. {slots}",
    "confirmation": "Booked {slot}. Appointment {appointment_id}.",
    "followup": "Thanks for the reply. What should I clarify?",
    "questions": {
        "project": "What kind of project is this?",
        "location": "What city is the property in?",
        "timeline": "When do you want the visit?",
        "intent": "Do you want an appointment, or are you still comparing options?",
    },
    "required": ["project", "location", "timeline", "intent"],
    "in_area": [],
    "out_of_area": [],
}


def load_client_copy(path: str | None) -> dict:
    loaded = json.loads(Path(path).read_text()) if path else {}
    if not isinstance(loaded, dict):
        loaded = {}
    copy = dict(GENERIC)
    for key in ("opener", "slot_offer", "confirmation", "followup"):
        value = loaded.get(key)
        if isinstance(value, str) and value.strip():
            copy[key] = value.strip()
    questions = dict(GENERIC["questions"])
    if isinstance(loaded.get("questions"), dict):
        for key, value in loaded["questions"].items():
            if isinstance(value, str) and value.strip():
                questions[str(key)] = value.strip()
    copy["questions"] = questions
    for key in ("required", "in_area", "out_of_area"):
        value = loaded.get(key)
        if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
            copy[key] = [item.strip() for item in value]
    return copy


def render_template(template: str, **values: str) -> str:
    try:
        rendered = template.format(**values)
    except (KeyError, IndexError, ValueError):
        rendered = template
    for key, value in values.items():
        token = "{" + key + "}"
        if token in rendered:
            rendered = rendered.replace(token, value)
        elif value and value not in rendered and key == "appointment_id":
            rendered = f"{rendered} Appointment {value}."
    return rendered.strip()
