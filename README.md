# boss-orchestrator-init

Deterministic, workspace-local initialization package for boss-orchestrator workflows.

This package provides:
1. **The `boss-orchestrator-init` skill**: Guides the AI agent through preflight, fact discovery, interviewing user preference frontiers, drafting the configuration in memory, and securing explicit confirmation.
2. **Deterministic helper (`scripts/boss_init.py`)**: A pure standard-library Python CLI that validates schema, renders managed files, computes raw byte before/after SHA256 hashes, generates diffs, guards against stale plans and tampering, checks reparse points / symlinks, preserves CRLF / BOM and user prose, and executes atomic binary writes with rollback.
3. **Runtime policy (`references/runtime-policy.md`)**: A self-contained, versioned runtime contract copied into `.setting/boss-orchestrator.md` on initialization.
4. **Unit test suite (`tests/test_boss_init.py`)**: Thorough verification of all safety, boundary, and parsing invariants using Python stdlib `unittest`.

---

## Supported Invariants & Offline Verification

- **Strictly workspace-local**: All writes are bounded to the target workspace root. No global files or parent directories are modified.
- **Offline validation only**: The helper validates supplied evidence structure and ISO dates offline against the schema. It **never** contacts a live catalog, makes network calls, or executes model probes.
- **Safe byte-for-byte preservation**: Updates only the owned block `<!-- boss-orchestrator-init:begin v1 -->` in `AGENTS.md`. Existing text before and after the block, CRLF newlines, UTF-8 BOM, and Matt Pocock `## Agent skills` blocks are preserved byte-for-byte.
- **Config user prose preservation**: Replaces only the fenced `json` code block in `.setting/config.md`, preserving developer notes and custom prose outside the fence.
- **Instruction override protection**: Fails closed if `AGENTS.override.md` is present and non-empty, preventing conflicting or bypassed orchestration instructions.
- **Symlink & reparse point rejection**: Rejects any symlink, junction, or reparse point component between root and managed targets (including within `.setting`).
- **Plan integrity & anti-tampering**: Verifies plan contents against deterministic rendering from the config, rejects duplicate plan paths, and halts on stale plans (before-hash mismatch).
- **Parent sentinel**: `parent.selection: current_active` preserves the user's active parent model without switching or passing sentinels to APIs.
- **Worker routing & equal priority**: All enabled workers have equal initial priority (`boss.priority: equal`). Operational fallback is an unordered allowlist of worker IDs (`boss.fallback_workers`), not a forced sequence.
- **Explicit thinking**: Enabled workers require explicit thinking definitions (`option_key`, `selected`, `allowed_values`) matching the worker's `options`, or `disabled` with a reason. Default thinking is disallowed for enabled workers.

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

### 2. Validate Config
Validates single fenced `json` block, key presence, absence of duplicate or unknown keys, and schema conformance:
```bash
python "<SKILL_DIR>/scripts/boss_init.py" validate --config path/to/config.md --root /path/to/workspace
```
Or validate via stdin:
```bash
cat config.md | python "<SKILL_DIR>/scripts/boss_init.py" validate --config - --root /path/to/workspace
```

### 3. Generate Plan
Renders exact target files (`AGENTS.md`, `.setting/config.md`, `.setting/boss-orchestrator.md`), computes before/after raw SHA256 hashes and unified diffs without modifying files on disk:
```bash
# Print plan JSON directly to stdout
python "<SKILL_DIR>/scripts/boss_init.py" plan --root /path/to/workspace --config path/to/config.md
```
Or accept drafted config via stdin:
```bash
cat config.md | python "<SKILL_DIR>/scripts/boss_init.py" plan --root /path/to/workspace --config -
```

### 4. Apply Plan
Verifies plan integrity, confirms hashes have not drifted, checks `--confirmed` execution flag, and applies writes atomically with rollback:
```bash
python "<SKILL_DIR>/scripts/boss_init.py" apply --root /path/to/workspace --plan plan.json --confirmed
```
Or pipe plan JSON via stdin:
```bash
cat plan.json | python "<SKILL_DIR>/scripts/boss_init.py" apply --root /path/to/workspace --plan - --confirmed
```
*Note: Exit code 0 indicates changes written; exit code 2 indicates workspace was already in the planned state (idempotent, no changes written).*

### 5. Check Status
Inspects workspace binding, config validity, runtime policy existence, and orchestration activation:
```bash
python "<SKILL_DIR>/scripts/boss_init.py" status --root /path/to/workspace
```
*Returns `status: active` (exit 0) when state is `enabled`, `status: inactive` (exit 1) when `state` is `draft` or `disabled`, or `status: invalid` (exit 1) if files or schema are invalid.*

---

## Configuration Schema (`.setting/config.md`)

The configuration file must contain exactly one closed code fence tagged `json`:

```json
{
  "schema_version": 1,
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
      "id": "worker-id",
      "label": "Display Label",
      "enabled": true,
      "disabled_reason": null,
      "provider_instance_id": "instance_id",
      "driver_kind": "driver_name",
      "route_id": "vendor/model-route",
      "options": { "thinking_level": "high" },
      "thinking": {
        "mode": "explicit",
        "option_key": "thinking_level",
        "selected": "high",
        "allowed_values": ["low", "medium", "high"]
      },
      "model_claim": { "name": "Model Name", "provenance": "user_declared" },
      "upstreams": { "mapping": null, "independence": "unknown" },
      "catalog_evidence": { "level": "catalog_verified", "source_ref": "catalog", "observed_at": "YYYY-MM-DD" },
      "execution_evidence": null
    }
  ],
  "boss": {
    "selection": "boss_per_task",
    "review_exception": "small_clear_local_review_fixes",
    "recursive_delegation": "task_explicit_only",
    "builtin_fallback": "excluded",
    "priority": "equal",
    "reliability_memory": "session",
    "parallel_scopes": "disjoint_only",
    "quality_feedback": "first",
    "no_progress_rounds": 2,
    "after_change": "escalate",
    "fallback_workers": ["worker-id"]
  },
  "confirmation": null
}
```

---

## Running Tests

Run the complete stdlib test suite:
```bash
python -m unittest discover -s tests -p "test_*.py"
```
