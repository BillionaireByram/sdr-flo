# 11 — Nightly Call Audit (three reports, three jobs)

SDR Flo can audit every completed sales call once, then publish three least-privilege reports for the people who can act on the findings. This extends the existing scoreboard; it does not create a separate product.

## What ships

`templates/intelligence/call_audit.py` provides:

1. A strict, evidence-backed transcript-audit prompt contract.
2. Validation and normalization for audit JSON.
3. Deterministic aggregation across the reporting window.
4. Separate JSON + Markdown outputs for Marketing, Sales Manager, and Owner.
5. A CLI suitable for a nightly systemd timer or approved cron job.

## Three reports, three jobs

| Report | Receives | Does not receive | Job |
| --- | --- | --- | --- |
| Marketing | objection frequency, upstream expectation/message gaps, source performance | raw rep criticism and coaching detail | Fix targeting, offer framing, ads, content, and pre-call expectations. |
| Sales Manager | rep scorecards, coaching moments, objection patterns, training actions | raw owner-only findings and marketing-gap detail | Coach reps and decide the next training block. |
| Owner | summary, source and rep performance, all raw findings, recommended actions | nothing intentionally filtered | See the unfiltered operating truth and choose priorities. |

The role split is a privacy and actionability control, not three copies of the same summary.

## Portable nightly pipeline

```text
approved recorder/transcript source
  -> client adapter exports completed calls
  -> authenticated local Sales Flo brain runs build_audit_prompt(...)
  -> one validated JSON audit per call
  -> call_audit.py report
  -> role files written
  -> approved delivery adapters route each file to its destination
```

Use the client's existing approved recorder/transcript source: Fathom, Zoom, GHL, Retell, or another contract-approved source. Do not record calls silently. The adapter is client-specific; the audit and reporting contract is not.

## Audit JSON contract

Each JSONL row requires:

- call identity/time, rep, lead source, duration, and outcome
- 0–10 scores by configured dimension
- normalized objections
- upstream marketing/message gaps
- specific coaching moments
- raw findings
- next actions
- evidence objects containing a transcript timestamp, verbatim quote, and exact `field:index` support references (for example `marketing_gaps:0`)

Every objection, gap, coaching moment, raw finding, and next action must have an exact evidence reference. Outcomes use one fixed taxonomy: `won`, `closed_won`, `booked`, `sold`, `lost`, `no_show`, `follow_up`, or `other`; unknown values fail closed. The validator also rejects malformed/timezone-free call timestamps, invalid reporting dates, non-finite numeric values, unknown evidence keys, invalid support indexes, and duplicate IDs in the current batch. Transcript content is serialized inside an explicit untrusted-data boundary so instructions inside a call cannot redefine the audit job.

## Run

```bash
python3 templates/intelligence/call_audit.py report \
  --input /var/lib/sdr-flo/call-audits/2026-08-10.jsonl \
  --output /var/lib/sdr-flo/call-reports/2026-08-10 \
  --state-dir /var/lib/sdr-flo/call-audit-state \
  --period 2026-08-10 \
  --timezone America/New_York
```

Outputs are isolated by role and written with owner-only permissions (`0700` directories, `0600` files):

```text
marketing/report.json
marketing/report.md
sales_manager/report.json
sales_manager/report.md
owner/report.json
owner/report.md
```

The stable `--state-dir` contains private `processed-call-ids.json` and `call-audit.lock` files. It must be reused across every reporting window and must be a separate, non-overlapping path from the report output; this prevents moving to a new daily output directory from reprocessing an old call and keeps state out of role delivery trees. A durable `pending-call-batch.json` marker is written before reports and removed only after the ledger is fsynced. If a crash leaves an incomplete marker, later runs fail closed until an operator verifies/rolls back the partial report and reconciles the ledger. The CLI receipt includes the period, timezone, call count, output directory, and state directory. Reusing a processed `call_id` fails closed.

## Scheduling

Schedule after the client's call/transcript source is complete for the day. Recommended default is 00:30 local business time with a persistent timer. Keep report generation separate from delivery:

1. Generate and verify all six files.
2. Confirm the call count matches the source export.
3. Deliver only through approved role destinations.
4. Record destination receipts.

Default new-client rollout is shadow mode: write reports locally for review, send nothing. Enable delivery only after destination and retention approval.

## Client packaging

This becomes a standard Sales Flo intelligence module for clients with recorded calls:

- **Call Truth:** evidence-backed audit of every completed call.
- **Message Loop:** objections and expectation gaps feed Marketing.
- **Coaching Loop:** specific moments and scorecards feed the sales manager.
- **Owner View:** unfiltered findings and priorities reach the owner.

Client-specific configuration is limited to transcript source, score dimensions, outcome taxonomy, reporting timezone, destinations, and retention policy. Do not fork the engine by niche.

## Safety and privacy

- Confirm recording consent and the client's retention policy before activation.
- Keep raw transcripts out of broad channels.
- Route reports by least privilege; Marketing does not need raw rep findings. Keep each role directory on a separate delivery ACL/account rather than granting a shared delivery worker access to the output root.
- Evidence supporting `raw_findings` is owner-only. It may not share an evidence row with lower-privilege fields, and the same normalized quote may not be reused in Marketing or Sales Manager evidence; use distinct timestamped quotes for owner, coaching, and marketing observations.
- Report writes reject symlinked path components, use atomic replacement, and enforce `0700` directories plus `0600` files. Do not weaken those permissions in delivery jobs.
- Markdown neutralizes transcript-controlled HTML, formatting, generic URI schemes, email/bare-domain autolinks, and remote-image URLs before rendering.
- Never infer a win, booking, or payment without source proof.
- Do not auto-change prompts or launch training solely from one call. Aggregate patterns and use the existing materiality/champion-challenger gates.
- External delivery remains approval-gated unless the client workflow explicitly authorizes it.

## Verification

```bash
python3 -m unittest discover -s templates/intelligence/tests -v
python3 -m unittest discover -s templates/channels/instagram/tests -v
```
