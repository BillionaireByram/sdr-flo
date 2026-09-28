# 02 — Channels

One brain behind every channel. Each channel is either **gateway-native** or comes through the **relay**. Below: the exact integration for each, with contracts, endpoints, and gotchas.

## Integration matrix

| Channel | Path | Inbound | Outbound | Key gotcha |
| --- | --- | --- | --- | --- |
| Instagram / Facebook DM | GHL relay | GHL "Customer Replied" webhook | `POST /conversations/messages` type `IG`/`FB` | Cloudflare needs a browser `User-Agent` or 1010 |
| TikTok DM | GHL native TikTok relay | GHL "Customer Replied" webhook | `POST /conversations/messages` type `TIKTOK` | comment→DM is a GHL workflow; relay sends replies only |
| SMS | GHL SMS or Twilio | GHL webhook / Twilio webhook | `type:SMS` or Twilio `/Messages` | consent + warmup + 1/sec |
| iMessage | Photon | sidecar (persistent) | `photon_send(phone,text)` | device must stay online; iMessage ≠ SMS |
| Email | Approved AgentMail sender | AgentMail inbound event | AgentMail send with Byram CC | Verify active sender and exact recipients before every send |
| Voice | Retell (any provider) | n/a (outbound) | `POST /v2/create-phone-call` + `override_agent_id` | metadata must carry the CRM contact id |
| Webinar | WebinarKit / Zoom | registration + attendance webhooks → spine | n/a (read from spine) | watch % ≥ threshold triggers post-webinar voice |

## GHL Conversations (IG, FB, TikTok, SMS) — the shared adapter

This one adapter serves four channels; only the `type` changes.

**Inbound** — a GHL workflow forwards each inbound message to the relay:
- Trigger: **Customer Replied**, filtered to the intended channel and campaign. Comment-triggered leads must have the enable tag before this workflow fires. A direct keyword DM can self-tag only on its first turn.
- Action: **Custom Webhook** → `POST http://<relay>:<port>/inbound`, header `x-webhook-secret: <SECRET>`, body:
```json
{ "contact_id":"{{contact.id}}", "text":"{{message.body}}", "messageId":"<GHL inbound message ID>",
  "locationId":"<verified GHL location ID>", "accountId":"<verified source account ID>",
  "first_name":"{{contact.first_name}}", "phone":"{{contact.phone}}", "channel":"IG" }
```
Use actual GHL workflow variables for the message and source IDs; verify their rendered values with a controlled inbound event. A missing stable message ID, mismatched channel/location, or account outside `RELAY_ALLOWED_ACCOUNT_IDS` is rejected before reasoning or sending. Configure one relay instance per sender identity and channel with its own `GHL_MSG_TYPE`, location, account allowlist, persona, and state database. Never infer the sender identity from the contact alone.

**Outbound** — `POST https://services.leadconnectorhq.com/conversations/messages`
- Headers: `Authorization: Bearer <GHL_PIT>`, `Version: 2021-04-15`, **`User-Agent: Mozilla/5.0 ...`** (omit it → Cloudflare 1010).
- Body: `{ "type":"IG|FB|TIKTOK|SMS", "contactId":"<id>", "message":"<text>" }` (type is **uppercase**).
- Chunk messages over ~950 chars; stagger sends 100ms–1s; skip outbound echoes.

**TikTok comment → DM** is a GHL automation (not the relay): comment contains the keyword → tag `*-lead` → public reply ("just sent you a dm") → opener DM → replies land in Conversations → the inbound webhook above. The relay supplies the copy; GHL fires it.

**Instagram comment → DM (Client Zero):** in each verified Instagram account's GHL workflow, use the Instagram Comment trigger with an explicit post and keyword phrase; add the enable tag; send one initial DM through GHL's Reply to Comment via DM action; then route Customer Replied events to the scoped relay. Record the comment ID, tag readback, opener message ID, reply message ID, and appointment ID. Keep the personal `@billionaireb` and MyDigitalFlo company identities in separate workflows and relay instances. A keyword on a personal post must never enable an unrelated company conversation or take over an existing human thread. Disable any other automated reply/follow-up writer for the same account and contact segment before activation.

## SMS (GHL or Twilio)
GHL SMS uses the adapter above (`type:SMS`). Twilio is the fallback for non-GHL / international: inbound webhook on receive, outbound `POST /Messages`. Compliance: explicit consent/opt-in, US 1 msg/sec, warmup (start ~10/day, ramp to ~150), strip dashes (carriers double-encode).

## iMessage (Photon)
Photon line + sidecar on a Mac/device. Persistent connection, no webhook/tunnel. Inbound forwarded as events `{phone,text,ts}`; outbound via `photon_send(phone,text)`. One **dedicated Photon project per client/line** (sharing a project bleeds conversations). Device must stay online. 1:1 only, not mass outreach. Pair with consent gating + daily cap; fall back to GHL SMS / Twilio for non-Apple numbers.

## Email (AgentMail)
Outbound email uses the verified, approved AgentMail sender for the active Mission Control agent. Include `byram@mydigitalflo.io` as CC on every outbound email, and send only to the exact requested recipients. Capture the provider message ID. If the sender cannot be verified, stop; do not fall back to Gmail or SMTP. Email is outside the inbound social launch until this identity check and an end-to-end receipt are proven.

## Voice (Retell, or any provider)
One number per client, multiple personas routed by `override_agent_id`. Trigger: `POST https://api.retellai.com/v2/create-phone-call` with `retell_llm_dynamic_variables` (personalization) + `metadata.contact_id` (required for the post-call webhook to attribute). **Warm-only**: only call leads above a score/watch threshold (gate in the brain, not Retell). Booking during a call uses serverless functions (`check-availability`, `book-appointment`) that write the calendar only on confirmation. Post-call webhook → `retell_call_log` + next action. Provider is abstracted — Retell today, swappable.

## Webinar funnel
Registration funnel (WebinarKit/Zoom, Netlify-hosted) → contact + `registered` tag → spine `webinar_registrations`. Attendance webhook → `webinar_attendance_events` with `watch_percent`. Post-webinar routing: watch % ≥ threshold → warm voice call (Retell hot closer); below → SMS/email nurture. The SDR Flo brain owns getting them **registered + shown up**; the post-webinar closer is the next stage.

## Universal relay rules (every channel)
- Validate the secret on every inbound. **Keyword-OR-tag gate** (below). Per-contact isolation.
- Strip dashes; never emit internal tool names; suppress empty/degenerate output; retry on bad model output.
- Dry-run flag before go-live. Mirror every message to the spine (`conversations` + `events`, channel-tagged).

## Hard-won field lessons (baked into the relay template)
- **Keyword-OR-tag gate, not pure tag.** A pure "only engage tagged leads" gate silently blocks your *entire* pipeline whenever the CRM workflow isn't reliably tagging (wrong trigger, narrow keyword list, tag/webhook race). The relay engages on **enable-tag OR a campaign keyword**, and **self-tags** the lead the moment they open with a keyword. This is what both lets real leads through and keeps the bot out of personal DMs.
- **Channel send receipt.** A 422 or a response without a message ID is unconfirmed delivery. Keep the reply on its verified channel and escalate for review; do not retry through SMS, email, or Facebook just because the contact has another address.
- **Guard tags = intentional kill switches only.** Never put a tag in the guard list that some workflow mass-applies — a noisy `ai off`-style tag will mute hundreds of real leads with no error. Real kill switches: `do-not-contact` / `manual` / `dnd` / `existing-client` (hard) + remove the enable-tag (soft).
- **Recovery sweep.** To catch leads missed during a misconfig, inspect recent CRM conversations and reconcile each unanswered inbound against the relay's event and provider receipt. Reprocessing requires the same channel and a stable message ID; uncertain sends go to human review.
