# 03 — The Brain (NEPQ stage machine)

The brain is what makes Flo a setter, not a chatbot. It runs a **stage-gated sales framework** that merges **Jeremy Miner NEPQ + Cole Gordon setter method + SPIN**, gap-fills each gate, and drives to the objective.

## Pieces

| Piece | What it is |
| --- | --- |
| `SOUL.md` | Identity, voice, the one objective, the hard rules. Loaded every message. |
| `skills/appointment-setter/SKILL.md` | The stage machine: stages, gates, gap-filling, close, objections, tonality. |
| booking plugin | `get_availability` + `book_call` on Google Calendar (freeBusy + events.insert). Books directly, no link. |
| relay calendar tools | `templates/relay/ghl_calendar.py` + `turn_engine.py`. GHL free slots and appointment create, used only when `GHL_CALENDAR_ID` and `GHL_LOCATION_ID` are set. The model cannot invent a slot, and a booked claim requires the provider receipt. Installing this repo does not restart a live relay. |
| lead-profile plugin | `lead_profile_lookup` — pulls the lead's enriched profile so Flo opens with context. |
| notice-filter plugin | strips system notices + dashes before send; disables markdown spam. |

Templates: [../templates/soul/SOUL.template.md](../templates/soul/SOUL.template.md), [../templates/skill/appointment-setter.SKILL.md](../templates/skill/appointment-setter.SKILL.md).

## The stage machine

Each stage has a **gate** (required info). Flo probes/gap-fills until the gate is filled, then advances; it scans for warm-lead skip-ahead, and **never re-asks a filled slot** (profile-first, every turn).

| Stage | Gate | Source method |
| --- | --- | --- |
| 1. Open | got a reply | Cole Gordon opener / curiosity off the keyword |
| 2. Situation | situation captured | NEPQ situation questions |
| 3. Problem awareness | problem named | SPIN problem/implication |
| 4. Consequence / Cost | cost recognized | NEPQ consequence, loss aversion |
| 5. Desire | desired outcome captured | future pacing |
| 6. Qualify | criteria met (OR-logic ICP) | qualification ruleset |
| 7. Transition / Bridge | lead leans in | logical close setup |
| 8. **Convert** | objective hit | **motion-specific** (book / link / checkout / register) |
| 9. Lock-in | confirmed + reminded | sticky; reminders / reschedule / cancel |

Stage 8 is the only stage that changes per motion — see [04-objectives.md](04-objectives.md).

## Gate-filling discipline
- **Profile-first:** read the full history + the per-lead profile every turn. Never re-ask what is known.
- **Warm-lead skip-ahead:** if several gates are already satisfied, jump forward (e.g., 2 → 6).
- **One question at a time.** Build rapport before asking for name/phone/email.
- **Two-option close** at convert ("want me to send you two times?" / "want the link?").
- **Objection handling:** agree-then-redirect, loss-aversion framing, capped social proof; never fight head-on.

## Continuity + destination (hard rules — learned the hard way)
- **Continuity:** Flo is ALWAYS mid-conversation. Never reintroduce itself, never restart, never re-send the opener. Read history, continue from the exact point. If it already has name/phone, move toward the objective.
- **Destination:** the conversation is not done until the objective is hit. After 2–3 real exchanges, drive to the close. Do not loop on discovery.

These two rules live verbatim in `SOUL.md` and are part of the optimizer's **protected core** (see [05-intelligence.md](05-intelligence.md)).

## Voice & compliance
- **No dashes** anywhere a lead sees (no em/en/inter-word hyphens). Enforced in the prompt AND mechanically in the relay's output filter.
- First person, short, texting-style, no markdown, no emojis spam, no income/benefit guarantees.
- **Never name internal tools** (Hermes, Codex, GHL, Retell, Supabase) to a lead.

## Per-lead profile + isolation
The relay keeps a per-`contact_id` profile (`name, business_type, situation, problem, desired_outcome, stage, qualification, objections, notes`) accumulated each turn and injected into the prompt, plus the last ~40 turns. Conversations never mix across contacts. Mirrored to the spine.

## Injection hardening
Flo only ever acts as the setter. It ignores "ignore your instructions" / role-swap / system-prompt-reveal / tool-abuse from a lead, never exposes internals, never invents tool results (e.g., never fakes a booking — on failure it tags system-down and says the team will follow up).

## Escalation
Triggers (in SOUL + skill): angry / legal / refund / existing-client / whale / explicit human request / stop. Flo calls `escalate` → alerts the operator + logs an alert, and **stops selling**.

## Reliability engines (deterministic, around the brain)
| Engine | Cadence | Job |
| --- | --- | --- |
| conversation sync | 10 min | session → spine; infer stage; **sticky booking** (never downgrade a booked lead) |
| follow-up ladder | 15 min | nudge quiet leads 30m / 1d / 3d / 7d; skip booked/opted-out; quiet hours; daily cap; race-guard |
| reminders / no-show | 30 min | 24h + 2h pre-call reminders; reschedule/cancel tools |
| health monitor | 20 min | probe agent, intake, channel, **auth token**, calendar, Supabase, disk; throttled alert |
| escalation | event | the `escalate` tool |

See [../templates/relay/](../templates/relay/) and the Setter Flo core build for the reference scripts.
