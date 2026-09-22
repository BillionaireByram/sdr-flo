import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock
from http.server import ThreadingHTTPServer

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

os.environ.setdefault("RELAY_SOUL", str(HERE.parent / "soul" / "SOUL.template.md"))
os.environ.setdefault("RELAY_DB", str(Path(tempfile.mkdtemp()) / "state.db"))
os.environ.setdefault("RELAY_LOG", str(Path(os.environ["RELAY_DB"]).parent / "agent.log.jsonl"))
os.environ.setdefault("RELAY_LIVE", "false")

import ghl_calendar  # noqa: E402
import turn_engine  # noqa: E402
import agent_service  # noqa: E402

SLOTS = [
    "2026-09-24T10:00:00-04:00",
    "2026-09-24T11:00:00-04:00",
    "2026-09-25T10:00:00-04:00",
]
REQUIRED = ("project", "location", "timeline", "intent")


def receipt(slot, appointment_id="appt-1"):
    body = ghl_calendar.appointment_body(
        calendar_id="cal-1",
        location_id="loc-1",
        contact_id="contact-1",
        start_time=slot,
        notify=False,
    )
    return {**body, "id": appointment_id, "dateAdded": "2026-09-22T00:00:00Z", "dateUpdated": "2026-09-22T00:00:00Z"}


class ScriptedBrain:
    def __call__(self, text, profile, offered):
        updated = dict(profile)
        lowered = text.lower()
        if "green" in lowered:
            updated["project"] = "putting green"
        if "fort" in lowered:
            updated["location"] = "fort example"
        if "month" in lowered:
            updated["timeline"] = "this month"
            updated["intent"] = "estimate"
        missing = turn_engine.missing_required(updated, REQUIRED)
        if missing:
            return {"reply": f"What is the {missing[0]}?", "actions": [], "profile": updated}
        if offered and text.strip()[:1] in "123":
            slot = offered[int(text.strip()[:1]) - 1]
            return {"reply": "taking that time", "actions": [{"tool": "book", "slot": slot}], "profile": updated}
        return {"reply": "ready for times", "actions": [{"tool": "offer_slots"}], "profile": updated}


class TurnCycleTests(unittest.TestCase):
    def test_multi_turn_qualify_offer_book_and_duplicate(self):
        state = turn_engine.fresh_state()
        brain = ScriptedBrain()
        books = []
        reads = {"n": 0}

        def slots_fn():
            reads["n"] += 1
            return list(SLOTS)

        def book_fn(slot):
            books.append(slot)
            return receipt(slot)

        def step(event_id, text):
            nonlocal state
            state, effect = turn_engine.run_turn(
                state=state,
                event_id=event_id,
                text=text,
                brain=brain,
                slots_fn=slots_fn,
                book_fn=book_fn,
                required=REQUIRED,
                appointment_request=lambda slot: receipt(slot, appointment_id="pending"),
            )
            return effect

        first = step("m1", "I want a putting green")
        self.assertIn("location", first["reply"])
        self.assertFalse(books)

        second = step("m2", "The property is in fort example")
        self.assertIn("timeline", second["reply"])

        third = step("m3", "this month and I want an estimate")
        self.assertIn("1) " + SLOTS[0], third["reply"])
        self.assertNotIn("Booked", third["reply"])
        self.assertEqual(state["offered"], SLOTS)

        fourth = step("m4", "2")
        self.assertTrue(fourth["booked"])
        self.assertEqual(books, [SLOTS[1]])
        self.assertIn("appt-1", fourth["reply"])
        self.assertNotIn("Reply STOP", fourth["reply"])

        duplicate = step("m4", "2")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(books, [SLOTS[1]])
        self.assertEqual(reads["n"], 2)

    def test_stop_is_one_confirmation_and_blocks_booking(self):
        state = turn_engine.fresh_state()
        calls = {"brain": 0, "book": 0}

        def brain(text, profile, offered):
            calls["brain"] += 1
            return {"reply": "still selling", "actions": [{"tool": "book", "slot": SLOTS[0]}], "profile": profile}

        state, effect = turn_engine.run_turn(
            state=state, event_id="s1", text="STOP", brain=brain, slots_fn=lambda: SLOTS,
            book_fn=lambda slot: calls.__setitem__("book", 1) or receipt(slot),
        )
        self.assertTrue(effect["opt_out"])
        self.assertEqual(effect["reply"], turn_engine.OPT_OUT_REPLY)
        self.assertEqual(calls["brain"], 0)
        state, again = turn_engine.run_turn(
            state=state, event_id="s2", text="hello", brain=brain, slots_fn=lambda: SLOTS, book_fn=lambda slot: receipt(slot),
        )
        self.assertFalse(again["send"])
        self.assertEqual(calls["brain"], 0)
        self.assertFalse(turn_engine.is_opt_out("cancel the Tuesday time"))

    def test_rejects_unoffered_slot_and_bad_receipt(self):
        state = turn_engine.fresh_state()
        state["profile"] = {"project": "lawn", "location": "fort example", "timeline": "this month", "intent": "estimate"}
        state["offered"] = [SLOTS[0]]

        def brain(text, profile, offered):
            return {"reply": "book it", "actions": [{"tool": "book", "slot": SLOTS[1]}], "profile": profile}

        state, effect = turn_engine.run_turn(
            state=state, event_id="b1", text="1", brain=brain, slots_fn=lambda: SLOTS, book_fn=lambda slot: receipt(slot),
        )
        self.assertFalse(effect["booked"])
        self.assertIn("not one of the open slots", effect["reply"])

        def bad_book(slot):
            return {"id": "appt-1"}

        state["offered"] = [SLOTS[0]]
        state, effect = turn_engine.run_turn(
            state=state, event_id="b2", text="1", brain=lambda text, profile, offered: {
                "reply": "book", "actions": [{"tool": "book", "slot": SLOTS[0]}], "profile": profile,
            },
            slots_fn=lambda: SLOTS,
            book_fn=bad_book,
            appointment_request=lambda slot: receipt(slot, "pending"),
        )
        self.assertFalse(effect["booked"])
        self.assertNotIn("Booked", effect["reply"])

    def test_out_of_area_does_not_offer(self):
        state = turn_engine.fresh_state()
        state["profile"] = {"project": "lawn", "location": "remote city", "timeline": "this month", "intent": "estimate"}
        state, effect = turn_engine.run_turn(
            state=state, event_id="o1", text="remote city", brain=lambda text, profile, offered: {
                "reply": "let me offer times", "actions": [{"tool": "offer_slots"}], "profile": profile,
            },
            slots_fn=lambda: (_ for _ in ()).throw(AssertionError("slots must not be read")),
            book_fn=lambda slot: (_ for _ in ()).throw(AssertionError("must not book")),
            out_of_area=("remote city",),
        )
        self.assertTrue(effect["handoff"])
        self.assertNotIn("1)", effect["reply"])


class CalendarContractTests(unittest.TestCase):
    def test_parses_live_shape_and_requires_receipt_fields(self):
        payload = {"2026-09-24": {"slots": SLOTS[:2]}, "traceId": "trace-1"}
        self.assertEqual(ghl_calendar.parse_free_slots(payload), SLOTS[:2])
        body = ghl_calendar.appointment_body(
            calendar_id="cal-1", location_id="loc-1", contact_id="contact-1", start_time=SLOTS[0], notify=False,
        )
        self.assertFalse(body["toNotify"])
        self.assertEqual(ghl_calendar.require_appointment_receipt({**body, "id": "appt-9"}, body), "appt-9")
        with self.assertRaises(ghl_calendar.CalendarReceiptError):
            ghl_calendar.require_appointment_receipt({"id": "appt-9"}, body)
        path = ghl_calendar.free_slots_path("cal-1", 1_000, 1_000 + 86_400_000, "America/New_York")
        self.assertIn("/calendars/cal-1/free-slots?", path)
        self.assertIn("timezone=America", path)


class RelayWireTests(unittest.TestCase):
    def test_handle_books_once_and_preserves_iso_text(self):
        sent = []
        posts = []

        def fake_ghl(method, path, body=None):
            if method == "GET":
                return 200, {"2026-09-24": {"slots": SLOTS[:2]}, "traceId": "t"}
            posts.append(body)
            return 201, {**body, "id": "appt-wire"}

        answers = [
            {"reply": "What is the location?", "actions": [], "profile": {"project": "lawn"}},
            {"reply": "What is the timeline?", "actions": [], "profile": {"location": "fort example"}},
            {"reply": "What is the intent?", "actions": [], "profile": {"timeline": "this month"}},
            {"reply": "ready", "actions": [{"tool": "offer_slots"}], "profile": {"intent": "estimate"}},
            {"reply": "booking", "actions": [{"tool": "book", "slot": SLOTS[1]}], "profile": {}},
        ]

        def fake_think(hist, inbound, profile):
            return answers.pop(0)

        with mock.patch.object(agent_service, "contact_tags", return_value=["ai-dm-start"]), \
             mock.patch.object(agent_service, "ghl", side_effect=fake_ghl), \
             mock.patch.object(agent_service, "think", side_effect=fake_think), \
             mock.patch.object(agent_service, "send_reply", side_effect=lambda contact, text: sent.append(text)), \
             mock.patch.object(agent_service, "LIVE", True), \
             mock.patch.dict(os.environ, {"GHL_CALENDAR_ID": "cal-1", "GHL_LOCATION_ID": "loc-1", "GHL_APPOINTMENT_NOTIFY": "false"}):
            agent_service.handle({"contactId": "contact-1", "messageId": "a", "text": "lawn"})
            agent_service.handle({"contactId": "contact-1", "messageId": "b", "text": "fort example"})
            agent_service.handle({"contactId": "contact-1", "messageId": "c", "text": "this month"})
            agent_service.handle({"contactId": "contact-1", "messageId": "d", "text": "I want an estimate"})
            booked = agent_service.handle({"contactId": "contact-1", "messageId": "e", "text": "2"})
            again = agent_service.handle({"contactId": "contact-1", "messageId": "e", "text": "2"})

        self.assertTrue(booked["booked"])
        self.assertIn(SLOTS[1], booked["reply"])
        self.assertIn("appt-wire", sent[-1])
        self.assertTrue(again["duplicate"])
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["calendarId"], "cal-1")
        self.assertFalse(posts[0]["toNotify"])
        self.assertNotIn("Reply STOP", " ".join(sent))
        json.dumps(posts[0])


class PersistentRelayTests(unittest.TestCase):
    def test_http_server_keeps_inbound_turns_and_health_does_not_send(self):
        seen = []

        def fake_think(hist, inbound, profile):
            seen.append({"inbound": inbound, "history": len(hist)})
            if "green" in inbound.lower():
                return {"reply": "What city is the property in?", "actions": [], "profile": {"project": "putting green"}}
            return {"reply": "When do you want the visit?", "actions": [], "profile": {"location": inbound.strip()}}

        server = ThreadingHTTPServer(("127.0.0.1", 0), agent_service.H)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        agent_service.SECRET = "relay-test-secret"
        try:
            thread.start()
            with mock.patch.object(agent_service, "contact_tags", return_value=[]), \
                 mock.patch.object(agent_service, "think", side_effect=fake_think), \
                 mock.patch.object(agent_service, "ghl", side_effect=AssertionError("provider write is not allowed in this test")):
                health = urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5)
                self.assertEqual(json.loads(health.read().decode())["service"], "sdr-relay")
                self.assertEqual(seen, [])

                def post(message_id, text, consented=False, occurred_at=""):
                    payload = {"contactId": "contact-persist", "text": text, "messageId": message_id, "phone": "+14707748556"}
                    if consented:
                        payload["consented"] = True
                    if occurred_at:
                        payload["occurredAt"] = occurred_at
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{port}/inbound",
                        data=json.dumps(payload).encode(),
                        headers={"content-type": "application/json", "x-webhook-secret": "relay-test-secret"},
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=5) as response:
                        return json.loads(response.read().decode())

                blocked = post("blocked", "putting green")
                first = post("m1", "putting green", consented=True)
                old = post("old", "yesterday", occurred_at="2000-01-01T00:00:00Z")
                second = post("m2", "Fort Lauderdale")
                again = post("m2", "Fort Lauderdale")
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(blocked["skipped"], "not-keyword-lead")
        self.assertEqual(old["skipped"], "before-consent")
        self.assertFalse(first.get("skipped"))
        self.assertIn("city", first["reply"])
        self.assertIn("visit", second["reply"])
        self.assertEqual(seen[1]["history"] > 0, True)
        self.assertTrue(again["duplicate"])
        self.assertFalse(again["sent"])


if __name__ == "__main__":
    unittest.main()
