import json, os, sqlite3, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOD = HERE.parent
# point the adapter at the real soul/config, a temp DB, offline brain (no bridge)
os.environ.update({
    "IG_DB": tempfile.mktemp(suffix=".db"),
    "IG_SOUL": str(MOD / "SOUL.byram.md"),
    "IG_CONFIG": str(MOD / "config.example.json"),
    "IG_LOG": tempfile.mktemp(suffix=".jsonl"),
    "RELAY_BRIDGE": "",                 # offline => template draft
    "SDR_FLO_DRAFT_ONLY": "true",
    "META_VERIFY_TOKEN": "vt123",
})
import sys; sys.path.insert(0, str(MOD))
import ig_adapter as ig
from meta_client import MetaClient

BANNED = ["sdr flo", "setter flo", "sales flo", "agent flo", "hermes", "flo", " - ", "—", "–"]


def fresh():
    db = tempfile.mktemp(suffix=".db"); ig.DB = db
    return ig.db(), ig.load_config(), MetaClient(token="x", ig_user_id="1", public_reply_live=False, private_reply_live=False, logger=lambda o: None)


class T(unittest.TestCase):
    def test_01_verify_challenge(self):
        c = MetaClient(token="x", ig_user_id="1")
        self.assertEqual(c.verify_challenge("subscribe", "vt123", "CHAL", "vt123"), "CHAL")
        self.assertIsNone(c.verify_challenge("subscribe", "wrong", "CHAL", "vt123"))

    def test_02_keyword_comment_creates_spine_and_drafts(self):
        con, cfg, cl = fresh()
        r = ig.handle_comment({"comment_id": "c1", "text": "FLO", "from_igsid": "u1", "username": "lead1", "media_id": "m1"}, client=cl, cfg=cfg, con=con)
        self.assertEqual(r["campaign"], "FLO")
        self.assertIn("dm_opener", r["drafted"]); self.assertIn("public_reply", r["drafted"])
        self.assertTrue(con.execute("SELECT 1 FROM leads WHERE igsid='u1'").fetchone())
        self.assertTrue(con.execute("SELECT 1 FROM sources WHERE igsid='u1'").fetchone())
        self.assertTrue(con.execute("SELECT 1 FROM events WHERE igsid='u1' AND type='comment_keyword'").fetchone())

    def test_03_non_keyword_no_dm(self):
        con, cfg, cl = fresh()
        r = ig.handle_comment({"comment_id": "c2", "text": "nice post", "from_igsid": "u2"}, client=cl, cfg=cfg, con=con)
        self.assertEqual(r.get("skip"), "no-keyword")
        self.assertFalse(con.execute("SELECT 1 FROM leads WHERE igsid='u2'").fetchone())

    def test_04_duplicate_comment_no_double(self):
        con, cfg, cl = fresh()
        ig.handle_comment({"comment_id": "c3", "text": "FLO", "from_igsid": "u3"}, client=cl, cfg=cfg, con=con)
        r2 = ig.handle_comment({"comment_id": "c3", "text": "FLO", "from_igsid": "u3"}, client=cl, cfg=cfg, con=con)
        self.assertEqual(r2.get("skip"), "dup-comment")

    def test_05_dm_reply_routes_to_brain(self):
        con, cfg, cl = fresh()
        ig.handle_comment({"comment_id": "c4", "text": "FLO", "from_igsid": "u4"}, client=cl, cfg=cfg, con=con)
        r = ig.handle_message({"message_id": "x1", "sender_igsid": "u4", "text": "hey I run a roofing company"}, client=cl, cfg=cfg, con=con)
        self.assertTrue(r["reply"])

    def test_06_optout_suppresses(self):
        con, cfg, cl = fresh()
        ig.handle_comment({"comment_id": "c5", "text": "FLO", "from_igsid": "u5"}, client=cl, cfg=cfg, con=con)
        r = ig.handle_message({"message_id": "x2", "sender_igsid": "u5", "text": "stop messaging me"}, client=cl, cfg=cfg, con=con)
        self.assertEqual(r.get("skip"), "opt-out")

    def test_07_guard_tag_suppresses(self):
        con, cfg, cl = fresh()
        con.execute("INSERT INTO leads VALUES('u6','x','ig','FLO','m','new','customer',0)"); con.commit()
        r = ig.handle_message({"message_id": "x3", "sender_igsid": "u6", "text": "hi"}, client=cl, cfg=cfg, con=con)
        self.assertEqual(r.get("skip"), "suppressed")

    def test_08_no_internal_names_or_dashes(self):
        con, cfg, cl = fresh()
        r = ig.handle_comment({"comment_id": "c7", "text": "FLO", "from_igsid": "u7"}, client=cl, cfg=cfg, con=con)
        blob = (r["drafted"]["dm_opener"] + " " + r["drafted"]["public_reply"]).lower()
        for b in BANNED:
            self.assertNotIn(b, blob, f"banned token leaked: {b!r}")

    def test_09_dryrun_send_returns_dry(self):
        cl = MetaClient(token="x", ig_user_id="1", public_reply_live=False, private_reply_live=False)
        self.assertTrue(cl.send_dm("u", "hi").get("dry"))
        self.assertTrue(cl.private_reply_to_comment("c", "hi").get("dry"))

    def test_10_webhook_envelope_dispatch(self):
        con, cfg, cl = fresh()
        env = json.loads((HERE / "fixtures" / "meta_instagram_comment.json").read_text())
        res = ig.normalize_and_dispatch(env, client=cl, cfg=cfg, con=con)
        self.assertTrue(any(x.get("campaign") == "FLO" for x in res))


if __name__ == "__main__":
    unittest.main(verbosity=2)
