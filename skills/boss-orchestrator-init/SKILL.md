---
name: boss-orchestrator-init
description: Initialize workspace-local boss-orchestrator policy, worker routing, and execution gates with explicit user confirmation.
---

# boss-orchestrator-init

Initialize a workspace for boss orchestration. This skill configures the top-level parent session to act as an orchestrator ("boss") that delegates substantive implementation to worker subagents, while keeping the parent's current active model and allowing small clear local review fixes.

This initialization is strictly workspace-local: it never modifies global configs, never installs dependencies globally, never probes network models without explicit permission, and never writes persistent changes without user confirmation.

## Resolving Helper Path

The helper script `boss_init.py` lives inside this skill's installation directory (`<SKILL_DIR>/scripts/boss_init.py`). When this skill is globally or locally installed and the agent's current working directory is the target workspace, relative commands like `python scripts/boss_init.py` will fail because `scripts/` does not exist in the target workspace root.

**Always resolve `<SKILL_DIR>` from this skill's definition / invocation metadata** and invoke the absolute helper path:
```bash
python "<SKILL_DIR>/scripts/boss_init.py" <command> --root <WORKSPACE_ROOT>
```

## Workflow

### 1. Preflight and Harness Discovery (Read-Only)

First, observe harness capabilities and target workspace:
- Verify that delegation and cancellation are supported by the active harness. If the harness is known to be unsupported, cancel before writing any files.
- Resolve the target workspace root to an absolute path. Verify it exists, is a real directory, and is NOT a symlink, junction, or reparse point.
- Check if `AGENTS.override.md` exists and is non-empty. Boss-orchestrator currently supports only `AGENTS.md`; fail closed before persistent writes if `AGENTS.override.md` is present and non-empty.
- Check current status using the helper:
  ```bash
  python "<SKILL_DIR>/scripts/boss_init.py" status --root <WORKSPACE_ROOT>
  ```
- If `.setting/config.md` already exists, inspect whether the workspace is active or inactive, and determine if the user wants an update or fresh initialization.

### 2. Fact Observation vs. User Decisions

Separate observable facts from user preferences:
- **Facts (Agent observes):** Inspect available providers, models, driver kinds, and advertised options through harness discovery. Do not ask the user for observable IDs.
- **Decisions (User decides):** Ask the user only about unresolved preferences on the decision frontier (e.g., candidate pool priority, thinking level overrides, probe execution authorization) with recommended answers, then wait for response.
- Do not re-interview settled decisions (e.g. parent sentinel `current_active`, equal initial priority, 2-round no-progress escalation, Matt Pocock coexistence).
- No mandatory third-party grilling skills are required.

### 3. Draft in Memory & Generate Exact Diff

Prepare the configuration in memory adhering to the schema:
- `parent.selection`: always `current_active` (sentinel, never switch parent model).
- `workers`: all declared routes. Enabled workers must have catalog evidence and execution evidence (if activating). Unresolved routes must remain `enabled: false` with a clear `disabled_reason`.
  - For enabled workers, `thinking` must be explicit: specifying `option_key`, `selected`, and `allowed_values` (which must match `options`), or `disabled` with a reason. Default thinking is disallowed for enabled workers.
- `boss`:
  - `selection`: `boss_per_task`
  - `review_exception`: `small_clear_local_review_fixes`
  - `recursive_delegation`: `task_explicit_only`
  - `builtin_fallback`: `excluded`
  - `priority`: `equal`
  - `reliability_memory`: `session`
  - `parallel_scopes`: `disjoint_only`
  - `quality_feedback`: `first`
  - `no_progress_rounds`: `2`
  - `after_change`: `escalate`
  - `fallback_workers`: unordered allowlist of enabled worker IDs
- `confirmation`: requires explicit user confirmation date `approved_at` when activating (`state: enabled`).

Generate the exact plan and diff in memory or to stdout without modifying files on disk by feeding the drafted config to stdin (`--config -`):
```bash
# Pipe drafted config JSON block to plan helper
python "<SKILL_DIR>/scripts/boss_init.py" plan --root <WORKSPACE_ROOT> --config -
```
**Do not write `.setting/config.md` or `.setting/plan.json` before obtaining user confirmation.**

Present the summary to the user:
- Candidate workers (enabled and disabled with reasons).
- Routing rules, operational fallback allowlist, loop/retry rules.
- Exact file diffs for `AGENTS.md`, `.setting/config.md`, and `.setting/boss-orchestrator.md`.

### 4. Explicit User Confirmation

Ask the user explicitly:
> "Do you approve the configuration, routing rules, review exception, and file changes above to initialize boss orchestration in this workspace?"

**A CLI flag (`--confirmed`) is an execution gate, NOT human consent.** Do not proceed to write files without the user's explicit affirmative response in chat.

### 5. Deterministic Plan and Apply

Once confirmed by the user in chat:
1. Generate the plan and pipe directly to apply via stdin (or write a temporary plan file outside managed paths):
   ```bash
   python "<SKILL_DIR>/scripts/boss_init.py" plan --root <WORKSPACE_ROOT> --config - | python "<SKILL_DIR>/scripts/boss_init.py" apply --root <WORKSPACE_ROOT> --plan - --confirmed
   ```
2. Verify workspace status:
   ```bash
   python "<SKILL_DIR>/scripts/boss_init.py" status --root <WORKSPACE_ROOT>
   ```

## Runtime Invariants

Once initialized, top-level parent sessions in this workspace operate under these rules:
- **Parent Role:** Keeps current model (`current_active`). Delegates all substantive tasks (coding, docs, tests, Git commands, builds).
- **Small Review Fixes:** The parent may fix small clear local review findings itself when required by harness instructions, provided they do not touch design, behavior, dependencies, permissions, or require investigation.
- **Worker Execution:** Workers are leaves. No recursive delegation unless the assigned task explicitly permits it.
- **Session Reliability:** Equal initial priority across workers (`boss.priority: equal`). No persistent scores (`boss.reliability_memory: session`). Quality feedback first (`boss.quality_feedback: first`). After 2 rounds with no measurable progress (`boss.no_progress_rounds: 2`), change worker or approach; if the blockage persists, escalate (`boss.after_change: escalate`).
- **Matt Pocock Coexistence:** Preserves any existing `## Agent skills` block and other content outside the marker blocks in `AGENTS.md` and user prose in `.setting/config.md`. No automatic installation of Matt tools or tracker modification.
- **Startup:** Lightweight check (`boss_init.py status --root .` or direct file inspection) at session start. No automated network probes, re-interviews, or file rewrites. Active only when `state == "enabled"`.
