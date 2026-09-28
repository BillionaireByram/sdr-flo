import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
os.environ.setdefault("RELAY_SOUL", str(HERE.parent / "soul" / "SOUL.template.md"))
os.environ.setdefault("RELAY_DB", str(Path(tempfile.mkdtemp()) / "state.db"))
os.environ.setdefault("RELAY_LOG", str(Path(os.environ["RELAY_DB"]).parent / "agent.log.jsonl"))

from ghl_webhook import ghl_webhook_fields
import agent_service


class GhlWebhookTests(unittest.TestCase):
    def test_missing_model_fails_closed_before_calling_a_bridge(self):
        with mock.patch.object(agent_service, "MODEL", ""), \
             mock.patch.object(agent_service.urllib.request, "urlopen", side_effect=AssertionError("bridge called")):
            result = agent_service.think([], "hello", {})
        self.assertEqual(result, {"reply": "", "actions": []})

    def test_rejected_reply_is_not_recorded_as_sent_or_retried_on_another_channel(self):
        contact = "contact-rejected"
        with mock.patch.object(agent_service, "LIVE", True), \
             mock.patch.object(agent_service, "contact_tags", return_value=[agent_service.ENABLE_TAG]), \
             mock.patch.object(agent_service, "think", return_value={"reply": "What are you looking for?", "actions": [], "profile": {}}), \
             mock.patch.object(agent_service, "ghl", return_value=(422, {"error": "wrong channel"})) as provider:
            result = agent_service.handle({"contactId": contact, "text": "hello", "messageId": "rejected-1"})
        self.assertFalse(result["sent"])
        self.assertTrue(result["delivery_unconfirmed"])
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(provider.call_args.args[2]["type"], agent_service.GHL_MSG_TYPE)
        self.assertFalse(agent_service.db().execute(
            "SELECT 1 FROM turns WHERE contact=? AND role='assistant'", (contact,)
        ).fetchone())

    def test_failed_contact_read_cannot_open_the_keyword_gate(self):
        with mock.patch.object(agent_service, "ghl", return_value=(503, {"contact": {"tags": []}})), \
             mock.patch.object(agent_service, "think", side_effect=AssertionError("reasoned")), \
             mock.patch.object(agent_service, "send_reply", side_effect=AssertionError("sent")), \
             mock.patch.object(agent_service, "KEYWORDS", ["flo"]):
            result = agent_service.handle({"contactId": "contact-unreadable", "text": "FLO", "messageId": "unreadable-1"})
        self.assertEqual(result["skipped"], "tag-fetch-failed")

    def test_customer_replied_shape(self):
        fields = ghl_webhook_fields({
            "contact_id": "contact-1",
            "phone": "+15555550199",
            "message": {"id": "msg-9", "body": "A putting green in Dallas"},
        })
        self.assertEqual(fields["contactId"], "contact-1")
        self.assertEqual(fields["messageId"], "msg-9")
        self.assertIn("Dallas", fields["text"])

    def test_form_webhook_does_not_send_while_the_relay_is_off(self):
        with mock.patch.object(agent_service, "LIVE", False), \
             mock.patch.object(agent_service, "send_reply", side_effect=AssertionError("sent")):
            result = agent_service.accept_ghl_form({"contact_id": "contact-1", "phone": "+15555550199"})
        self.assertEqual(result["httpStatus"], 503)
        self.assertFalse(result["sent"])


if __name__ == "__main__":
    unittest.main()
