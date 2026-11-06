# Validation and Evidence

## Test Suite Execution
- **Date**: 2026-11-06
- **Runner**: Python standard library `unittest` (`test_boss_init.TestBossInit`)
- **Results**: 41 tests passed, 0 failures, 0 errors (~1.3s execution time)
- **Verified Invariants**:
  - **Legacy Schema Version 1 Backward Compatibility**:
    - Validates v1 equal-priority configs without errors (including existing root config with multiple opencode routes enabled).
    - Status check reports `active` legacy state without marking workspace invalid or mutating disk.
    - Plan rejects v1 configs without auto-conversion and requires migration to v2.
    - Migration command (`migrate`) detects multi-route conflicts, rejects duplicate order lists, validates emitted draft, and produces clean v2 draft upon user selection without modifying disk.
  - **Schema Version 2 Ordered Priority Policy**:
    - Enforces exactly one enabled worker route per `provider_instance_id`; rejects multiple enabled routes on the same provider instance.
    - Allows multiple distinct named provider instances (e.g. `antigravity` vs `antigravity_2`).
    - Permits disabled alternatives for the same provider instance with `disabled_reason`.
    - Validates `boss.priority: "provider_order"`; rejects `"equal"`.
    - Strict `schema_version` type int requirement (rejects bool, float, str at all entry points: validate, plan, apply, status, migrate).
    - Rejects booleans (`True`/`False`) or non-positive integers for numeric fields (`retry_after_successful_tasks`, `no_progress_rounds`).
    - Treats `fallback_workers` in v2 as redundant: valid when omitted, and if present must strictly match enabled worker order.
  - **Deterministic Pure SessionRouter State Machine (Verification / Reference Module)**:
    - Pure reference module: live routing instruction-governed by orchestrator without harness middleware.
    - Single source of order: enabled worker list order strictly determines priority. Priority 1 is selected for primary dispatches.
    - Capacity queueing: when Priority 1 capacity is full, action is `queue`, avoiding spilling to lower priority solely for speed.
    - Operational error advance: operational error (auth, quota, timeout, connection) immediately stops dispatching on affected provider and advances to the next eligible priority.
    - In-flight identity & terminal registry: requires valid dispatched in-flight identity on completion, prevents all replay and unknown task completions, rejects worker mismatch before mutation.
    - Strict handoff contract: validates all fields and types in `HandoffBrief` including `cancellation_uncertain_effects` and list element types.
    - Per-task quality rounds: quality rounds keyed per task with validated worker/task identity; 2 consecutive correction rounds with no progress switches provider; exhausting all providers escalates unaccepted without fallback to parent or builtin.
    - Single global recovery trial: exactly one recovery trial may be pending or in-flight across the entire router; no concurrent trials permitted.
    - Quality exhaustion on recovery: settles/clears recovery trial and resets counter to 0.
    - Task counting and recovery trial:
      - Tasks counted once per unique task ID only upon explicit parent acceptance of evidence.
      - 5 accepted completions on lower-priority providers triggers a single real recovery trial on the higher-priority provider.
      - Flooding prevented: only one global pending recovery trial allowed.
      - Failed recovery trial resets counter to 0 (5 new accepted tasks required).
      - Succeeded and accepted trial restores provider to healthy, returning new dispatches to Priority 1.
      - Multi-level failure ordering: highest eligible failed priority is retried first.
      - Session reset: resets in-memory failure state clean to Priority 1 with zero persistent state across sessions.
  - **Atomic Plan, Apply, Rollback & Tamper Protection**:
    - Raw byte before/after SHA256 verification and detection of tampered plan content.
    - Stale plan detection upon file drift.
    - Atomic file write with simulated failure rollback.
    - Symlink, NTFS junction, and reparse point rejection.
    - Instruction override protection (`AGENTS.override.md` presence rejection).
    - Byte-for-byte preservation of raw CRLF line endings, UTF-8 BOM, and Matt Pocock `## Agent skills` blocks.
    - Developer prose preservation outside fenced JSON blocks in `.setting/config.md`.

## Helper and Migration Workflows
- Deterministic helper (`scripts/boss_init.py`) verified offline in standard-library Python.
- Migration command (`migrate`) verified on root workspace:
  - Without flags: detects `opencode` conflict between `hafizh` and `rizpedia`, requesting user decision.
  - With `--select-route opencode=hazhtsu/deepseek-hafizh --order lason,nia,hafizh`: outputs valid `schema_version: 2` config draft with zero changes to files on disk.

## Discovery and Scope Verification
- **Root Workspace State**: Preserved untouched on disk. Currently active under legacy `schema_version: 1` (`lason`, `nia`, `hafizh`, `rizpedia`). No unapproved root changes, commits, or npm publishes made.
- **Model Probes**: No network or paid model probes conducted.
