# SDR Policy State Machine

Deterministic policy layer for SDR Flo. Policy decides **whether** to act before the
model decides **how** to phrase it. Pairs with the flo-core `policy-backbone`
framework (engine repo: `flo-core/frameworks/policy-backbone/`).

## State machine

```text
sourced → enriched → qualified → outreach-ready → approved
→ sent → replied → engaged → meeting-booked → opportunity

Exit paths: nurture | disqualified | opted-out | escalated
```

A transition is valid only when the policy evaluator approves it AND the required
evidence is stored. Fallback on any uncertainty is `needs review` — never an
autonomous send.

## OutreachPolicy controls

- ICP / account-fit criteria
- Contact role and evidence quality
- Consent basis and suppression status
- Jurisdiction/channel eligibility
- Approved claims and proof links
- Send windows, domain/provider, per-contact cadence, follow-up cap
- High-value / restricted-industry / uncertain-data review conditions
- Calendar booking and CRM handoff ownership

## Module map

| Module | Owns |
|---|---|
| `source-flo` | Account list intake, provenance, dedupe |
| `enrich-flo` | Source-grounded firmographic/contact research |
| `qualify-flo` | Deterministic ICP scoring → allow / deny / review |
| `outreach-flo` | Evidence-bound personalization + pre-send compliance validation |
| `sequence-flo` | Cadence, provider receipts, delivery/bounce/reply/opt-out webhooks |
| `reply-flo` | Classify reply, route objections, book calls, or suppress |
| `handoff-flo` | Qualified meeting/opportunity summary pushed to GHL |
| `sdr-owner-flo` | Daily pipeline, approval queue, deliverability exceptions, attribution |

## Decision trace (mandatory per action)

evidence → policy version → proposal → approval → provider receipt → next state

## MVP sequence

1. One ICP. One approved email provider.
2. Source → enrich → score → owner-approved first touch → reply classification →
   booked-call handoff.
3. No multichannel autonomy, no LinkedIn automation, no mass sends until
   consent/deliverability controls prove out.

## Sources

Distilled 2026-07-16 from vault
`wiki/research/local-service-sdr-flo-policy-framework-2026-07-15.md`. State-machine
and decision-trace patterns adapted from DavidDiazMerino/cashfromchaos — repo has
NO tracked license: ideas only, never copy its source, UI, or assets.
