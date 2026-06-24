# 04 — Objectives (the motions)

SDR Flo runs the same stage machine for every job. Only **Stage 8 (Convert)** and the **objective marker** (what counts as a "hit" for the scoreboard) change. A client can run multiple motions at once (e.g., Takeoff runs Book + Community).

## Configure a motion

In the relay/intelligence config, each motion declares:
```json
{
  "objective_label": "what we are driving to (human readable)",
  "outcome_name": "link sent | call booked | sold | registered",
  "objective_marker": "<text the agent sends>  OR  __BOOKED__ / __SOLD__",
  "objective_kind": "marker | book | sell",
  "protected": ["...anchors the optimizer must keep verbatim..."]
}
```

## Book a call
- **Stage 8:** two-option close → `get_availability` (Google Calendar freeBusy, lead's timezone, weekday + business hours, 2h min notice) → offer 2–3 slots → `book_call` (re-check, events.insert, Meet link, reminders). Never fake a booking; on failure tag system-down + say the team will follow up.
- **Hit =** a `book` action fired (`objective_kind: book`).
- **Lock-in:** sticky booking; 24h + 2h reminders; reschedule/cancel tools; no sales follow-ups to booked leads.

## Push to a community
- **Stage 8:** after rapport + situation, drop the **tracked community link** mid-conversation (never on message 1, never the instant they say a keyword). Collect name → phone → email one at a time, then send the link tied to their situation. Optionally deliver a free resource mid-conversation as nurture.
- **Hit =** the tracked link string appears in an outbound message (`objective_kind: marker`, `objective_marker` = the link slug).
- Example: Takeoff University (`/urls/l/...`).

## Sell a low-ticket offer
- **Stage 8:** qualify for fit → present the offer tied to their problem → handle price/timing objections → send the **checkout link**. Keep it conversational; the close is the link + a nudge.
- **Hit =** checkout link sent, or payment webhook received (`objective_kind: sell`; pair with a payment-confirmation event for a true "sold" count).
- Re-engage on abandonment.

## Get into a webinar / free training
- **Stage 8:** bridge the training as the logical next step for their exact situation, drop the **registration link** mid-conversation, confirm registration, set the expectation to show up live, nudge before it starts.
- **Hit =** registration link sent / `registered` (`objective_kind: marker`).
- **Hand-off:** after the webinar, the existing post-webinar machine (warm voice call on watch % ≥ threshold) takes over. SDR Flo's job ends at registration + show-up.

## Qualification (OR-logic)
Each motion defines an ICP gate, usually **OR-logic** so a lead qualifies on any strong signal (e.g., credit ≥ X **OR** revenue ≥ Y). The skill asks the gating questions in order, qualifies on the first satisfied condition, and routes non-qualifiers to a **downsell** motion (e.g., not-ready-to-book → push to community) with the right tags.

## Tags per motion
Every motion uses tags to drive routing + the scoreboard: an **enable tag** (the fail-closed gate — Flo only engages tagged leads), stage/outcome tags (qualified, booking-intent, link-sent, registered, sold), and downsell tags. The relay applies them; GHL workflows gate on them.
