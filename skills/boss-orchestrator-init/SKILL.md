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
- If `.boss-orchestrator/config.md` or legacy `.setting/config.md` already exists:
  - If `.boss-orchestrator/config.md` exists: report active/inactive status.
  - If legacy `.setting/config.md` exists and `.boss-orchestrator/config.md` does not: report legacy status. Safe path-only migration (`migrate-path`) or v2 migration (`migrate`) is available. Do not silently overwrite v1.
  - If both layouts exist: fail clearly with conflict to prevent ambiguous orchestration.
  - Determine if the user wants an update, path migration, v2 migration, or fresh initialization.

### 2. Conversational Inventory Presentation (Single Turn)

Separate observable facts from user decisions without running sequential interviews or interactive forms:
- **No Grilling or Form Modals:** Do not invoke the `grilling` or `grill-me` skills. Do not use interactive UI forms, modal dialogs, or input tools (`ask_question`, `request_user_input`, `AskUserQuestion`, Plan mode forms). Do not conduct a sequential, multi-turn interview asking questions one by one.
- **Read-Only Inventory Discovery (Observable Facts):** Scan ALL available providers from actual harness discovery without running network probes. Enumerate all active eligible provider instances (`providerInstanceId`, distinguishing active vs disabled, without inferring authorization success or upstream quota independence), along with available models and options. Different named instances (e.g. `antigravity` vs `antigravity_2`) are distinct provider entries. State unknown or unavailable properties explicitly (e.g. unknown upstream mappings, pool weights, or unavailable options). Do not copy the entire model catalog into `workers[]`.
- **Emit ONE Complete Ordinary Chat Response:** Provide a single clear conversational chat message that explains the discovered inventory and details the core operating rules the user's selection will govern:
  1. **One model per provider:** Exactly one enabled worker route per provider instance.
  2. **Explicit thinking options:** Model options and thinking parameters must be explicit (`thinking.option_key`, `thinking.selected`, `thinking.allowed_values`); default/implicit thinking is disallowed for enabled workers.
  3. **First-written priority (`boss.priority: provider_order`):** The order in which the user lists providers directly defines priority (first listed provider = Priority 1 primary dispatch, second = Priority 2, etc.). Redundant fallback arrays are removed.
  4. **Dynamic multi-instance execution:** Static 1-route config does not restrict runtime concurrency; the boss can summon multiple independent task instances on disjoint scopes within harness capacity.
  5. **Queue capacity:** Priority 1 handles all new task dispatches while eligible and capacity is available. If Priority 1 capacity is full, **QUEUE**; do not spill to Priority 2 solely for speed. Queueing is an instruction policy: the top-level orchestrator holds tasks within the conversational turn rather than relying on an automatic background scheduler daemon or service.
  6. **Operational fallback with partial-work handoff:** On auth, quota, connection, or service error, immediately advance to the next eligible priority. Generate a structured handoff brief preserving filesystem partial work (do not restart from scratch by default).
  7. **2 no-progress correction rounds:** Give concrete quality feedback first; 2 consecutive rounds with no measurable progress switches provider; exhausting all providers escalates unaccepted (`boss.after_change: escalate`) without fallback to parent or builtin models.
  8. **Session-only 5 accepted lower-task recovery (`boss.retry_after_successful_tasks: 5`):** After 5 successfully completed and parent-accepted worker tasks on lower-priority provider(s), retry ONE real task on the higher-priority provider. Session reset starts clean at Priority 1.
- **Copyable Ordered Reply Example:** Include a copyable ordered template grounded directly in the discovered provider instance IDs, model route IDs, and explicit option values so the user can easily paste and edit their selection.
- **End Turn:** Stop calling tools and end the turn immediately after emitting the inventory response to await the user's selection in ordinary chat.

### 3. Parse User Selection & Clarify Missing Choices

In the subsequent turn, process the user's ordinary chat reply:
- **Parse Selection & Priority Order:**
  - Extract the ordered list of provider instances, selected model per provider instance, and explicit options/thinking.
  - The first provider in the user's list becomes Priority 1, the second becomes Priority 2, etc.
  - Unselected providers are excluded from active routing; unselected route alternatives remain `enabled: false` with `disabled_reason: "inactive provider route alternative"`.
- **Targeted Ordinary Chat Clarification:**
  - If the user's reply is ambiguous or missing essential choices (e.g. missing an explicit thinking level or model selection for an included provider), ask for clarification via ordinary chat focused strictly on the missing part.
  - Preserve all known and established choices. Do not restart the discovery presentation or re-open settled decisions (e.g. parent sentinel `current_active`, 2-round no-progress escalation, Matt Pocock coexistence).
- **User Selection is NOT Activation Approval:**
  - User selection establishes candidate routes and priority ordering. It does NOT authorize file changes or workspace activation.
  - Candidate execution probes (if authorized/needed) run only after selection as part of the existing authorized flow, with explicit user permission before any probe execution.
  - Strictly NO managed files (`AGENTS.md`, `.boss-orchestrator/config.md`, `.boss-orchestrator/runtime-policy.md`, `.gitignore`) may be written before explicit confirmation in chat.

### 4. Draft in Memory & Generate Exact Diff (Preview)

Prepare the `schema_version: 2` configuration in memory adhering to the schema:
- `parent.selection`: always `current_active` (sentinel, never switch parent model).
- `workers`: exactly one enabled route per provider instance. The order of enabled entries in `workers[]` directly defines provider priority order (first enabled worker = Priority 1).
  - Model options and thinking must be explicit (`thinking.option_key`, `thinking.selected`, `thinking.allowed_values` matching `options`).
  - Catalog and execution evidence must be verified before activation.
- `boss`:
  - `selection`: `boss_per_task`
  - `review_exception`: `small_clear_local_review_fixes`
  - `recursive_delegation`: `task_explicit_only`
  - `builtin_fallback`: `excluded`
  - `priority`: `provider_order` (single source of priority order)
  - `reliability_memory`: `session`
  - `parallel_scopes`: `disjoint_only`
  - `quality_feedback`: `first`
  - `no_progress_rounds`: `2` (user-editable positive integer)
  - `after_change`: `escalate`
  - `retry_after_successful_tasks`: `5` (user-editable positive integer)
  - Redundant `fallback_workers` is removed.
- `confirmation`: requires explicit user confirmation date `approved_at` when activating (`state: enabled`).

Generate the exact plan and diff in memory or to stdout without modifying files on disk by feeding the drafted config to stdin (`--config -`). Stdin input requires exactly one markdown fenced JSON block (tagged `json`):
```bash
# Pipe drafted config (requires exactly one markdown fenced JSON block) to plan helper
python "<SKILL_DIR>/scripts/boss_init.py" plan --root <WORKSPACE_ROOT> --config -
```
**Do not write `.boss-orchestrator/config.md`, `.boss-orchestrator/runtime-policy.md`, or `.gitignore` before obtaining user confirmation.**

Present the summary to the user in ordinary chat:
- Candidate workers (enabled in priority order and disabled alternatives with reasons).
- Ordered routing rules: Priority 1 primary dispatch, capacity queueing without spill, operational advance, 2-round quality escalation, 5-task session-only recovery trial.
- Exact file diffs for `AGENTS.md`, `.boss-orchestrator/config.md`, `.boss-orchestrator/runtime-policy.md`, and `.gitignore`.

### 5. Explicit User Confirmation

Ask the user explicitly in ordinary chat:
> "Do you approve the configuration, priority ordering, routing rules, review exception, and file changes above to initialize boss orchestration in this workspace?"

**A CLI flag (`--confirmed`) is an execution gate, NOT human consent.** Do not proceed to write files without the user's explicit affirmative response in chat.

### 6. Deterministic Plan and Apply

Once confirmed by the user in chat:
1. Generate the plan and pipe directly to apply via stdin (stdin input requires exactly one markdown fenced JSON block):
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
- **Ordered Priority (`boss.priority: provider_order`):** Worker order in `workers[]` determines priority. Dispatch to Priority 1 for all new tasks while eligible and capacity available. If Priority 1 capacity is full, **QUEUE**; do not spill to Priority 2 solely for speed (instruction-governed within turn, no background auto scheduler daemon).
- **Dynamic Multi-Instance Execution:** One static enabled route per provider instance. Boss can summon multiple independent task instances (`taskId` / `clientRequestId` unique) on disjoint scopes within harness capacity.
- **Operational Failures & Handoff:** On auth, quota, connection, or service error, immediately stop dispatching on the affected provider and advance to the next eligible priority. Perform a structured handoff (goal, files/diff, completed/partial steps, test revision evidence, errors, cancellation side effects, next action). Preserve filesystem partial work; do not restart from scratch by default.
- **Quality First & Escalation:** Give concrete feedback first. 2 consecutive correction rounds with no measurable progress (`boss.no_progress_rounds: 2`) switches to the next provider. If all providers are exhausted, escalate unaccepted (`boss.after_change: escalate`). Never fall back to parent or builtin models.
- **Session-Only Recovery (`boss.retry_after_successful_tasks: 5`):** After 5 successfully completed and parent-accepted worker tasks on lower-priority provider(s), the boss may retry ONE real task on the higher-priority provider. Counted once per unique task ID only after parent acceptance. 1 trial at a time. Succeeded trial restores provider; failed trial resets counter to 0. Session reset starts clean at Priority 1.
- **Small Review Fixes:** The parent may fix small clear local review findings itself when required by harness instructions, provided they do not touch design, behavior, dependencies, permissions, or require investigation.
- **Matt Pocock Coexistence:** Preserves existing `## Agent skills` block and other content outside the marker blocks in `AGENTS.md` and user prose in `.boss-orchestrator/config.md`.
- **Startup:** Lightweight check (`boss_init.py status --root .`) at session start. Active only when `state == "enabled"`.
