# Validation and Evidence

## Test Suite Execution
- **Date**: 2026-11-06
- **Runner**: Python standard library `unittest` (`test_boss_init.TestBossInit`)
- **Results**: 20 tests passed, 0 failures, 0 errors (~1.1s execution time)
- **Verified Invariants**:
  - Offline schema validation, required keys, duplicate and unknown key rejection
  - Byte-for-byte preservation of raw CRLF line endings and UTF-8 BOM
  - Coexistence with existing `AGENTS.md` content and Matt Pocock `## Agent skills` blocks
  - User prose preservation outside fenced JSON blocks in `.setting/config.md`
  - Instruction override protection (`AGENTS.override.md` presence rejection)
  - Symlink, NTFS junction, and reparse point rejection
  - Anti-tampering and stale plan detection via raw SHA256 before/after hash checks
  - Simulated disk write failure with atomic rollback to initial state
  - CLI stdin/pipe workflows (`validate`, `plan`, `apply`, `status`)
  - Idempotent apply exit code semantics
- **Harness Handling Clarification**:
  - Offline unsupported config test validates schema handling of `harness.unsupported: "cancel_before_writes"`. This is NOT an actual unsupported harness integration test.

## Helper and End-to-End Workflows
- Deterministic helper (`scripts/boss_init.py`) verified offline in stdlib Python.
- End-to-end stdin piping and CLI parameter workflows execute cleanly without external dependencies or network operations.

## Discovery and Scope Verification
- **Global Skill Discovery**: Verified across both root and global user skill scopes.
- **UI Slash Commands**: NOT verified.
- **Root Workspace Activation**: Preview generated; persistent activation on workspace root is pending explicit user approval.
- **Model Probes**: No network or paid model probes conducted beyond the 4 baseline checks already completed.
