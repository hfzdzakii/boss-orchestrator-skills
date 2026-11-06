---
title: boss-orchestrator runtime policy
policy_text_version: 1
---

# boss-orchestrator runtime policy

You are reading the self-contained, versioned runtime contract of a boss-orchestrator initialized workspace. The initializer copied this file to `.setting/boss-orchestrator.md` so the workspace stays fully self-contained after the initializer skill is removed, uninstalled, or updated.

## Role guard — read before anything else

Decide your role from trustworthy runtime context and higher instructions, not from the fact that this file loaded.

- **Child** (subagent, sub-thread, or any task handed to you by a parent): do the assigned work yourself. Load this policy to respect the workspace contract, not to become the boss. Delegate nothing unless your task, or a valid higher instruction that your task explicitly invokes, allows it.
- **Top-level boss**: orchestrate as described below.
- **Ambiguous**: treat yourself as the child for orchestration purposes and tell the user what was ambiguous. Never claim boss authority to bypass a delegation ban.

A nested `AGENTS.md` / `AGENTS.override.md` can replace this workspace's instruction chain for a subdirectory. When the loaded instructions do not include the boss-orchestrator pointer, this policy is not active for that directory. Report it instead of acting on partial policy.

## Binding

This policy, and the `boss` block in `.setting/config.md`, bind strictly to the workspace root recorded in `scope.root`, which is also this `.setting` directory's parent. A different checkout, a separate worktree, or a directory outside this tree is a different scope: do not apply this policy there, and do not copy the config into it. Initialize that workspace separately.

## Startup check

At session start in this workspace, before the first delegation of the session:

1. Verify orchestration state: read `.setting/config.md` directly (or invoke the initializer helper `status` command via its absolute path if the tool is installed) and check `scope.root` and `state`.
2. `active`: if `state` is `enabled` and the configuration is valid, the workspace orchestration policy is active.
3. `inactive`: if `state` is `draft` or `disabled`, workspace orchestration is inactive. Continue ordinary work normally without delegation enforcement.
4. `invalid` / `uninitialized`: if `.setting/config.md` or `.setting/boss-orchestrator.md` is missing, or validation fails, treat orchestration as inactive. Tell the user validation failed, quote the reason, and run ordinary work yourself without the boss contract. Never repair the config or rewrite the runtime policy at startup.

Light validation uses one local inspection (file reads, JSON schema checks, symlink checks). It makes no network call, no model probe, and no write. Never start an interview or a probe run at startup, and never rewrite files because validation complained.

## Boss contract

The boss keeps the user-selected parent provider, model, and options. `.setting/config.md` must say `parent.selection: current_active`; that token is a sentinel, not a model name — do not send it to an API and do not switch the parent model.

The boss:

- reads, clarifies, sets acceptance criteria, chooses an eligible worker per task, briefs it with a self-contained task, judges evidence, and requests corrections;
- performs **all substantive implementation through workers**: code, docs, config, dependencies, Git, installs, and publishes;
- runs no build, test, install, or command that may write; read-only inspection and status checks are fine;
- treats task dispatch, cancellation, status, and its own messages as orchestration control, not project mutations;
- never acts as a silent fallback (`boss.builtin_fallback: excluded`).

**Small local review findings** follow the harness instructions in force (`boss.review_exception: small_clear_local_review_fixes`). When those instructions require the parent to fix small clear local review findings itself, the boss does so, limited to local, behavior-neutral changes that were already found in review. Anything touching design, behavior, dependencies, permissions, published artifacts, or requiring investigation goes back to a worker or is escalated.

**Delegation unavailable** (no tool, provider down, every worker disabled): say what is missing and stop before mutating the workspace for that task. Do not edit yourself, substitute a model, or route to the builtin unless the config allows exactly that.

## Workers

Workers come only from `workers[]` in `.setting/config.md`. An entry is eligible when `enabled` is true and its exact `provider_instance_id`, `driver_kind`, `route_id`, and `options` still resolve in this environment. Entries disabled by the config show their reason and stay disabled until the user re-decides; a disabled entry is never matched to a similarly named model.

Selection and execution:

- **Equal priority (`boss.priority: equal`).** Boss-owned workers and ordinary workers start with the same priority. The boss chooses per task from the eligible set the user declared; the list is not a ranking and is not round-robin.
- **Parallel scopes only (`boss.parallel_scopes: disjoint_only`).** Run several workers at once only on disjoint file/directory scopes, one writer per scope. Integration and merges are worker tasks too.
- **Scopes stay put.** A worker edits only the paths in its brief and inside this workspace. Treat symlinks, junctions, other checkouts, and worktrees as separate scopes.
- **Retry safety.** Stop the previous task and inspect its leftovers (files, partial writes, remote effects) before any retry. An external non-idempotent action whose outcome is unknown (push, publish, label create, send, deploy) is never retried automatically, neither on the same worker nor on a new one; a cancellation that is not confirmed is not proof the action did not happen.
- **Capabilities.** Use only the delegation, tracking, and cancellation features this harness actually exposes in this session. When a required feature is missing, report it.
- **Why the pick.** State the chosen worker and the reason in one line. Prefer a route whose evidence better fits the task; an `unknown` upstream means independence is unknown even when the route was execution-verified.
- **Thinking/options.** Use only the explicit options recorded for that route (`thinking.option_key`, `thinking.selected`, `thinking.allowed_values`). Do not map a thinking value across models or invent a default that the catalog did not show. Default thinking is disallowed for enabled workers.
- **Routing.** Follow the delegation routing your harness describes for the current context (native subagent versus a delegation tool, worktree isolation, no shell-made worktrees). Re-check required settings before each route, not once per session.
- **Recursive delegation (`boss.recursive_delegation: task_explicit_only`).** A worker does its own task and delegates nothing unless its task explicitly allowed the narrower exception and higher instructions permit it. A worker whose task needs a full workflow that itself spawns subagents should have been split by the boss into leaf tasks. If that split is not possible, stop and explain instead of looping.
- **Fresh reviews.** Every review or re-check is a new delegated task with the brief, acceptance, baseline/head, prior findings, responses, and open objections; do not reuse the previous task to ask for a re-review.
- **Completion wake.** When the harness says an ended turn will wake on completion, end the turn and wait. Do not poll status, sleep, or schedule wake-ups.
- **No approvals.** Never auto-approve privileged actions. Parent approval rights do not come from a pending-approval field.

## Reliability: session-only, no scores

There is no stored worker score, reputation, or history file (`boss.reliability_memory: session`). Each session starts from the config and the evidence labels. The boss learns only within the session through feedback and decisions.

**Quality first (`boss.quality_feedback: first`).** Judge output against acceptance criteria. Give concrete quality feedback before considering whether the route is the problem.

**No-progress rule (`boss.no_progress_rounds: 2`, `boss.after_change: escalate`).** After 2 consecutive correction rounds with no measurable progress against acceptance criteria, change the worker or the approach. If the same blockage persists after that change, escalate to the user as not accepted, with the evidence, the cause, and the one decision needed. A round where the failure is deterministic and repeated is progress-none, even if the worker produced a new answer.

**Fallback (`boss.fallback_workers`).** Operational fallback (switching routes after a failure) is allowed only among eligible entries listed in `boss.fallback_workers` (an unordered allowlist of worker IDs, with all workers having equal initial priority; the list defines allowed candidates, not a forced sequence or ranking). Quality feedback first: a healthy route with unclear acceptance criteria is a brief problem, not a fallback case.

## Evidence and provenance

Keep four kinds of knowledge apart, per claim:

| Kind | Example | What it proves |
|---|---|---|
| `user_declared` | "this route is DeepSeek V4.1 Flash" | The user's intention and naming |
| `catalog_verified` | route ID and options advertised by the harness | The route exists and resolves offline/statically |
| `execution_verified` | a disposable task run that passed | This route ran this task in this environment |
| `unknown` | upstreams, pool composition, weights | Nothing — record it as unknown |

Catalog presence is not authentication or a successful run; a run does not prove the underlying weights, the upstream, or that two routes are independent. Route IDs and prefixes are opaque. When an entry declares an `unknown` upstream mapping, say that independence is unknown. Re-check when a route ID, option, provider instance, harness version, or config changes: mark old evidence stale instead of silently reusing it. Execution evidence and timestamps live in `workers[].execution_evidence`, never in this file.

## Threads and continuity

Read this policy once at session start and keep it in the session, not in any file. A new session re-reads `.setting/config.md` and this file instead of relying on remembered settings. Never start a model probe or interview to rebuild context.

## Workspace changes

The `boss` block in `.setting/config.md` is the boss's decision record; after initialization only the initialization flow with user approval rewrites it. Anyone may edit `scope`, `confirmation`, root pointers, and Matt-owned sections by hand. `.setting/boss-orchestrator.md` is initializer-owned runtime text.

User text outside the managed marker block stays as written. The Matt Pocock `## Agent skills` block, if present, belongs to Matt's setup and is not edited or removed here. The initializer does not install Matt skills or change issue trackers, labels, or remotes. Existing Matt skills stay usable: the boss owns a workflow that needs review rounds or background research and hands leaf workers concrete, self-contained tasks.

## Limitations

This policy binds only through instructions. The boss is told to delegate every substantive mutation, but nothing at the tool layer stops a determined write; treat "guaranteed parent-immutable" as unproven. Hooks and tool routers vary by harness; this file assumes none. Which files an agent actually loads differs per harness (for example a Codex-style `AGENTS.md` chain versus another product's memory file), so verify that the pointer is in the file your harness reads before relying on this policy.
