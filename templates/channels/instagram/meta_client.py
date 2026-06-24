#!/usr/bin/env python3
"""
Meta / Instagram Graph API client — OFFICIAL API ONLY.

We never touch the unofficial/private Instagram API (instagrapi, browser automation,
etc.) — those get accounts banned. Every call here is the documented Graph API.

Three actions, each gated by a live flag so DRY-RUN composes-but-never-sends:
  - reply_to_comment(comment_id, text)        public reply under the post
  - private_reply_to_comment(comment_id, text)  DM the commenter (the "private reply",
                                                allowed within 7 days of the comment)
  - send_dm(recipient_igsid, text)            DM a user who is in an open thread (24h window)

Setup the caller provides (env): META_GRAPH_VERSION, IG_USER_ID (the IG-scoped business id
that owns the messaging), PAGE_ACCESS_TOKEN (or IG access token per the chosen login method).
Permissions: instagram_basic, instagram_manage_comments, instagram_manage_messages.
"""
import json, os, urllib.request, urllib.error, hmac, hashlib


class MetaClient:
    def __init__(self, *, token, ig_user_id, version="v21.0", app_secret="",
                 public_reply_live=False, private_reply_live=False, logger=None):
        self.token = token
        self.ig_user_id = ig_user_id
        self.base = f"https://graph.facebook.com/{version}"
        self.app_secret = app_secret
        self.public_reply_live = public_reply_live
        self.private_reply_live = private_reply_live
        self.log = logger or (lambda o: None)

    # ---- webhook security ----
    def verify_challenge(self, mode, token, challenge, verify_token):
        """GET subscription handshake: return the challenge iff token matches."""
        if mode == "subscribe" and token and token == verify_token:
            return challenge
        return None

    def valid_signature(self, raw_body: bytes, header_sig: str) -> bool:
        """X-Hub-Signature-256 check. If no app_secret configured, skip (dev)."""
        if not self.app_secret:
            return True
        if not header_sig or not header_sig.startswith("sha256="):
            return False
        digest = hmac.new(self.app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest("sha256=" + digest, header_sig)

    # ---- send paths (each dry-run gated) ----
    def _post(self, path, body):
        req = urllib.request.Request(
            f"{self.base}/{path}?access_token={self.token}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return e.code, {"error": e.read().decode()[:300]}
        except Exception as e:
            return 0, {"error": str(e)[:200]}

    def reply_to_comment(self, comment_id, text):
        if not self.public_reply_live:
            self.log({"act": "ig_public_reply", "dry": True, "comment_id": comment_id, "text": text})
            return {"dry": True}
        s, d = self._post(f"{comment_id}/replies", {"message": text})
        self.log({"act": "ig_public_reply", "status": s, "comment_id": comment_id, "resp": d})
        return d

    def private_reply_to_comment(self, comment_id, text):
        # The "private reply" path: message a comment author once, within 7 days.
        body = {"recipient": {"comment_id": comment_id}, "message": {"text": text}}
        if not self.private_reply_live:
            self.log({"act": "ig_private_reply", "dry": True, "comment_id": comment_id, "text": text})
            return {"dry": True}
        s, d = self._post(f"{self.ig_user_id}/messages", body)
        self.log({"act": "ig_private_reply", "status": s, "comment_id": comment_id, "resp": d})
        return d

    def send_dm(self, recipient_igsid, text):
        body = {"recipient": {"id": recipient_igsid}, "message": {"text": text}}
        if not self.private_reply_live:
            self.log({"act": "ig_dm", "dry": True, "recipient": recipient_igsid, "text": text})
            return {"dry": True}
        s, d = self._post(f"{self.ig_user_id}/messages", body)
        self.log({"act": "ig_dm", "status": s, "recipient": recipient_igsid, "resp": d})
        return d
