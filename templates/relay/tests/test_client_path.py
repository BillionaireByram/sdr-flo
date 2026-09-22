import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
os.environ.setdefault("RELAY_SOUL", str(HERE.parent / "soul" / "SOUL.template.md"))
os.environ.setdefault("RELAY_DB", str(Path(tempfile.mkdtemp()) / "state.db"))
os.environ.setdefault("RELAY_LOG", str(Path(os.environ["RELAY_DB"]).parent / "agent.log.jsonl"))
os.environ.setdefault("RELAY_LIVE", "false")

import agent_service
from access_grant import mint_demo_access
from copy_config import GENERIC

SLOTS = ["2026-09-24T10:00:00-04:00", "2026-09-24T11:00:00-04:00"]


def receipt(slot):
    return {
        "id": "appt-1",
        "calendarId": "cal-1",
        "locationId": "loc-1",
        "contactId": "contact-path",
        "startTime": slot,
    }


class ClientPathTests(unittest.TestCase):
    def setUp(self):
        self.copy = Path(tempfile.mkdtemp()) / "copy.json"
        self.copy.write_text(
            '{"opener":"Demo opener, not a signed customer. What project is this?",'
            '"slot_offer":"Open times. Reply with a number. {slots}",'
            '"confirmation":"Booked {slot}. Appointment {appointment_id}.",'
            '"followup":"Thanks for the reply. What should I clarify?",'
            '"questions":{"location":"What city is the property in?","timeline":"When do you want the visit?","intent":"Do you want an appointment?"},'
            '"required":["project","location","timeline","intent"]}'
        )
        self.secret = "path-secret"
        self.code = mint_demo_access(self.secret, int(time.time() * 1000) + 60_000)
        self.sent = []
        self.books = []

    def env(self):
        return {
            "RELAY_COPY_FILE": str(self.copy),
            "DEMO_ACCESS_SECRET": self.secret,
            "OPT_IN_PHRASE": "DEMO OPT IN",
            "RELAY_ALLOWED_PHONE": "+15555550199",
            "RELAY_CONTACT_ID": "contact-path",
            "GHL_CALENDAR_ID": "cal-1",
            "GHL_LOCATION_ID": "loc-1",
            "GHL_CONVERSATION_ID": "conv-1",
        }

    def ghl(self, method, path, body=None):
        if method == "GET" and "free-slots" in path:
            return 200, {"2026-09-24": {"slots": SLOTS}}
        if method == "POST" and path == "/calendars/events/appointments":
            self.books.append(body)
            return 201, {**body, "id": "appt-1"}
        if method == "POST" and path.endswith("/tags"):
            return 200, {}
        raise AssertionError(method + path)

    def think(self, hist, inbound, profile):
        updated = dict(profile)
        lowered = inbound.lower()
        if "putting" in lowered:
            updated["project"] = "putting green"
        if "fort" in lowered:
            updated["location"] = "fort example"
        if "month" in lowered:
            updated["timeline"] = "this month"
            updated["intent"] = "estimate"
        missing = [key for key in ("project", "location", "timeline", "intent") if not updated.get(key)]
        if missing:
            return {"reply": "next", "actions": [], "profile": updated}
        if inbound.strip().startswith("2"):
            return {"reply": "book", "actions": [{"tool": "book", "slot": SLOTS[1]}], "profile": updated}
        return {"reply": "offer", "actions": [{"tool": "offer_slots"}], "profile": updated}

    def test_defaults_are_not_client_specific(self):
        self.assertNotIn("ProTurf", GENERIC["opener"])
        self.assertNotIn("Fort Lauderdale", str(GENERIC))

    def test_opt_in_through_booked_confirmation_and_blocks(self):
        with mock.patch.dict(os.environ, self.env()), \
             mock.patch.object(agent_service, "LIVE", True), \
             mock.patch.object(agent_service, "send_reply", side_effect=lambda contact, text: self.sent.append(text)), \
             mock.patch.object(agent_service, "ghl", side_effect=self.ghl), \
             mock.patch.object(agent_service, "think", side_effect=self.think):
            missing = agent_service.accept_opt_in({"phrase": "DEMO OPT IN", "last4": "0199", "rateKey": "missing"})
            invalid = agent_service.accept_opt_in({"accessCode": f"{int(time.time() * 1000) + 60_000}.forged", "phrase": "DEMO OPT IN", "last4": "0199", "rateKey": "invalid"})
            opened = agent_service.accept_opt_in({"accessCode": self.code, "phrase": "DEMO OPT IN", "last4": "0199", "rateKey": "open"})
            again = agent_service.accept_opt_in({"accessCode": self.code, "phrase": "DEMO OPT IN", "last4": "0199", "rateKey": "open-2"})
            agent_service.handle({"contactId": "contact-path", "phone": "+15555550199", "text": "putting green", "messageId": "m1"})
            agent_service.handle({"contactId": "contact-path", "phone": "+15555550199", "text": "fort example", "messageId": "m2"})
            agent_service.handle({"contactId": "contact-path", "phone": "+15555550199", "text": "this month and I want an estimate", "messageId": "m3"})
            offered = agent_service.handle({"contactId": "contact-path", "phone": "+15555550199", "text": "ready", "messageId": "m4"})
            booked = agent_service.handle({"contactId": "contact-path", "phone": "+15555550199", "text": "2", "messageId": "m5"})
            duplicate = agent_service.handle({"contactId": "contact-path", "phone": "+15555550199", "text": "2", "messageId": "m5"})
            stopped = agent_service.handle({"contactId": "contact-path", "phone": "+15555550199", "text": "STOP", "messageId": "m6"})

        self.assertEqual(missing["httpStatus"], 401)
        self.assertFalse(missing["sent"])
        self.assertEqual(invalid["httpStatus"], 401)
        self.assertEqual(opened["sent"], True)
        self.assertIn("not a signed customer", opened["reply"])
        self.assertNotIn("I opted in and want to talk about the project", opened["reply"])
        self.assertEqual(again["httpStatus"], 409)
        self.assertIn(SLOTS[0], offered["reply"])
        self.assertIn(SLOTS[1], offered["reply"])
        self.assertTrue(booked["booked"])
        self.assertIn("appt-1", booked["reply"])
        self.assertIn(SLOTS[1], booked["reply"])
        self.assertNotIn("Reply STOP", booked["reply"])
        self.assertEqual(len(self.books), 1)
        self.assertTrue(duplicate["duplicate"])
        self.assertFalse(duplicate["sent"])
        self.assertEqual(len(self.books), 1)
        self.assertIn("opted out", stopped["reply"].lower())
        self.assertEqual(self.sent[0], opened["reply"])
        self.assertIn("appt-1", self.sent[-2] if len(self.sent) > 2 else "")


class MintCliTests(unittest.TestCase):
    def test_cli_writes_a_code_without_printing_it(self):
        destination = Path(tempfile.mkdtemp()) / "code.txt"
        env = os.environ.copy()
        env["DEMO_ACCESS_SECRET"] = "cli-secret"
        env["DEMO_ACCESS_CODE_OUT"] = str(destination)
        completed = subprocess.run(
            [sys.executable, str(HERE / "mint_access_code.py")],
            cwd=str(HERE),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        code = destination.read_text().strip()
        self.assertEqual(completed.returncode, 0)
        self.assertNotIn(code, completed.stdout)
        self.assertNotIn(code, completed.stderr)
        self.assertNotIn("cli-secret", completed.stdout + completed.stderr)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode) & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
