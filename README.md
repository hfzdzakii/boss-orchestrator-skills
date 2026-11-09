# boss-orchestrator-init

Deterministic, workspace-local initialization package for boss-orchestrator workflows.

This package provides:
1. **The `boss-orchestrator-init` skill**: Guides the AI agent through preflight, read-only harness and provider discovery, presenting inventory and routing principles in a single conversational turn, parsing user ordering and model choices in ordinary chat, drafting the configuration in memory, and securing explicit confirmation under the ordered-provider policy.
2. **Deterministic helper (`scripts/boss_init.py`)**: A pure standard-library Python CLI that validates schema (v1 legacy and v2 ordered policy), renders managed files, computes raw byte before/after SHA256 hashes, generates diffs, guards against stale plans and tampering, checks reparse points / symlinks, preserves CRLF / BOM and user prose, executes atomic binary writes with rollback, drafts migrations from v1, and provides a pure deterministic session routing verification and reference state machine (`SessionRouter`). Note that live routing during task execution is instruction-governed by the top-level orchestrator agent without runtime harness middleware or hooks.
3. **Runtime policy (`references/runtime-policy.md`)**: A self-contained, versioned runtime contract (v2) copied into `.setting/boss-orchestrator.md` on initialization.
4. **Unit test suite (`tests/test_boss_init.py`)**: Thorough verification of safety, boundaries, parsing, migration, and the deterministic session routing state machine using Python stdlib `unittest`.

---

## Supported Invariants & Offline Verification

- **Strictly workspace-local**: All writes are bounded to the target workspace root. No global files or parent directories are modified.
- **Offline validation only**: The helper validates supplied evidence structure and ISO dates offline against the schema. It **never** contacts a live catalog, makes network calls, or executes model probes.
- **Ordered-provider policy (`boss.priority: provider_order`)**:
  - Exactly one enabled route per provider instance (`provider_instance_id`). Distinct connection instances (e.g. `antigravity` vs `antigravity_2`) are independent entries.
  - The order of enabled entries in `workers[]` defines provider priority (first written = Priority 1). Redundant competing fallback arrays are removed.
- **Dynamic multi-instance concurrent dispatch**: Static configuration of 1 worker route per provider does not limit runtime concurrency. The boss can summon multiple independent task instances (`taskId` and `clientRequestId` unique) on disjoint scopes within actual harness capacity.
- **Primary dispatch and capacity queueing**: Use Priority 1 for all new dispatches while eligible and capacity is available. If Priority 1 capacity is known full, **QUEUE** the task; do not spill to Priority 2 solely for speed.
- **Operational error advance & structured handoff**: On authentication, quota, connection, or service error, immediately stop dispatching on the affected provider and advance to the next eligible priority. Perform a complete handoff (goal, files/diff, completed/partial steps, test revision evidence, errors, cancellation side effects, next action). Preserve filesystem partial work; do not restart from scratch by default.
- **Quality first & 2-round escalation**: Quality feedback first. 2 consecutive correction rounds with no measurable progress (`boss.no_progress_rounds: 2`) switches to the next eligible provider. If all providers are exhausted, escalate unaccepted without falling back to parent or builtin models.
- **Session-only 5-task recovery trial (`boss.retry_after_successful_tasks: 5`)**:
  - After 5 successfully completed and parent-accepted worker tasks on lower-priority provider(s), the boss may retry ONE real task on the higher-priority provider.
  - Counted once per unique task ID only upon parent acceptance. 1 trial at a time. Succeeded trial restores provider; failed trial resets counter to 0. Session reset starts clean at Priority 1.
- **Legacy v1 backward compatibility**:
  - `status` and `validate` recognize existing `schema_version: 1` configs as legacy active without marking them invalid or altering disk.
  - `migrate` command detects conflicts (such as multiple enabled routes under one provider) and drafts a valid `schema_version: 2` config once user decisions are supplied.
  - New `plan` and `apply` emit `schema_version: 2` and reject arbitrary auto-conversion.
- **Safe byte-for-byte preservation**: Updates only the owned block `<!-- boss-orchestrator-init:begin v1 -->` in `AGENTS.md`. Existing text before and after the block, CRLF newlines, UTF-8 BOM, and Matt Pocock `## Agent skills` blocks are preserved byte-for-byte.
- **Config user prose preservation**: Replaces only the fenced `json` code block in `.setting/config.md`, preserving developer notes and custom prose outside the fence.
- **Instruction override protection**: Fails closed if `AGENTS.override.md` is present and non-empty.
- **Plan integrity & anti-tampering**: Verifies plan contents against deterministic rendering from the config, rejects duplicate plan paths, and halts on stale plans (before-hash mismatch).

---

## Installation

No custom npm package is required. Install locally into the user skill store via the skills CLI:

```bash
# Install from local repository to global skill store
npx skills add . --skill boss-orchestrator-init -g -a codex --copy
```

---

## CLI Helper Usage (`scripts/boss_init.py`)

The helper uses only Python standard library modules (`argparse`, `difflib`, `hashlib`, `json`, `pathlib`, `os`, `sys`).

Always invoke the helper using its absolute path `<SKILL_DIR>/scripts/boss_init.py` (resolved from the skill's install location), specifying `--root <WORKSPACE_ROOT>`.

### 1. View Help
```bash
python "<SKILL_DIR>/scripts/boss_init.py" --help
```

### 2. Check Status
Inspects workspace binding, config validity, runtime policy existence, and orchestration activation:
```bash
python "<SKILL_DIR>/scripts/boss_init.py" status --root /path/to/workspace
```
*Returns `status: active` (exit 0) when state is `enabled` (including legacy v1 with notice), `status: inactive` (exit 1) when `state` is `draft` or `disabled`, or `status: invalid` (exit 1) if files or schema are invalid.*

### 3. Validate Config
Validates single fenced `json` block, key presence, absence of duplicate or unknown keys, and schema conformance (v1 or v2):
```bash
python "<SKILL_DIR>/scripts/boss_init.py" validate --config path/to/config.md --root /path/to/workspace
```
Or validate via stdin (input must contain exactly one markdown fenced JSON block):
```bash
cat config.md | python "<SKILL_DIR>/scripts/boss_init.py" validate --config - --root /path/to/workspace
```

### 4. Migrate Legacy v1 Config
Detects unresolved multi-route conflicts in legacy v1 configs and drafts a v2 configuration upon user specification without writing to disk:
```bash
# Check unresolved provider conflicts
python "<SKILL_DIR>/scripts/boss_init.py" migrate --root /path/to/workspace

# Draft v2 config with selected route and priority order
python "<SKILL_DIR>/scripts/boss_init.py" migrate --root /path/to/workspace \
  --select-route opencode=hazhtsu/deepseek-hafizh \
  --order lason,nia,hafizh
```

### 5. Generate Plan (Emits Schema Version 2)
Renders exact target files (`AGENTS.md`, `.setting/config.md`, `.setting/boss-orchestrator.md`), computes before/after raw SHA256 hashes and unified diffs without modifying files on disk:
```bash
# Print plan JSON directly to stdout
python "<SKILL_DIR>/scripts/boss_init.py" plan --root /path/to/workspace --config path/to/config.md
```
Or accept drafted config via stdin (input must contain exactly one markdown fenced JSON block):
```bash
cat config.md | python "<SKILL_DIR>/scripts/boss_init.py" plan --root /path/to/workspace --config -
```

### 6. Apply Plan
Verifies plan integrity, confirms hashes have not drifted, checks `--confirmed` execution flag, and applies writes atomically with rollback:
```bash
python "<SKILL_DIR>/scripts/boss_init.py" apply --root /path/to/workspace --plan plan.json --confirmed
```
Or pipe plan JSON via stdin:
```bash
cat plan.json | python "<SKILL_DIR>/scripts/boss_init.py" apply --root /path/to/workspace --plan - --confirmed
```
*Note: Exit code 0 indicates changes written; exit code 2 indicates workspace was already in the planned state (idempotent, no changes written).*

---

## Configuration Schema (`.setting/config.md` - Schema Version 2)

The configuration file must contain exactly one closed code fence tagged `json`:

```json
{
  "schema_version": 2,
  "state": "draft",
  "scope": {
    "kind": "workspace",
    "root": "/absolute/path/to/workspace",
    "git": false
  },
  "harness": {
    "allowlist": ["t3"],
    "unsupported": "cancel_before_writes"
  },
  "parent": {
    "selection": "current_active"
  },
  "workers": [
    {
      "id": "worker-1",
      "label": "Worker 1 (Priority 1)",
      "enabled": true,
      "disabled_reason": null,
      "provider_instance_id": "provider_inst_1",
      "driver_kind": "driver_name",
      "route_id": "vendor/model-route-1",
      "options": { "thinking_level": "high" },
      "thinking": {
        "mode": "explicit",
        "option_key": "thinking_level",
        "selected": "high",
        "allowed_values": ["low", "medium", "high"]
      },
      "model_claim": { "name": "Model Name 1", "provenance": "user_declared" },
      "upstreams": { "mapping": null, "independence": "unknown" },
      "catalog_evidence": { "level": "catalog_verified", "source_ref": "catalog", "observed_at": "2026-11-06" },
      "execution_evidence": null
    },
    {
      "id": "worker-2",
      "label": "Worker 2 (Priority 2)",
      "enabled": true,
      "disabled_reason": null,
      "provider_instance_id": "provider_inst_2",
      "driver_kind": "driver_name",
      "route_id": "vendor/model-route-2",
      "options": { "thinking_level": "high" },
      "thinking": {
        "mode": "explicit",
        "option_key": "thinking_level",
        "selected": "high",
        "allowed_values": ["low", "medium", "high"]
      },
      "model_claim": { "name": "Model Name 2", "provenance": "user_declared" },
      "upstreams": { "mapping": null, "independence": "unknown" },
      "catalog_evidence": { "level": "catalog_verified", "source_ref": "catalog", "observed_at": "2026-11-06" },
      "execution_evidence": null
    },
    {
      "id": "worker-1-alt",
      "label": "Inactive Alternative Route",
      "enabled": false,
      "disabled_reason": "inactive provider route alternative",
      "provider_instance_id": "provider_inst_1",
      "driver_kind": "driver_name",
      "route_id": "vendor/model-route-alt",
      "options": null,
      "thinking": { "mode": "disabled", "reason": "unselected route alternative" },
      "model_claim": { "name": "Model Alt", "provenance": "user_declared" },
      "upstreams": { "mapping": null, "independence": "unknown" },
      "catalog_evidence": null,
      "execution_evidence": null
    }
  ],
  "boss": {
    "selection": "boss_per_task",
    "review_exception": "small_clear_local_review_fixes",
    "recursive_delegation": "task_explicit_only",
    "builtin_fallback": "excluded",
    "priority": "provider_order",
    "reliability_memory": "session",
    "parallel_scopes": "disjoint_only",
    "quality_feedback": "first",
    "no_progress_rounds": 2,
    "after_change": "escalate",
    "retry_after_successful_tasks": 5
  },
  "confirmation": null
}
```

*(Note: Sample dates such as `"2026-11-06"` in illustrative configuration snippets are valid ISO-8601 dates for schema demonstration, explicitly not live evidence.)*

---

## Running Tests

Run the complete stdlib test suite:
```bash
python -m unittest discover -s tests -p "test_*.py"
```
