# Intelligence layer (scoreboard + optimizer)

Drop-in self-optimization for any SDR Flo install. See [../../docs/05-intelligence.md](../../docs/05-intelligence.md).

- `intelligence.py` — the engine (scoreboard tally + plain-English report; champion/challenger optimizer with protected core, gauntlet, materiality gate, versioning, auto-rollback).
- `config.example.json` — per-client config: state_db/log/service, bridge/model, vault_reports, targets, min_convos, per-motion objective_marker/objective_kind/protected, and the gauntlet scenarios.
- `call_audit.py` — validates finding-level evidence references and emits least-privilege Marketing, Sales Manager, and Owner reports as JSON + inert Markdown in separate owner-only role directories. Atomic symlink-safe writes and a locked processed-call ledger enforce cross-run once-per-call behavior.
- `call-audit-config.example.json` — client rollout reference for transcript source, score dimensions, destinations, and retention.

Run: `intelligence.py daily` (00:00) · `intelligence.py weekly` (Sun 00:30) · `scoreboard [daily|weekly]` (read-only) · `rollback <motion>`.
Ship with `INTEL_DRY=1` (shadow); flip to `0` for live self-optimization.

Call-audit quick run: `python3 call_audit.py report --input audits.jsonl --output reports/2026-08-10 --state-dir state/call-audit --period 2026-08-10 --timezone America/New_York`. Reuse the stable state directory across every reporting window. Keep external report delivery disabled until each role destination is approved.
