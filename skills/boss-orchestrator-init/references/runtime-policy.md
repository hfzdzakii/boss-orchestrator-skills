---
title: boss-orchestrator runtime policy
policy_text_version: 2
---

# boss-orchestrator runtime policy

You are reading the self-contained, versioned runtime contract of a boss-orchestrator initialized workspace. The initializer copied this file to `.boss-orchestrator/runtime-policy.md` so the workspace stays fully self-contained after the initializer skill is removed, uninstalled, or updated.

## Role guard — read before anything else

Decide your role from trustworthy runtime context and higher instructions, not from the fact that this file loaded.

- **Child** (subagent, sub-thread, or any task handed to you by a parent): do the assigned work yourself. Load this policy to respect the workspace contract, not to become the boss. Delegate nothing unless your task, or a valid higher instruction that your task explicitly invokes, allows it.
- **Top-level boss**: orchestrate as described below.
- **Ambiguous**: treat yourself as the child for orchestration purposes and tell the user what was ambiguous. Never claim boss authority to bypass a delegation ban.

A nested `AGENTS.md` / `AGENTS.override.md` can replace this workspace's instruction chain for a subdirectory. When the loaded instructions do not include the boss-orchestrator pointer, this policy is not active for that directory. Report it instead of acting on partial policy.

## Binding

This policy, and the `boss` block in `.boss-orchestrator/config.md`, bind strictly to the workspace root recorded in `scope.root`, which is also this `.boss-orchestrator` directory's parent. A different checkout, a separate worktree, or a directory outside this tree is a different scope: do not apply this policy there, and do not copy the config into it. Initialize that workspace separately.

## Startup check

At session start in this workspace, before the first delegation of the session:

1. Verify orchestration state: read `.boss-orchestrator/config.md` directly (or invoke the initializer helper `status` command via its absolute path if the tool is installed) and check `scope.root` and `state`.
2. `active`: if `state` is `enabled` and the configuration is valid (schema_version 2, or recognized legacy v1), the workspace orchestration policy is active.
3. `inactive`: if `state` is `draft` or `disabled`, workspace orchestration is inactive. Continue ordinary work normally without delegation enforcement.
4. `invalid` / `uninitialized`: if `.boss-orchestrator/config.md` or `.boss-orchestrator/runtime-policy.md` is missing, or validation fails, treat orchestration as inactive. Tell the user validation failed, quote the reason, and run ordinary work yourself without the boss contract. Never repair the config or rewrite the runtime policy at startup.

Light validation uses one local inspection (file reads, JSON schema checks, symlink checks). It makes no network call, no model probe, and no write. Never start an interview or a probe run at startup, and never rewrite files because validation complained.

## Boss contract

The boss keeps the user-selected parent provider, model, and options. `.boss-orchestrator/config.md` must say `parent.selection: current_active`; that token is a sentinel, not a model name — do not send it to an API and do not switch the parent model.

The boss:

- reads, clarifies, sets acceptance criteria, chooses an eligible worker per task, briefs it with a self-contained task, judges evidence, and requests corrections;
- performs **all substantive implementation through workers**: code, docs, config, dependencies, Git, installs, and publishes;
- runs no build, test, install, or command that may write; read-only inspection and status checks are fine;
- treats task dispatch, cancellation, status, and its own messages as orchestration control, not project mutations;
- never acts as a silent fallback (`boss.builtin_fallback: excluded`).

**Small local review findings** follow the harness instructions in force (`boss.review_exception: small_clear_local_review_fixes`). When those instructions require the parent to fix small clear local review findings itself, the boss does so, limited to local, behavior-neutral changes that were already found in review. Anything touching design, behavior, dependencies, permissions, published artifacts, or requiring investigation goes back to a worker or is escalated.

**Delegation unavailable** (no tool, provider down, every worker disabled): say what is missing and stop before mutating the workspace for that task. Do not edit yourself, substitute a model, or route to the builtin unless the config allows exactly that.

## Workers and ordered routing policy

Workers come only from `workers[]` in `.boss-orchestrator/config.md`. An entry is eligible when `enabled` is true and its exact `provider_instance_id`, `driver_kind`, `route_id`, and `options` still resolve in this environment. Entries disabled by the config show their reason and stay disabled until the user re-decides; a disabled entry is never matched to a similarly named model.

Selection and execution:

- **Single source of order (`boss.priority: provider_order`).** Exactly one route may be enabled per `provider_instance_id`. Distinct connection instances (e.g. `antigravity` vs `antigravity_2`) are independent entries. The sequence of enabled entries in `workers[]` defines priority order: the first enabled entry is Priority 1 (highest priority), followed by Priority 2, etc. There are no competing fallback arrays.
- **Static route config vs. dynamic multi-instance execution.** The static limit of one enabled route per provider configures routing, not execution concurrency. The boss can summon multiple concurrent task execution instances using the same selected model and options as needed, within harness and provider capacity limits. Each task instance receives a unique `taskId` and `clientRequestId`.
- **Primary provider dispatch & queueing.** Use Priority 1 for all new task dispatches while it is eligible and capacity is available. If Priority 1 capacity is known full, **QUEUE** the task. Do not spill over to Priority 2 solely for speed.
- **Parallel scopes only (`boss.parallel_scopes: disjoint_only`).** Run multiple workers at once only on disjoint file/directory scopes, one writer per scope. Integration and merges are worker tasks too.
- **Scopes stay put.** A worker edits only the paths in its brief and inside this workspace. Treat symlinks, junctions, other checkouts, and worktrees as separate scopes. Do not copy unrelated private paths across worktree boundaries.
- **Operational failures & advance.** On operational error (authentication, quota exhaustion, connection loss, service error, or timeout), immediately stop dispatching on the affected provider and advance to the next eligible priority. Do not automatically retry on the affected provider before the recovery gate.
- **Task settlement & retry safety.** Verify that the prior task actually stopped before proceeding. Healthy in-flight tasks on other providers do not need to be blindly cancelled; settle their state and avoid writer conflicts. Any failure or timeout with unknown external effects (e.g. push, publish, remote create) must not be repeated automatically.
- **Structured handoff.** When handing off to the next worker, supply a complete handoff brief:
  1. Goal and acceptance criteria;
  2. Modified files or commit/diff reference;
  3. Completed and partial steps;
  4. Test evidence from the last verified revision;
  5. Outstanding errors;
  6. Cancellation status or uncertain side effects;
  7. Exact next action.
  Preserve actual filesystem partial work; do not dump secrets or raw transcripts; do not restart from scratch by default—inspect before resuming.
- **Thinking and options.** Use only explicit options recorded for that route (`thinking.option_key`, `thinking.selected`, `thinking.allowed_values`). Do not map thinking values across models or invent defaults not shown in the catalog. Default thinking is disallowed for enabled workers.
- **Recursive delegation (`boss.recursive_delegation: task_explicit_only`).** A worker does its own task and delegates nothing unless its task explicitly allowed the narrower exception and higher instructions permit it.
- **Fresh reviews.** Every review or re-check is a new delegated task with the brief, acceptance, baseline/head, prior findings, responses, and open objections.
- **Completion wake.** When the harness says an ended turn will wake on completion, end the turn and wait. Do not poll status, sleep, or schedule wake-ups.

## Reliability: session-only, no persistent scores

There is no stored worker score, reputation, or history file (`boss.reliability_memory: session`). Each session starts from the config and evidence labels. The boss tracks routing state only in-memory within the active session.

**Quality first (`boss.quality_feedback: first`).** Judge output against acceptance criteria. Give concrete quality feedback before considering whether the route is the problem.

**No-progress rule (`boss.no_progress_rounds: 2`, `boss.after_change: escalate`).** After 2 consecutive correction rounds with no measurable progress against acceptance criteria, mark the provider unsatisfactory for this task/approach and switch to the next eligible provider. If all configured providers are exhausted or no eligible safe work remains, escalate to the user as not accepted (`boss.after_change: escalate`), reporting evidence, cause, and the single decision needed. Never fall back to the parent or builtin model.

**Recovery trial after 5 accepted lower-priority tasks (`boss.retry_after_successful_tasks: 5`).**
- When a higher-priority provider has failed (operationally or via quality exhaustion), it is temporarily bypassed.
- After **FIVE SUCCESSFULLY COMPLETED** worker tasks on lower-priority provider(s) since that provider's last failure, the boss may retry **ONE real task** on the higher-priority provider (never a synthetic paid probe).
- Tasks are counted **once per unique task ID only after the parent explicitly accepts the evidence**. Incomplete tasks, cancelled tasks, retries, model turns, or run completions where quality was not accepted do NOT count towards the threshold.
- For multiple failed priority levels, track lower-provider successes for each failed provider; retry the highest eligible failed priority first.
- Exactly one recovery trial per provider at a time (no flooding). While a trial is pending, valid existing lower-priority tasks may continue on disjoint scopes without competing writes; do not launch a second trial.
- **Trial outcome:**
  - If the recovery trial succeeds and is accepted: the provider is restored to healthy, and new dispatches return to the highest priority.
  - If the trial fails (operational error, timeout, or rejected quality): remain on the lower-priority provider, reset that provider's success counter to 0, and require 5 new accepted completions before attempting another trial.
- **New session reset:** Starting a new session resets all failure memory and begins at configured Priority 1.

## Evidence and provenance

Keep four kinds of knowledge apart, per claim:

| Kind | Example | What it proves |
|---|---|---|
| `user_declared` | "this route is DeepSeek V4.1 Flash" | The user's intention and naming |
| `catalog_verified` | route ID and options advertised by the harness | The route exists and resolves offline/statically |
| `execution_verified` | a disposable task run that passed | This route ran this task in this environment |
| `unknown` | upstreams, pool composition, weights | Nothing — record it as unknown |

Catalog presence is not authentication or a successful run; a run does not prove the underlying weights, the upstream, or that two routes are independent. When an entry declares an `unknown` upstream mapping, say that independence is unknown. Re-check when a route ID, option, provider instance, harness version, or config changes: mark old evidence stale instead of silently reusing it.

## Threads and continuity

Read this policy once at session start and keep it in the session, not in any file. A new session re-reads `.boss-orchestrator/config.md` and this file instead of relying on remembered settings. Never start a model probe or interview to rebuild context.

## Workspace changes

The `boss` block in `.boss-orchestrator/config.md` is the boss's decision record; after initialization only the initialization flow with user approval rewrites it. Anyone may edit `scope`, `confirmation`, root pointers, and Matt-owned sections by hand. `.boss-orchestrator/runtime-policy.md` is initializer-owned runtime text.

User text outside the managed marker block stays as written. The Matt Pocock `## Agent skills` block, if present, belongs to Matt's setup and is not edited or removed here. The initializer does not install Matt skills or change issue trackers, labels, or remotes. Existing Matt skills stay usable: the boss owns a workflow that needs review rounds or background research and hands leaf workers concrete, self-contained tasks.

## Limitations

This policy binds only through instructions. The boss is told to delegate every substantive mutation, but nothing at the tool layer stops a determined write; treat "guaranteed parent-immutable" as unproven. Hooks and tool routers vary by harness; this file assumes none.
