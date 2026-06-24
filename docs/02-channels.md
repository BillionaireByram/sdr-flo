# 02 — Channels

One brain behind every channel. Each channel is either **gateway-native** or comes through the **relay**. Below: the exact integration for each, with contracts, endpoints, and gotchas.

## Integration matrix

| Channel | Path | Inbound | Outbound | Key gotcha |
| --- | --- | --- | --- | --- |
| Instagram / Facebook DM | GHL relay | GHL "Customer Replied" webhook | `POST /conversations/messages` type `IG`/`FB` | Cloudflare needs a browser `User-Agent` or 1010 |
| TikTok DM | GHL native TikTok relay | GHL "Customer Replied" webhook | `POST /conversations/messages` type `TIKTOK` | comment→DM is a GHL workflow; relay sends replies only |
| SMS | GHL SMS or Twilio | GHL webhook / Twilio webhook | `type:SMS` or Twilio `/Messages` | consent + warmup + 1/sec |
| iMessage | Photon | sidecar (persistent) | `photon_send(phone,text)` | device must stay online; iMessage ≠ SMS |
| Email | Gmail connector / AgentMail | IMAP IDLE / poll | SMTP via per-account proxy | app password + warmup + encrypt at rest |
| Voice | Retell (any provider) | n/a (outbound) | `POST /v2/create-phone-call` + `override_agent_id` | metadata must carry the CRM contact id |
| Webinar | WebinarKit / Zoom | registration + attendance webhooks → spine | n/a (read from spine) | watch % ≥ threshold triggers post-webinar voice |

## GHL Conversations (IG, FB, TikTok, SMS) — the shared adapter

This one adapter serves four channels; only the `type` changes.

**Inbound** — a GHL workflow forwards each inbound message to the relay:
- Trigger: **Customer Replied**, filtered to the channel + the enable tag (so the relay only ever sees opted-in leads).
- Action: **Custom Webhook** → `POST http://<relay>:<port>/inbound`, header `x-webhook-secret: <SECRET>`, body:
```json
{ "contact_id":"{{contact.id}}", "text":"{{message.body}}", "tags":"{{contact.tags}}",
  "first_name":"{{contact.first_name}}", "phone":"{{contact.phone}}", "channel":"ig|fb|tiktok|sms" }
```

**Outbound** — `POST https://services.leadconnectorhq.com/conversations/messages`
- Headers: `Authorization: Bearer <GHL_PIT>`, `Version: 2021-04-15`, **`User-Agent: Mozilla/5.0 ...`** (omit it → Cloudflare 1010).
- Body: `{ "type":"IG|FB|TIKTOK|SMS", "contactId":"<id>", "message":"<text>" }` (type is **uppercase**).
- Chunk messages over ~950 chars; stagger sends 100ms–1s; skip outbound echoes.

**TikTok comment → DM** is a GHL automation (not the relay): comment contains the keyword → tag `*-lead` → public reply ("just sent you a dm") → opener DM → replies land in Conversations → the inbound webhook above. The relay supplies the copy; GHL fires it.

## SMS (GHL or Twilio)
GHL SMS uses the adapter above (`type:SMS`). Twilio is the fallback for non-GHL / international: inbound webhook on receive, outbound `POST /Messages`. Compliance: explicit consent/opt-in, US 1 msg/sec, warmup (start ~10/day, ramp to ~150), strip dashes (carriers double-encode).

## iMessage (Photon)
Photon line + sidecar on a Mac/device. Persistent connection, no webhook/tunnel. Inbound forwarded as events `{phone,text,ts}`; outbound via `photon_send(phone,text)`. One **dedicated Photon project per client/line** (sharing a project bleeds conversations). Device must stay online. 1:1 only, not mass outreach. Pair with consent gating + daily cap; fall back to GHL SMS / Twilio for non-Apple numbers.

## Email (Gmail connector / AgentMail)
Primary: per-client Gmail via app password (IMAP `imap.gmail.com:993`, SMTP `smtp.gmail.com:587`), each account on a stable proxy, encrypted at rest, warmup-ramped to ~150/day. Read inbox via IMAP IDLE/poll; send via SMTP; extract verification codes by inbox search. Fallback: AgentMail (legacy). Email is also the future home of the **cold outreach** roadmap item.

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
- **Channel send-fallback.** One CRM location commonly holds **IG + SMS** leads (you DM some, you text others). Sending the wrong message `type` for a conversation returns **422** and the reply *silently never delivers*. The relay retries `SMS`/`Email`/`FB` on a 422.
- **Guard tags = intentional kill switches only.** Never put a tag in the guard list that some workflow mass-applies — a noisy `ai off`-style tag will mute hundreds of real leads with no error. Real kill switches: `do-not-contact` / `manual` / `dnd` / `existing-client` (hard) + remove the enable-tag (soft).
- **Recovery sweep.** To catch leads missed during a misconfig, sweep the CRM inbox (recent conversations), and for each whose last message is inbound, re-post it through the relay — the gate self-selects keyword leads and the send-fallback delivers. Idempotent (already-answered = last message outbound = skipped).
