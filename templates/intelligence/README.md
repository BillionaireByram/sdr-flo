# Intelligence layer (scoreboard + optimizer)

Drop-in self-optimization for any SDR Flo install. See [../../docs/05-intelligence.md](../../docs/05-intelligence.md).

- `intelligence.py` — the engine (scoreboard tally + plain-English report; champion/challenger optimizer with protected core, gauntlet, materiality gate, versioning, auto-rollback).
- `config.example.json` — per-client config: state_db/log/service, bridge/model, vault_reports, targets, min_convos, per-motion objective_marker/objective_kind/protected, and the gauntlet scenarios.

Run: `intelligence.py daily` (00:00) · `intelligence.py weekly` (Sun 00:30) · `scoreboard [daily|weekly]` (read-only) · `rollback <motion>`.
Ship with `INTEL_DRY=1` (shadow); flip to `0` for live self-optimization.
