# Channel adapters — quick config

The relay ships with the GHL Conversations adapter (IG/FB/TikTok/SMS). To add a channel, point the relay's `send_reply()` (and the inbound webhook) at it. Full contracts + gotchas in [../../docs/02-channels.md](../../docs/02-channels.md).

## GHL Conversations (IG / FB / TikTok / SMS) — built in
- Inbound: GHL workflow "Customer Replied" (filter to channel + enable tag) → Custom Webhook → `:PORT/inbound`, header `x-webhook-secret`.
- Outbound: `POST /conversations/messages`, `Version: 2021-04-15`, browser `User-Agent`, body `{type, contactId, message}`. `type` ∈ `IG|FB|TIKTOK|SMS` (uppercase). Set `GHL_MSG_TYPE`.
- TikTok: comment→DM is a GHL automation; the relay handles replies only.

## Twilio (SMS) — swap send_reply()
- Inbound: Twilio webhook → normalize. Outbound: `POST /Messages` (account SID + token). Consent + 1/sec + warmup.

## Photon (iMessage) — sidecar
- Persistent sidecar; inbound events `{phone,text}`; outbound `photon_send(phone,text)`. Dedicated Photon project per client. Device online required.

## Gmail (email) — connector
- IMAP IDLE/poll inbound; SMTP outbound via per-account proxy; app password; warmup to ~150/day; encrypt creds at rest.

## Retell (voice) — adapter, outbound
- `POST /v2/create-phone-call` + `override_agent_id` + `metadata.contact_id`. Warm-only gate in the brain. Post-call webhook → `retell_call_log` + next action. Provider is swappable.

## Webinar (WebinarKit/Zoom) — ingest
- Registration + attendance webhooks → spine. Watch % ≥ threshold → warm voice call. SDR Flo owns registration + show-up; the post-webinar closer is the next stage.

## Instagram (organic CTA: comment -> DM -> qualify -> book) — built
Official Graph API only. See [instagram/README.md](instagram/README.md). Comment keyword router + private DM + brain handoff + spine, shadow-first. Persona is per-niche (Client Zero = Byram's voice).
