# Instagram social-CTA channel (comment → DM → qualify → book)

The SDR Flo channel adapter for Instagram organic content CTAs. **Official Meta Graph API only** — we never use the unofficial/private API (account-ban risk). Built by lifting the best patterns from open-source (InstaAuto's comment→DM + Supabase shape, ig-mcp's official Graph API send paths) into our own canonical, brain-owning implementation.

> This is a channel **adapter** that feeds the canonical SDR Flo brain + spine. It is NOT a parallel bot. Per-niche persona is config: **Client Zero = Byram's personal IG, so the agent speaks AS Byram**, never "Flo" or any internal name.

## The loop
```
IG comment "FLO"  → comments webhook → keyword router → (public reply) + private DM opener
lead replies (DM) → messages webhook → SDR Flo brain (SOUL.byram.md, NEPQ) → qualify → book / give value
everything        → the spine (leads, conversations, events, sources)  [SQLite now, Supabase wired next]
```

## Files
- `ig_adapter.py` — webhook server + `handle_comment` / `handle_message` (pure, testable) + keyword router + spine writer + idempotency + dry-run gating + brain handoff.
- `meta_client.py` — official Graph API client: `reply_to_comment`, `private_reply_to_comment`, `send_dm`, webhook verify + signature. Every send dry-run gated.
- `SOUL.byram.md` — the Byram-voice persona (per-niche persona config of the SDR Flo brain).
- `config.example.json` — per-campaign CTA config (keyword `FLO`, offer, value_link, public/private toggles, opener copy).
- `env.example` — Meta app + tokens + flags (all placeholders).
- `tests/` — fixtures + 10 tests (verify, keyword→spine+draft, non-keyword no-DM, dedup, DM→brain, opt-out + guard suppression, no-internal-names/no-dashes, dry-run-no-send, envelope dispatch).

## Safety (baked in)
- **Shadow-first:** `SDR_FLO_DRAFT_ONLY=true` (default) drafts + persists everything, sends nothing. Live needs `IG_PUBLIC_REPLY_ENABLED` / `IG_PRIVATE_REPLY_ENABLED` flipped *and* draft-only off.
- **Idempotent** on comment id + message id (no double public-reply/DM).
- **Suppression** at intake + reply: booked/customer/existing-client/human-owned/opted-out/support/billing/refund/complaint + "stop"/"unsubscribe".
- **Never** emits internal tool names; **no dashes** lead-facing; **never** fakes a booking.

## Run
- Tests (offline, dry): `python3 -m unittest tests.test_ig_adapter -v`
- Server: `python3 ig_adapter.py` (handles GET verify + POST events on `:8820`).

## Go-live (after Byram authenticates the Meta app)
1. Create the Meta app (Instagram product) + connect the FB Page linked to @billionaireb; permissions `instagram_basic`, `instagram_manage_comments`, `instagram_manage_messages`.
2. Fill `.env` (App ID/Secret, IG user id, page token, verify token).
3. Point the Instagram webhook (fields: `comments`, `messages`) at this adapter's public URL; complete the verify challenge.
4. Point `RELAY_BRIDGE` at the Codex/Max reasoning bridge so the Byram brain reasons live.
5. Dry-run on a real post first; then flip the live flags on one keyword and watch.

## Roadmap (v2)
Value-post → gift-for-email/phone with per-post tracked links (needs the link-org system) · Chatwoot as the DM inbox/human-handoff surface · Supabase spine write (swap the SQLite calls).
