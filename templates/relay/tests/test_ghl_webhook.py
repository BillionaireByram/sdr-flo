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
