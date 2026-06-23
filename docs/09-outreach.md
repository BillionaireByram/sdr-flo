# 09 — Outbound (cold outreach engine)

The outbound front door of SDR Flo. Cold outreach is **not a separate tool — it is the front door of the Acquisition Engine.** It decides who is worth contacting and why, reaches them, and pushes every positive reply into the same brain: qualify → convert → follow up → learn.

> Builds on the DigitalFlo Cold Outreach Engine (`digitalflo-app`, 2026-05-07): source → research → score → gift → approve → sequence → reply → book → learn, with 8 Supabase tables (`outreach_campaigns`, `outbound_prospects`, `prospect_research`, `outreach_approvals`, `outreach_sequences`, `outreach_events`, `outreach_suppression`, `outreach_assets`). This doc upgrades that framework with 2026 winning practices.

## The 2026 reality (why the order changed)
- Average cold email reply rate is **~3.43%**. Signal-anchored, tightly-targeted outreach hits **15–25%** (a 5x lift). "Good" = 5–10%, "elite" = >10%.
- **Infrastructure and targeting now matter more than copy.** Personalization is the *final* layer, not the foundation. The order of leverage is: deliverability → data/targeting → offer → sequence → copy.
- Opens are dead as a metric (Apple Mail Privacy inflates them). **Reply rate and positive-reply rate are the north star.**
- First email captures ~58% of replies; follow-ups capture the other ~42%. Multichannel beats email-only by up to ~287%.

## Layer 0 — Infrastructure & deliverability (the new foundation)
Do this before a single send. Most "my cold email doesn't work" is a Layer 0 failure.
- **Separate sending domains**, never the primary/brand domain. Prefer **aged domains (12+ months)**; buy + park ahead of campaigns. 2–4 lookalike domains per client to spread reputation risk.
- **Pre-warmed mailboxes** (Google Workspace / M365), **US IPs**, multiple inboxes per domain. Authentication is non-negotiable: **MX + SPF + DKIM + DMARC** correct before sending.
- **Warmup 2–4 weeks**, then keep it running indefinitely: ~5/day week 1 → 35–50/day by week 4.
- **Cap ~25–30 cold sends per mailbox/day.** Scale with more inboxes, not higher per-inbox volume.
- **Performance-based inbox rotation** (route volume to the best-placing inboxes, not blind round-robin).
- **List verification + waterfall** (Layer 2) to keep **bounce < 2–3%**; **spam-complaint < 0.1%** (Google enforces < 0.3%).
- First touch: **plain text, ≤ 1 link (ideally zero), no images, no tracking pixels.** Custom tracking domain only if tracking at all.
- Infra is a buy/operate decision (Primeforge / Mailforge / Infraforge / Instantly / Smartlead / Maildoso for inboxes + warmup). The framework stays tool-agnostic; the relay just needs SMTP/IMAP per the Gmail connector ([02-channels.md](02-channels.md)).

## Layer 1 — Signal-first targeting (the biggest lever)
Stop emailing a static ICP list. **Anchor every prospect to a real buying signal** — that is the 5x.
- **B2B signals:** funding round, leadership/role change, hiring surge (e.g., posting SDR/ops roles), tech-stack change, new location, earnings/news, ad-spend ramp.
- **Local-business signals** (DigitalFlo's bread and butter): unanswered/negative reviews, slow speed-to-lead, weak or missing booking path, running ads to a leaky funnel, competitor capturing demand faster.
- The signal both **gates entry** (only contact when a signal fires) and **becomes the email's reason to exist**. Tie the gift to the signal.

## Layer 2 — Enrichment & verification (waterfall)
- **Waterfall enrichment:** query multiple providers in ranked order until a verified result is found → ~80–90% match, far lower bounce than any single provider. Clay-style orchestration: choose the fields, route each to a ranked source list, verify, gate before it touches the system.
- Dedupe + remove catch-all/risky/role-based addresses. Honor the suppression list (`outreach_suppression`).
- Store the verified contact + the firing signal on `outbound_prospects` (extend with `signal_type`, `signal_detail`, `signal_date`).

## Layer 3 — Research report → fit/intent score
Keep the **12-point research report** and the **scoring model** (already built). Two upgrades:
- Make the report **signal-led** (the firing signal is step 0; the report explains it and finds the leak it implies).
- Score = fit (ICP match) × intent (signal strength/recency) × reachability (verified contact). **Only sequence above the threshold** — outreach energy follows the score.

## Layer 4 — Gift-first proof asset
Keep the **gift menu** (Lead Leak Snapshot, Speed-to-Lead Scorecard, Review-to-Revenue Map, Booking Teardown, Competitor Capture Gap). The gift is **proof the research found a real leak** — it earns the reply. Lead with the artifact, never with "want a call?" Human approval gate stays (`outreach_approvals`).

## Layer 5 — Copy that gets replies
- **Relevance > brevity > single ask > proof > low-friction CTA** (in that order).
- **First line is 100% about them and tied to the signal.** Signal-based openers get ~9% reply; generic AI compliments ("loved your post") get ~1% and are instantly spotted — **banned.**
- **First touch < 80 words** (50–125 max). One idea. No pitch-slapping.
- **Soft, interest-based CTA** — "want me to send it over?" / "worth a look?" — not "book a 30-min call." The gift is the CTA.
- No dashes (house rule), plain text, one link max.

## Layer 6 — Sequence & cadence
- **4–6 touches**, **3-7-7 cadence** (Day 0, 3, 10, 17) — captures ~93% of replies by Day 10. Increasing gaps between touches.
- **Each touch adds new value** (a second proof point, a different angle on the leak, a relevant result) — not "just bumping this up."
- **Break-up email** at the end (permission-to-close; often the second-best performer).
- **Multichannel** (up to ~287% more replies): weave in the channels SDR Flo already owns — Instagram/LinkedIn DM + a call/voicemail — anchored to the same signal. e.g. Day 0 email → Day 3 DM/connect → Day 4 call → Day 7 email → Day 10 DM → Day 14 break-up.
- Send **Tue–Thu, 8–11am / 2–4pm** local. Respect per-inbox daily caps + warmup.

## Layer 7 — Reply capture → the brain (the fold-in)
This is what makes it SDR Flo and not just a blaster.
- Classify every reply (positive / curious / objection / referral / not-now / unsubscribe / OOO).
- **Positive/curious → route into the relay** → the NEPQ brain takes over to qualify → convert (book / community / sell / webinar), carrying the research + signal context. Fast speed-to-lead.
- Unsubscribe/negative → suppress + stop. OOO → reschedule the next touch.
- Email send + inbox read use the **Gmail connector** ([02-channels.md](02-channels.md)); reply events log to `outreach_events` + the spine.

## Layer 8 — Metrics & the learning loop
- **North star: reply rate + positive-reply rate** (per campaign, per signal type, per inbox). Track bounce, spam-complaint, and per-domain reputation health as guardrails. Opens are noise.
- Feed it into the **intelligence layer** ([05-intelligence.md](05-intelligence.md)): the scoreboard tallies outbound → reply → positive → booked by source/signal; the optimizer improves source rules, scoring, gift pick, and copy angles weekly — gated, non-destructive, evolve-only-when-needed.

## Compliance
CAN-SPAM (US): truthful headers, real physical address, working unsubscribe honored fast. GDPR/EU: legitimate-interest basis + easy opt-out. Maintain `outreach_suppression` globally across all campaigns/inboxes. Never email purchased consumer lists.

## Mapping to the existing build + what to add
**Already built (`digitalflo-app`):** the model (`lib/acquisition-engine/cold-outreach.ts`), 8-table schema, API routes (prospects/approvals/send/compliance), dashboard UI, gift assets. Keep it as the **control plane**.
**Add for runtime:**
1. Layer 0 infra (domains/inboxes/warmup) — buy/operate; wire SMTP/IMAP to the Gmail connector.
2. `signal_*` fields on prospects + a signal-source step (Layer 1).
3. Waterfall enrichment + verification step (Layer 2).
4. The **send loop** (cap-aware, rotation, schedule-aware) + warmup guardrails.
5. **Reply classifier → relay handoff** (Layer 7).
6. Outbound metrics into the scoreboard (Layer 8).

These are the build tickets when we go to run live cold campaigns; the framework above is the spec.
