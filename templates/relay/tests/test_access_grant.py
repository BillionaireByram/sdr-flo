import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from access_grant import consume_grant, mint_demo_access
from ghl_poll import fetch_inbound, parse_inbound_messages


class GrantTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.secret = "test-secret"
        self.now = 1_700_000_000_000
        self.code = mint_demo_access(self.secret, self.now + 60_000)

    def test_phrase_and_digits_without_a_real_code_do_not_pass(self):
        result = consume_grant(self.con, "1700000060000.forged", self.secret, "ip", True, self.now)
        self.assertEqual(result["httpStatus"], 401)
        self.assertFalse(result["sent"])

    def test_not_live_does_not_consume_or_send(self):
        first = consume_grant(self.con, self.code, self.secret, "ip", False, self.now)
        second = consume_grant(self.con, self.code, self.secret, "ip2", True, self.now)
        self.assertEqual(first["httpStatus"], 503)
        self.assertEqual(second["httpStatus"], 200)

    def test_a_code_can_be_used_once_when_live(self):
        first = consume_grant(self.con, self.code, self.secret, "once", True, self.now)
        second = consume_grant(self.con, self.code, self.secret, "once-b", True, self.now)
        self.assertTrue(first["ok"])
        self.assertEqual(second["httpStatus"], 409)
        self.assertFalse(second["sent"])

    def test_rate_limit_stops_before_send(self):
        for index in range(5):
            result = consume_grant(self.con, "bad", self.secret, "same", True, self.now)
            self.assertEqual(result["httpStatus"], 401)
        blocked = consume_grant(self.con, self.code, self.secret, "same", True, self.now)
        self.assertEqual(blocked["httpStatus"], 429)
        self.assertFalse(blocked["sent"])


class PollTests(unittest.TestCase):
    def test_parse_keeps_inbound_only(self):
        payload = {"messages": {"messages": [
            {"id": "in-1", "direction": "inbound", "body": "Fort Lauderdale", "dateAdded": "2026-09-22T15:00:00Z"},
            {"id": "out-1", "direction": "outbound", "body": "hello"},
        ]}}
        self.assertEqual(parse_inbound_messages(payload)[0]["id"], "in-1")

    def test_fetch_does_not_accept_a_failed_read(self):
        with self.assertRaises(RuntimeError):
            fetch_inbound(lambda path: (503, {}), "conversation-1")


if __name__ == "__main__":
    unittest.main()
