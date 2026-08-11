# Three Role Call Audit Implementation Plan

> **For Hermes:** Execute task by task with strict red-green-refactor TDD.

**Goal:** Add a reusable nightly sales-call audit module that turns normalized call audits into separate Marketing, Sales Manager, and Owner reports for Sales Flo and client deployments.

**Architecture:** Keep transcript interpretation provider-agnostic through a versioned JSON audit contract and prompt builder. Aggregate validated audit records deterministically into three role-specific JSON and Markdown reports, so each client can plug in its approved recording/transcription source and its own authenticated reasoning bridge without forking the framework.

**Tech Stack:** Python 3 standard library, JSON/JSONL, unittest, Markdown.

---

### Task 1: Lock the audit contract and role outputs

**Files:**
- Create: `templates/intelligence/tests/test_call_audit.py`
- Create: `templates/intelligence/call_audit.py`

1. Write failing tests for input validation, deterministic aggregates, role-specific visibility, and no-call behavior.
2. Run `python3 -m unittest discover -s templates/intelligence/tests -v` and verify expected import failure.
3. Implement immutable audit normalization and deterministic aggregation.
4. Re-run the focused suite and verify green.

### Task 2: Add prompt and CLI surfaces

**Files:**
- Modify: `templates/intelligence/tests/test_call_audit.py`
- Modify: `templates/intelligence/call_audit.py`
- Create: `templates/intelligence/call-audit-config.example.json`

1. Write failing tests for prompt contract and CLI report emission.
2. Verify red.
3. Implement the provider-agnostic transcript-audit prompt and JSONL-to-report CLI.
4. Verify focused and full suites green.

### Task 3: Document client deployment

**Files:**
- Create: `docs/11-call-audit.md`
- Modify: `docs/05-intelligence.md`
- Modify: `templates/intelligence/README.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

Document ingestion adapters, overnight schedule, role routing, privacy/approval boundaries, client packaging, and verification commands. Run all repository tests and a real sample CLI execution. Commit only after proof is green.
