#!/usr/bin/env python3
"""Deterministic stdlib helper for boss-orchestrator-init skill.

Supports schema_version 1 (legacy equal-priority) and schema_version 2 (ordered-provider policy).
Includes pure session routing verification and reference state machine for runtime dispatch and recovery.
Live routing during task execution is instruction-governed by the top-level orchestrator agent
without runtime harness middleware or hooks.
"""
from __future__ import annotations
import argparse, difflib, hashlib, json, os, re, sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

TOOL_VERSION = "2"
SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (1, 2)
MARKER_BEGIN = "<!-- boss-orchestrator-init:begin v1 -->"
MARKER_END = "<!-- boss-orchestrator-init:end v1 -->"
MANAGED_FILES = ("AGENTS.md", ".setting/config.md", ".setting/boss-orchestrator.md")
ID_RE, DATE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$"), re.compile(r"^\d{4}-\d{2}-\d{2}$")
FILE_ATTRIBUTE_REPARSE_POINT = 0x400

AGENTS_BLOCK = """## boss-orchestrator (workspace orchestration)

For the top-level parent session in this workspace, follow the policy in
`.setting/boss-orchestrator.md` and the workers in `.setting/config.md`. At session
start, read both files and check `scope.root` and `state`; if `.setting` is missing,
the root does not match, or `state` is not `enabled`, workspace orchestration is
inactive. Work delegated to you as a child task is not covered by this block:
do the task yourself."""

CONFIG_INTRO = """# boss-orchestrator workspace config

Read by .setting/boss-orchestrator.md. The single fenced json block below is the only
machine-read part of this file; null means unresolved, never wildcard or permission.
"""


class InitError(Exception):
    def __init__(self, reasons: list[str] | str):
        self.reasons = [reasons] if isinstance(reasons, str) else reasons
        super().__init__("; ".join(self.reasons))


def _reject_dup(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for k, v in pairs:
        if k in d:
            raise InitError(f"Duplicate key {k!r} in JSON block")
        d[k] = v
    return d


def _reject_const(val: str) -> Any:
    raise InitError(f"Non-finite number {val!r} not allowed in config")


def parse_config_md(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    fences = [i for i, line in enumerate(lines) if re.match(r"^(`{3,}|~{3,})", line.strip())]
    if len(fences) != 2:
        raise InitError(f"Expected exactly 1 closed code fence in config, found {len(fences)//2}")
    tag = lines[fences[0]].lstrip("`~").strip().lower()
    if tag != "json":
        raise InitError(f"Config code block must be tagged json, found {tag!r}")
    raw = "\n".join(lines[fences[0] + 1:fences[1]])
    try:
        data = json.loads(raw, object_pairs_hook=_reject_dup, parse_constant=_reject_const)
    except json.JSONDecodeError as err:
        raise InitError(f"Invalid JSON: {err.msg} (line {err.lineno})") from None
    if not isinstance(data, dict):
        raise InitError("Config JSON must be an object")
    return data


def _check_keys(obj: dict[str, Any], allowed: set[str], path: str, errs: list[str]) -> None:
    for k in sorted(set(obj) - allowed):
        errs.append(f"{path}: unknown key {k!r}")
    for k in sorted(allowed - set(obj)):
        errs.append(f"{path}: missing key {k!r}")


def _is_date(val: Any) -> bool:
    if not isinstance(val, str) or not DATE_RE.match(val):
        return False
    try:
        date.fromisoformat(val)
        return True
    except ValueError:
        return False


def _is_reparse_or_link(path: Path) -> bool:
    try:
        if path.is_symlink() or os.path.islink(path):
            return True
        st = os.lstat(path)
        if hasattr(st, "st_file_attributes") and bool(st.st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT):
            return True
    except (OSError, ValueError):
        pass
    return False


def _safe_resolve(root: Path, rel_str: str) -> Path:
    if not root.is_dir():
        raise InitError(f"Root does not exist or is not a directory: {root}")
    if _is_reparse_or_link(root):
        raise InitError(f"Root directory is a symlink, junction, or reparse point: {root}")

    parts = Path(rel_str).parts
    curr = root
    for p in parts:
        if p == "..":
            curr = curr.parent
            try:
                curr.resolve().relative_to(root.resolve())
            except ValueError:
                raise InitError(f"Target path {rel_str!r} escapes root {str(root)!r}")
        else:
            curr = curr / p
            if curr.exists() and _is_reparse_or_link(curr):
                raise InitError(f"Symlink, junction, or reparse point rejected: {curr}")

    try:
        curr.resolve().relative_to(root.resolve())
    except ValueError:
        raise InitError(f"Target path {rel_str!r} escapes root {str(root)!r}")

    if curr.exists() and _is_reparse_or_link(curr):
        raise InitError(f"Symlink, junction, or reparse point rejected: {curr}")
    return curr


def _check_agents_override(root: Path) -> None:
    override_path = root / "AGENTS.override.md"
    if override_path.is_file():
        b = override_path.read_bytes()
        if len(b.strip()) > 0:
            raise InitError(
                "Root AGENTS.override.md is present and non-empty. "
                "Boss-orchestrator currently supports only AGENTS.md. "
                "Overriding instructions would conflict or bypass orchestration; aborting before persistent writes."
            )


def _validate_evidence(ev: Any, expected_level: str, path: str, errs: list[str]) -> None:
    if not isinstance(ev, dict):
        errs.append(f"{path} must be an object")
        return
    if not ev:
        errs.append(f"{path} cannot be empty object")
        return
    _check_keys(ev, {"level", "source_ref", "observed_at"}, path, errs)
    if ev.get("level") != expected_level:
        errs.append(f"{path}.level must be {expected_level!r}")
    if not isinstance(ev.get("source_ref"), str) or not ev["source_ref"].strip():
        errs.append(f"{path}.source_ref must be non-empty string")
    if not _is_date(ev.get("observed_at")):
        errs.append(f"{path}.observed_at must be valid YYYY-MM-DD date string")


def _validate_shared_config(cfg: dict[str, Any], root: Path | None, errs: list[str]) -> None:
    _check_keys(cfg, {"schema_version", "state", "scope", "harness", "parent", "workers", "boss", "confirmation"}, "root", errs)
    if cfg.get("state") not in ("draft", "enabled", "disabled"):
        errs.append("state must be draft, enabled, or disabled")

    # Scope validation
    scope = cfg.get("scope")
    if not isinstance(scope, dict):
        errs.append("scope must be an object")
    else:
        _check_keys(scope, {"kind", "root", "git"}, "scope", errs)
        if scope.get("kind") != "workspace":
            errs.append("scope.kind must be 'workspace'")
        if not isinstance(scope.get("root"), str) or not scope["root"].strip():
            errs.append("scope.root must be non-empty string")
        elif root and Path(scope["root"]).resolve() != root.resolve():
            errs.append(f"scope.root {scope['root']!r} does not match target root {str(root)!r}")
        if not isinstance(scope.get("git"), bool):
            errs.append("scope.git must be boolean")

    # Harness validation
    harness = cfg.get("harness")
    if not isinstance(harness, dict):
        errs.append("harness must be an object")
    else:
        _check_keys(harness, {"allowlist", "unsupported"}, "harness", errs)
        if not isinstance(harness.get("allowlist"), list) or not harness["allowlist"] or any(not isinstance(x, str) for x in harness["allowlist"]):
            errs.append("harness.allowlist must be non-empty list of strings")
        if harness.get("unsupported") != "cancel_before_writes":
            errs.append("harness.unsupported must be 'cancel_before_writes'")

    # Parent validation
    parent = cfg.get("parent")
    if not isinstance(parent, dict):
        errs.append("parent must be an object")
    else:
        _check_keys(parent, {"selection"}, "parent", errs)
        if parent.get("selection") != "current_active":
            errs.append("parent.selection must be 'current_active'")

    # Confirmation validation
    conf = cfg.get("confirmation")
    if cfg.get("state") == "enabled":
        if not isinstance(conf, dict):
            errs.append("confirmation must be an object when state is enabled")
        else:
            _check_keys(conf, {"approved_at"}, "confirmation", errs)
            if not _is_date(conf.get("approved_at")):
                errs.append("confirmation.approved_at valid YYYY-MM-DD date required when state is enabled")
    elif conf is not None:
        if not isinstance(conf, dict):
            errs.append("confirmation must be null or an object")
        else:
            _check_keys(conf, {"approved_at"}, "confirmation", errs)
            if not _is_date(conf.get("approved_at")):
                errs.append("confirmation.approved_at must be valid YYYY-MM-DD date")


def _validate_workers_common(
    workers: Any, cfg: dict[str, Any], errs: list[str], enforce_one_enabled_per_provider: bool
) -> set[str]:
    enabled_ids: set[str] = set()
    if not isinstance(workers, list) or not workers:
        errs.append("workers must be non-empty list")
        return enabled_ids

    seen_ids: set[str] = set()
    seen_routes: set[tuple[str, str, str]] = set()
    seen_enabled_providers: set[str] = set()

    for idx, w in enumerate(workers):
        p = f"workers[{idx}]"
        if not isinstance(w, dict):
            errs.append(f"{p}: must be an object")
            continue
        _check_keys(
            w,
            {
                "id", "label", "enabled", "disabled_reason", "provider_instance_id", "driver_kind",
                "route_id", "options", "thinking", "model_claim", "upstreams", "catalog_evidence",
                "execution_evidence"
            },
            p,
            errs,
        )
        wid = w.get("id")
        if not isinstance(wid, str) or not ID_RE.match(wid):
            errs.append(f"{p}.id must match {ID_RE.pattern}")
        elif wid in seen_ids:
            errs.append(f"{p}.id duplicate worker id {wid!r}")
        else:
            seen_ids.add(wid)

        if not isinstance(w.get("label"), str) or not w["label"].strip():
            errs.append(f"{p}.label must be non-empty string")

        pid = w.get("provider_instance_id")
        dk = w.get("driver_kind")
        rid = w.get("route_id")

        if not isinstance(pid, str) or not pid.strip():
            errs.append(f"{p}.provider_instance_id must be non-empty string")
        if not isinstance(dk, str) or not dk.strip():
            errs.append(f"{p}.driver_kind must be non-empty string")
        if not isinstance(rid, str) or not rid.strip():
            errs.append(f"{p}.route_id must be non-empty string")

        if isinstance(pid, str) and isinstance(dk, str) and isinstance(rid, str):
            route = (pid, dk, rid)
            if route in seen_routes:
                errs.append(f"{p}: duplicate route {route!r}")
            else:
                seen_routes.add(route)

        en = w.get("enabled")
        if not isinstance(en, bool):
            errs.append(f"{p}.enabled must be boolean")
        elif en:
            if isinstance(wid, str) and ID_RE.match(wid):
                enabled_ids.add(wid)
            if enforce_one_enabled_per_provider and isinstance(pid, str):
                if pid in seen_enabled_providers:
                    errs.append(f"{p}: provider_instance_id {pid!r} already has an enabled worker route")
                else:
                    seen_enabled_providers.add(pid)

            if w.get("disabled_reason") is not None:
                errs.append(f"{p}.disabled_reason must be null when enabled")
            if not isinstance(w.get("options"), dict) or not w["options"]:
                errs.append(f"{p}.options must be non-empty dict when enabled")
            if w.get("catalog_evidence") is None:
                errs.append(f"{p}.catalog_evidence required for enabled worker")
            else:
                _validate_evidence(w.get("catalog_evidence"), "catalog_verified", f"{p}.catalog_evidence", errs)
            if cfg.get("state") == "enabled":
                if w.get("execution_evidence") is None:
                    errs.append(f"{p}.execution_evidence required when state is enabled")
                else:
                    _validate_evidence(w.get("execution_evidence"), "execution_verified", f"{p}.execution_evidence", errs)
            elif w.get("execution_evidence") is not None:
                _validate_evidence(w.get("execution_evidence"), "execution_verified", f"{p}.execution_evidence", errs)
        else:
            if not isinstance(w.get("disabled_reason"), str) or not w["disabled_reason"].strip():
                errs.append(f"{p}.disabled_reason required when disabled")
            if w.get("execution_evidence") is not None:
                errs.append(f"{p}.execution_evidence must be null when disabled")
            if w.get("catalog_evidence") is not None:
                _validate_evidence(w.get("catalog_evidence"), "catalog_verified", f"{p}.catalog_evidence", errs)

        # Thinking validation
        th = w.get("thinking")
        if en is True:
            if not isinstance(th, dict):
                errs.append(f"{p}.thinking must be an object for enabled worker")
            else:
                for k in sorted(set(th) - {"mode", "option_key", "selected", "allowed_values", "reason"}):
                    errs.append(f"{p}.thinking: unknown key {k!r}")
                mode = th.get("mode")
                if mode == "default":
                    errs.append(f"{p}.thinking mode 'default' is not allowed for enabled worker")
                elif mode == "disabled":
                    if "reason" not in th or not isinstance(th.get("reason"), str) or not th["reason"].strip():
                        errs.append(f"{p}.thinking disabled requires non-empty reason")
                    for extra in ("option_key", "selected", "allowed_values"):
                        if extra in th:
                            errs.append(f"{p}.thinking disabled should not have {extra}")
                elif mode == "explicit":
                    for req in ("option_key", "selected", "allowed_values"):
                        if req not in th:
                            errs.append(f"{p}.thinking: missing key {req!r}")
                    if "reason" in th:
                        errs.append(f"{p}.thinking explicit should not have reason")
                    opt_key = th.get("option_key")
                    sel = th.get("selected")
                    allowed = th.get("allowed_values")
                    if opt_key is not None and (not isinstance(opt_key, str) or not opt_key.strip()):
                        errs.append(f"{p}.thinking explicit requires non-empty option_key")
                    if sel is not None and (not isinstance(sel, str) or not sel.strip()):
                        errs.append(f"{p}.thinking explicit requires non-empty selected")
                    if allowed is not None:
                        if not isinstance(allowed, list) or not allowed or any(not isinstance(x, str) for x in allowed):
                            errs.append(f"{p}.thinking explicit requires non-empty list of string allowed_values")
                        elif sel not in allowed:
                            errs.append(f"{p}.thinking selected {sel!r} not in allowed_values {allowed!r}")

                    opts = w.get("options")
                    if isinstance(opts, dict) and isinstance(opt_key, str) and isinstance(sel, str):
                        if opt_key not in opts:
                            errs.append(f"{p}.options missing thinking option_key {opt_key!r}")
                        elif opts[opt_key] != sel:
                            errs.append(f"{p}.options[{opt_key!r}] ({opts[opt_key]!r}) does not match thinking.selected ({sel!r})")
                else:
                    errs.append(f"{p}.thinking mode must be 'explicit' or 'disabled'")
        else:
            if th is not None:
                if not isinstance(th, dict):
                    errs.append(f"{p}.thinking must be an object or null")
                else:
                    for k in sorted(set(th) - {"mode", "option_key", "selected", "allowed_values", "reason"}):
                        errs.append(f"{p}.thinking: unknown key {k!r}")
                    if th.get("mode") not in ("default", "explicit", "disabled"):
                        errs.append(f"{p}.thinking mode must be default, explicit, or disabled")
                    elif th.get("mode") == "disabled" and ("reason" not in th or not isinstance(th.get("reason"), str) or not th["reason"].strip()):
                        errs.append(f"{p}.thinking disabled requires reason")

        # Model claim validation
        claim = w.get("model_claim")
        if not isinstance(claim, dict):
            errs.append(f"{p}.model_claim must be an object")
        else:
            _check_keys(claim, {"name", "provenance"}, f"{p}.model_claim", errs)
            if not isinstance(claim.get("name"), str) or not claim["name"].strip():
                errs.append(f"{p}.model_claim.name must be non-empty string")
            if claim.get("provenance") != "user_declared":
                errs.append(f"{p}.model_claim.provenance must be 'user_declared'")

        # Upstreams validation
        up = w.get("upstreams")
        if not isinstance(up, dict):
            errs.append(f"{p}.upstreams must be an object")
        else:
            _check_keys(up, {"mapping", "independence"}, f"{p}.upstreams", errs)
            if up.get("independence") not in ("unknown", "declared_independent", "declared_shared"):
                errs.append(f"{p}.upstreams.independence must be 'unknown', 'declared_independent', or 'declared_shared'")

    if cfg.get("state") == "enabled" and not enabled_ids:
        errs.append("state 'enabled' requires at least 1 enabled worker")

    return enabled_ids


def validate_config_v1(cfg: dict[str, Any], root: Path | None = None) -> list[str]:
    """Validate legacy schema_version 1 configuration."""
    errs: list[str] = []
    if not isinstance(cfg, dict):
        return ["Config root must be a JSON object"]

    ver = cfg.get("schema_version")
    if type(ver) is not int or isinstance(ver, bool) or ver != 1:
        errs.append("schema_version must be integer 1")

    _validate_shared_config(cfg, root, errs)
    enabled_ids = _validate_workers_common(cfg.get("workers"), cfg, errs, enforce_one_enabled_per_provider=False)

    boss = cfg.get("boss")
    if not isinstance(boss, dict):
        errs.append("boss must be an object")
    else:
        _check_keys(
            boss,
            {
                "selection", "review_exception", "recursive_delegation", "builtin_fallback",
                "fallback_workers", "priority", "reliability_memory", "parallel_scopes",
                "quality_feedback", "no_progress_rounds", "after_change"
            },
            "boss",
            errs,
        )
        if boss.get("selection") != "boss_per_task":
            errs.append("boss.selection must be 'boss_per_task'")
        if boss.get("review_exception") != "small_clear_local_review_fixes":
            errs.append("boss.review_exception must be 'small_clear_local_review_fixes'")
        if boss.get("recursive_delegation") != "task_explicit_only":
            errs.append("boss.recursive_delegation must be 'task_explicit_only'")
        if boss.get("builtin_fallback") != "excluded":
            errs.append("boss.builtin_fallback must be 'excluded'")
        if boss.get("priority") != "equal":
            errs.append("boss.priority must be 'equal'")
        if boss.get("reliability_memory") != "session":
            errs.append("boss.reliability_memory must be 'session'")
        if boss.get("parallel_scopes") != "disjoint_only":
            errs.append("boss.parallel_scopes must be 'disjoint_only'")
        if boss.get("quality_feedback") != "first":
            errs.append("boss.quality_feedback must be 'first'")
        if boss.get("after_change") != "escalate":
            errs.append("boss.after_change must be 'escalate'")

        npr = boss.get("no_progress_rounds")
        if not isinstance(npr, int) or isinstance(npr, bool) or npr <= 0:
            errs.append("boss.no_progress_rounds must be a positive integer")

        fb = boss.get("fallback_workers")
        if not isinstance(fb, list):
            errs.append("boss.fallback_workers must be a list")
        else:
            seen_fb: set[str] = set()
            for x in fb:
                if not isinstance(x, str):
                    errs.append(f"boss.fallback_workers elements must be string, found {type(x).__name__}")
                elif x in seen_fb:
                    errs.append(f"boss.fallback_workers contains duplicate worker id {x!r}")
                elif x not in enabled_ids:
                    errs.append(f"boss.fallback_workers contains worker id {x!r} which is not an enabled worker")
                else:
                    seen_fb.add(x)

    return errs


def validate_config_v2(cfg: dict[str, Any], root: Path | None = None) -> list[str]:
    """Validate current schema_version 2 configuration."""
    errs: list[str] = []
    if not isinstance(cfg, dict):
        return ["Config root must be a JSON object"]

    ver = cfg.get("schema_version")
    if type(ver) is not int or isinstance(ver, bool) or ver != 2:
        errs.append("schema_version must be integer 2")

    _validate_shared_config(cfg, root, errs)
    enabled_ids = _validate_workers_common(cfg.get("workers"), cfg, errs, enforce_one_enabled_per_provider=True)

    boss = cfg.get("boss")
    if not isinstance(boss, dict):
        errs.append("boss must be an object")
    else:
        # fallback_workers is redundant in v2 (workers order is the single source of truth).
        # We permit either omitting it or including a list that strictly matches enabled worker IDs in priority order.
        allowed_boss_keys = {
            "selection", "review_exception", "recursive_delegation", "builtin_fallback",
            "priority", "reliability_memory", "parallel_scopes", "quality_feedback",
            "no_progress_rounds", "after_change", "retry_after_successful_tasks"
        }
        if "fallback_workers" in boss:
            allowed_boss_keys.add("fallback_workers")

        _check_keys(boss, allowed_boss_keys, "boss", errs)

        if boss.get("selection") != "boss_per_task":
            errs.append("boss.selection must be 'boss_per_task'")
        if boss.get("review_exception") != "small_clear_local_review_fixes":
            errs.append("boss.review_exception must be 'small_clear_local_review_fixes'")
        if boss.get("recursive_delegation") != "task_explicit_only":
            errs.append("boss.recursive_delegation must be 'task_explicit_only'")
        if boss.get("builtin_fallback") != "excluded":
            errs.append("boss.builtin_fallback must be 'excluded'")
        if boss.get("priority") != "provider_order":
            errs.append("boss.priority must be 'provider_order'")
        if boss.get("reliability_memory") != "session":
            errs.append("boss.reliability_memory must be 'session'")
        if boss.get("parallel_scopes") != "disjoint_only":
            errs.append("boss.parallel_scopes must be 'disjoint_only'")
        if boss.get("quality_feedback") != "first":
            errs.append("boss.quality_feedback must be 'first'")
        if boss.get("after_change") != "escalate":
            errs.append("boss.after_change must be 'escalate'")

        npr = boss.get("no_progress_rounds")
        if not isinstance(npr, int) or isinstance(npr, bool) or npr <= 0:
            errs.append("boss.no_progress_rounds must be a positive integer")

        rst = boss.get("retry_after_successful_tasks")
        if not isinstance(rst, int) or isinstance(rst, bool) or rst <= 0:
            errs.append("boss.retry_after_successful_tasks must be a positive integer")

        if "fallback_workers" in boss:
            fb = boss.get("fallback_workers")
            workers = cfg.get("workers", [])
            ordered_enabled = [w.get("id") for w in workers if isinstance(w, dict) and w.get("enabled")]
            if not isinstance(fb, list) or fb != ordered_enabled:
                errs.append("boss.fallback_workers in schema_version 2 is redundant and must strictly match enabled worker IDs in priority order")

    return errs


def validate_config(cfg: dict[str, Any], root: Path | None = None, expected_version: int | None = None) -> list[str]:
    """Validate configuration according to its declared schema_version (1 or 2)."""
    if not isinstance(cfg, dict):
        return ["Config root must be a JSON object"]

    ver = cfg.get("schema_version")
    if expected_version is not None:
        if type(expected_version) is not int or isinstance(expected_version, bool):
            return [f"expected_version must be integer (1 or 2), got {type(expected_version).__name__}"]
        if type(ver) is not int or isinstance(ver, bool) or ver != expected_version:
            return [f"schema_version must be integer {expected_version}"]

    if type(ver) is not int or isinstance(ver, bool):
        return ["schema_version must be an integer (1 or 2)"]
    if ver == 1:
        return validate_config_v1(cfg, root)
    elif ver == 2:
        return validate_config_v2(cfg, root)
    else:
        return [f"unsupported schema_version {ver!r}; supported versions are 1, 2"]


# ==============================================================================
# Pure Deterministic Session Routing State Machine
# ==============================================================================

@dataclass
class HandoffBrief:
    goal_acceptance: str
    files_or_diff: str
    completed_steps: list[str]
    partial_steps: list[str]
    test_evidence_revision: str
    outstanding_errors: list[str]
    cancellation_uncertain_effects: str
    exact_next_action: str

    def validate(self) -> list[str]:
        errs = []
        if not isinstance(self.goal_acceptance, str) or not self.goal_acceptance.strip():
            errs.append("goal_acceptance must be non-empty string")
        if not isinstance(self.files_or_diff, str) or not self.files_or_diff.strip():
            errs.append("files_or_diff must be non-empty string")
        if not isinstance(self.completed_steps, list):
            errs.append("completed_steps must be a list")
        elif any(not isinstance(x, str) or not x.strip() for x in self.completed_steps):
            errs.append("completed_steps elements must be non-empty strings")
        if not isinstance(self.partial_steps, list):
            errs.append("partial_steps must be a list")
        elif any(not isinstance(x, str) or not x.strip() for x in self.partial_steps):
            errs.append("partial_steps elements must be non-empty strings")
        if not isinstance(self.test_evidence_revision, str) or not self.test_evidence_revision.strip():
            errs.append("test_evidence_revision must be non-empty string")
        if not isinstance(self.outstanding_errors, list):
            errs.append("outstanding_errors must be a list")
        elif any(not isinstance(x, str) or not x.strip() for x in self.outstanding_errors):
            errs.append("outstanding_errors elements must be non-empty strings")
        if not isinstance(self.cancellation_uncertain_effects, str) or not self.cancellation_uncertain_effects.strip():
            errs.append("cancellation_uncertain_effects must be non-empty string")
        if not isinstance(self.exact_next_action, str) or not self.exact_next_action.strip():
            errs.append("exact_next_action must be non-empty string")
        return errs


@dataclass
class ProviderStatus:
    worker_id: str
    provider_instance_id: str
    priority_rank: int  # 1 = highest priority
    state: Literal["healthy", "operational_failed", "quality_exhausted"] = "healthy"
    success_count_since_fail: int = 0
    active_recovery_trial_task_id: str | None = None
    last_failure_reason: str | None = None


@dataclass
class RouteDecision:
    action: Literal["dispatch", "recovery_trial", "queue", "escalate"]
    worker_id: str | None = None
    provider_instance_id: str | None = None
    priority_rank: int | None = None
    reason: str = ""
    is_recovery_trial: bool = False


class SessionRouter:
    """Pure in-memory deterministic routing verification and reference module for a boss session.

    NOTE: Live routing during task execution is instruction-governed by the top-level
    orchestrator agent without runtime harness middleware or hooks. This class serves as an
    executable reference state machine to verify and simulate routing invariants: ordered
    priorities, dynamic multi-instance capacity/queueing, operational advance, structured
    handoffs, per-task 2-round quality escalation, and session-only 5-task recovery trials.
    """

    def __init__(self, config: dict[str, Any]):
        errs = validate_config(config)
        if errs:
            raise InitError(f"Cannot initialize SessionRouter with invalid config: {'; '.join(errs)}")

        workers = config.get("workers", [])
        self.ordered_workers = [w for w in workers if isinstance(w, dict) and w.get("enabled") is True]
        boss = config.get("boss", {})
        self.no_progress_rounds_threshold: int = int(boss.get("no_progress_rounds", 2))
        self.retry_after_successful_tasks: int = int(boss.get("retry_after_successful_tasks", 5))

        self.providers: dict[str, ProviderStatus] = {}
        for rank, w in enumerate(self.ordered_workers, start=1):
            wid = w["id"]
            pid = w["provider_instance_id"]
            self.providers[wid] = ProviderStatus(
                worker_id=wid,
                provider_instance_id=pid,
                priority_rank=rank,
            )

        self.in_flight_tasks: dict[str, dict[str, Any]] = {}
        self.terminal_tasks: dict[str, dict[str, Any]] = {}
        self.accepted_task_ids: set[str] = set()
        self.consecutive_no_progress: dict[str, int] = {}  # keyed per task_id
        self.last_handoff: HandoffBrief | None = None

    def get_route_decision(self, capacity_available: bool = True) -> RouteDecision:
        """Determine next routing action: dispatch, recovery trial, queue, or escalate."""
        sorted_providers = sorted(self.providers.values(), key=lambda p: p.priority_rank)

        # 1. Check recovery trial eligibility on failed providers in priority order (highest priority first).
        # Invariant: only one global pending recovery trial across the entire session router.
        active_trial_exists = any(p.active_recovery_trial_task_id is not None for p in self.providers.values())
        if not active_trial_exists:
            for p in sorted_providers:
                if p.state != "healthy":
                    if p.success_count_since_fail >= self.retry_after_successful_tasks and p.active_recovery_trial_task_id is None:
                        if not capacity_available:
                            return RouteDecision(
                                action="queue",
                                worker_id=p.worker_id,
                                provider_instance_id=p.provider_instance_id,
                                priority_rank=p.priority_rank,
                                reason=f"Recovery trial permitted on {p.worker_id} but capacity full; queueing",
                                is_recovery_trial=True,
                            )
                        return RouteDecision(
                            action="recovery_trial",
                            worker_id=p.worker_id,
                            provider_instance_id=p.provider_instance_id,
                            priority_rank=p.priority_rank,
                            reason=f"Recovery trial permitted for {p.worker_id} after {p.success_count_since_fail} lower-priority completions",
                            is_recovery_trial=True,
                        )

        # 2. Find highest priority healthy provider
        for p in sorted_providers:
            if p.state == "healthy":
                if not capacity_available:
                    return RouteDecision(
                        action="queue",
                        worker_id=p.worker_id,
                        provider_instance_id=p.provider_instance_id,
                        priority_rank=p.priority_rank,
                        reason=f"Priority {p.priority_rank} ({p.worker_id}) capacity full; queueing without spilling",
                        is_recovery_trial=False,
                    )
                return RouteDecision(
                    action="dispatch",
                    worker_id=p.worker_id,
                    provider_instance_id=p.provider_instance_id,
                    priority_rank=p.priority_rank,
                    reason=f"Dispatching to eligible priority {p.priority_rank} ({p.worker_id})",
                    is_recovery_trial=False,
                )

        # 3. All providers exhausted
        return RouteDecision(
            action="escalate",
            reason="All configured providers exhausted or failed; escalating unaccepted without fallback",
        )

    def record_task_dispatch(self, task_id: str, worker_id: str, is_recovery_trial: bool = False) -> None:
        if worker_id not in self.providers:
            raise InitError(f"Unknown worker_id {worker_id!r}")
        if task_id in self.in_flight_tasks:
            raise InitError(f"Task {task_id!r} is already in-flight")
        if task_id in self.terminal_tasks:
            raise InitError(f"Task {task_id!r} has already completed; replay rejected")

        if is_recovery_trial:
            # Enforce only one global pending recovery trial
            if any(p.active_recovery_trial_task_id is not None for p in self.providers.values()):
                raise InitError("Only one global recovery trial may be pending or in-flight at a time")
            p = self.providers[worker_id]
            if p.state == "healthy":
                raise InitError(f"Worker {worker_id!r} is healthy; recovery trial not applicable")
            p.active_recovery_trial_task_id = task_id

        self.in_flight_tasks[task_id] = {
            "worker_id": worker_id,
            "is_recovery_trial": is_recovery_trial,
        }

    def record_operational_error(self, task_id: str, error_reason: str = "operational error", worker_id: str | None = None) -> None:
        if task_id in self.terminal_tasks:
            raise InitError(f"Task {task_id!r} has already completed and reached terminal state; replay rejected")
        if task_id not in self.in_flight_tasks:
            raise InitError(f"Task {task_id!r} is not in-flight; operational error rejected")

        task_info = self.in_flight_tasks[task_id]
        dispatched_worker = task_info["worker_id"]
        if worker_id is not None and worker_id != dispatched_worker:
            raise InitError(
                f"Worker mismatch for task {task_id!r}: task was dispatched to {dispatched_worker!r}, "
                f"operational error reported for {worker_id!r}; rejected before mutation"
            )
        worker_id = dispatched_worker

        del self.in_flight_tasks[task_id]
        self.terminal_tasks[task_id] = {
            "worker_id": worker_id,
            "outcome": "operational_error",
            "parent_accepted": False,
            "reason": error_reason,
        }

        p = self.providers[worker_id]
        p.state = "operational_failed"
        p.success_count_since_fail = 0
        p.last_failure_reason = error_reason
        if p.active_recovery_trial_task_id == task_id:
            p.active_recovery_trial_task_id = None

    def record_quality_round(self, task_id: str, worker_id: str, measurable_progress: bool) -> None:
        if worker_id not in self.providers:
            raise InitError(f"Unknown worker_id {worker_id!r}")
        if task_id in self.terminal_tasks:
            raise InitError(f"Task {task_id!r} has already reached terminal state; cannot record quality round")
        if task_id not in self.in_flight_tasks:
            raise InitError(f"Task {task_id!r} is not in-flight; cannot record quality round")

        task_info = self.in_flight_tasks[task_id]
        dispatched_worker = task_info["worker_id"]
        if worker_id != dispatched_worker:
            raise InitError(
                f"Worker mismatch for task {task_id!r}: task was dispatched to {dispatched_worker!r}, "
                f"quality round reported for {worker_id!r}; rejected before mutation"
            )

        # Quality rounds are keyed per task
        if measurable_progress:
            self.consecutive_no_progress[task_id] = 0
        else:
            cur = self.consecutive_no_progress.get(task_id, 0) + 1
            self.consecutive_no_progress[task_id] = cur
            if cur >= self.no_progress_rounds_threshold:
                p = self.providers[worker_id]
                p.state = "quality_exhausted"
                p.last_failure_reason = f"{cur} consecutive rounds with no measurable progress on task {task_id}"
                # Quality exhaustion settles/clears recovery and resets counter
                p.active_recovery_trial_task_id = None
                p.success_count_since_fail = 0
                self.consecutive_no_progress[task_id] = 0

    def record_task_completion(
        self,
        task_id: str,
        worker_id: str,
        outcome: Literal["success", "operational_error", "cancelled", "incomplete"],
        parent_accepted: bool = False,
    ) -> None:
        # 1. Terminal registry prevents all replay
        if task_id in self.terminal_tasks:
            raise InitError(f"Task {task_id!r} has already completed and reached terminal state; replay rejected")

        # 2. Require valid dispatched in-flight identity on completion (unknown task rejected)
        if task_id not in self.in_flight_tasks:
            raise InitError(f"Task {task_id!r} is not in-flight (unknown task completion rejected)")

        # 3. Worker mismatch rejected before mutation
        task_info = self.in_flight_tasks[task_id]
        dispatched_worker = task_info["worker_id"]
        if worker_id != dispatched_worker:
            raise InitError(
                f"Worker mismatch for task {task_id!r}: task was dispatched to {dispatched_worker!r}, "
                f"completion reported for {worker_id!r}; rejected before mutation"
            )

        if outcome == "operational_error":
            self.record_operational_error(task_id, error_reason="operational error", worker_id=worker_id)
            return

        is_trial = task_info.get("is_recovery_trial", False)

        # Validated: transition from in-flight to terminal
        del self.in_flight_tasks[task_id]
        self.terminal_tasks[task_id] = {
            "worker_id": worker_id,
            "outcome": outcome,
            "parent_accepted": parent_accepted,
        }

        p = self.providers[worker_id]

        if outcome in ("cancelled", "incomplete") or not parent_accepted:
            if is_trial and p.active_recovery_trial_task_id == task_id:
                # Recovery trial did not complete and get accepted: trial failed, reset counter
                p.active_recovery_trial_task_id = None
                p.success_count_since_fail = 0
            return

        # Accepted success
        self.accepted_task_ids.add(task_id)

        if is_trial and p.active_recovery_trial_task_id == task_id:
            # Recovery trial passed! Restore provider
            p.state = "healthy"
            p.active_recovery_trial_task_id = None
            p.success_count_since_fail = 0
            p.last_failure_reason = None
            return

        # Normal accepted task: increment success_count_since_fail on all HIGHER-priority failed providers
        for other in self.providers.values():
            if other.state != "healthy" and other.priority_rank < p.priority_rank:
                other.success_count_since_fail += 1

    def create_handoff(self, brief: HandoffBrief) -> HandoffBrief:
        errs = brief.validate()
        if errs:
            raise InitError(f"Invalid HandoffBrief: {'; '.join(errs)}")
        self.last_handoff = brief
        return brief

    def reset_session(self) -> None:
        """Reset routing state for a new session without cross-session persistent state."""
        self.in_flight_tasks.clear()
        self.terminal_tasks.clear()
        self.accepted_task_ids.clear()
        self.consecutive_no_progress.clear()
        self.last_handoff = None
        for p in self.providers.values():
            p.state = "healthy"
            p.success_count_since_fail = 0
            p.active_recovery_trial_task_id = None
            p.last_failure_reason = None


# ==============================================================================
# Rendering and Lifecycle
# ==============================================================================

def get_runtime_template_bytes() -> bytes:
    base = Path(__file__).resolve().parent.parent
    for cand in (base / "references" / "runtime-policy.md", base / "templates" / "runtime-policy.md"):
        if cand.is_file():
            return cand.read_bytes()
    return b"# boss-orchestrator runtime policy\n\nRole: parent_only. Substantive work delegated.\n"


def render_agents_bytes(existing_bytes: bytes | None) -> bytes:
    marker_b = MARKER_BEGIN.encode("utf-8")
    marker_e = MARKER_END.encode("utf-8")

    if existing_bytes is None:
        return f"{MARKER_BEGIN}\n{AGENTS_BLOCK}\n{MARKER_END}\n".encode("utf-8")

    bc = existing_bytes.count(marker_b)
    ec = existing_bytes.count(marker_e)
    if bc != ec or bc > 1:
        raise InitError(f"Corrupt AGENTS.md markers (begin={bc}, end={ec})")

    newline_bytes = b"\r\n" if b"\r\n" in existing_bytes else b"\n"
    newline_str = "\r\n" if b"\r\n" in existing_bytes else "\n"

    block_str = f"{MARKER_BEGIN}{newline_str}{AGENTS_BLOCK.replace(chr(10), newline_str)}{newline_str}{MARKER_END}"
    block_bytes = block_str.encode("utf-8")

    if bc == 1:
        bi = existing_bytes.index(marker_b)
        ei = existing_bytes.index(marker_e)
        if bi > ei:
            raise InitError("Corrupt AGENTS.md markers: begin is after end")
        before = existing_bytes[:bi]
        after = existing_bytes[ei + len(marker_e):]
        return before + block_bytes + after

    # Append markers
    if existing_bytes.endswith(newline_bytes * 2):
        sep = b""
    elif existing_bytes.endswith(newline_bytes):
        sep = newline_bytes
    else:
        sep = newline_bytes * 2

    return existing_bytes + sep + block_bytes + newline_bytes


def render_config_bytes(cfg: dict[str, Any], existing_bytes: bytes | None) -> bytes:
    json_str = json.dumps(cfg, indent=2)
    if existing_bytes is None:
        return f"{CONFIG_INTRO}\n```json\n{json_str}\n```\n".encode("utf-8")

    text = existing_bytes.decode("utf-8")
    newline_str = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline_str) if newline_str in text else text.splitlines()

    fence_indices = []
    for i, line in enumerate(lines):
        if re.match(r"^(`{3,}|~{3,})", line.strip()):
            fence_indices.append(i)

    if len(fence_indices) >= 2:
        f1, f2 = fence_indices[0], fence_indices[1]
        fence_match = re.match(r"^(`{3,}|~{3,})", lines[f1].strip())
        fence_len = len(fence_match.group(1)) if fence_match else 3
        fence_char = lines[f1].strip()[0]
        fence_marker = fence_char * fence_len

        before_lines = lines[:f1]
        after_lines = lines[f2 + 1:]

        json_lines = json_str.splitlines()
        new_block = [f"{fence_marker}json"] + json_lines + [fence_marker]

        result_lines = before_lines + new_block + after_lines
        return newline_str.join(result_lines).encode("utf-8")

    res = f"{CONFIG_INTRO}\n```json\n{json_str}\n```\n"
    if newline_str == "\r\n":
        res = res.replace("\n", "\r\n")
    return res.encode("utf-8")


def render_managed(root: Path, cfg: dict[str, Any], existing_override: dict[str, bytes | None] | None = None) -> dict[str, bytes]:
    if existing_override and "AGENTS.md" in existing_override:
        existing_agents = existing_override["AGENTS.md"]
    else:
        agents_path = _safe_resolve(root, "AGENTS.md")
        existing_agents = agents_path.read_bytes() if agents_path.is_file() else None

    if existing_override and ".setting/config.md" in existing_override:
        existing_config = existing_override[".setting/config.md"]
    else:
        config_path = _safe_resolve(root, ".setting/config.md")
        existing_config = config_path.read_bytes() if config_path.is_file() else None

    return {
        "AGENTS.md": render_agents_bytes(existing_agents),
        ".setting/config.md": render_config_bytes(cfg, existing_config),
        ".setting/boss-orchestrator.md": get_runtime_template_bytes(),
    }


def sha256_bytes(b: bytes | None) -> str | None:
    return hashlib.sha256(b).hexdigest() if b is not None else None


def make_plan(root: Path, config_content: str) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir() or _is_reparse_or_link(root):
        raise InitError(f"Root does not exist, is not a directory, or is a reparse point: {root}")

    _check_agents_override(root)

    cfg = parse_config_md(config_content)
    ver = cfg.get("schema_version")
    if type(ver) is not int or isinstance(ver, bool):
        raise InitError(f"schema_version must be an integer (1 or 2), found {type(ver).__name__}")
    if ver == 1:
        raise InitError(
            "Config has schema_version 1 (legacy). New plans require schema_version 2. "
            "Please use the migrate command to draft a v2 configuration with one enabled route per provider and ordered priority."
        )
    elif ver != 2:
        raise InitError(f"Unsupported schema_version {ver!r}; expected {SCHEMA_VERSION}")

    errs = validate_config_v2(cfg, root)
    if errs:
        raise InitError(errs)

    rendered = render_managed(root, cfg)
    files_plan = []
    for rel_path, new_bytes in rendered.items():
        fpath = _safe_resolve(root, rel_path)
        cur_bytes = fpath.read_bytes() if fpath.is_file() else None
        b_sha, a_sha = sha256_bytes(cur_bytes), sha256_bytes(new_bytes)
        cur_text = cur_bytes.decode("utf-8") if cur_bytes is not None else ""
        new_text = new_bytes.decode("utf-8")
        diff = "".join(
            difflib.unified_diff(
                cur_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
            )
        )
        files_plan.append({
            "path": rel_path,
            "before_sha256": b_sha,
            "after_sha256": a_sha,
            "content": new_text,
            "diff": diff,
        })
    return {"version": SCHEMA_VERSION, "root": str(root), "config": cfg, "files": files_plan}


def apply_plan(root: Path, plan_data: dict[str, Any], confirmed: bool) -> tuple[int, str]:
    if not confirmed:
        raise InitError("Apply refused: --confirmed flag required for execution")

    root = root.resolve()
    if not root.is_dir() or _is_reparse_or_link(root):
        raise InitError(f"Root does not exist, is not a directory, or is a reparse point: {root}")

    _check_agents_override(root)

    if not isinstance(plan_data, dict):
        raise InitError("Plan data must be a JSON object")

    p_ver = plan_data.get("version")
    if type(p_ver) is not int or isinstance(p_ver, bool) or p_ver not in SUPPORTED_SCHEMA_VERSIONS:
        raise InitError(f"Plan version mismatch: expected integer in {SUPPORTED_SCHEMA_VERSIONS}")

    plan_root = Path(plan_data.get("root", "")).resolve()
    if root != plan_root:
        raise InitError(f"Plan root mismatch: plan for {str(plan_root)!r}, target is {str(root)!r}")

    cfg = plan_data.get("config")
    if not isinstance(cfg, dict):
        raise InitError("Plan missing valid config object")

    errs = validate_config(cfg, root, expected_version=p_ver)
    if errs:
        raise InitError(errs)

    raw_files = plan_data.get("files")
    if not isinstance(raw_files, list):
        raise InitError("Plan files must be a list")

    seen_paths: set[str] = set()
    plan_files: dict[str, dict[str, Any]] = {}
    for pf in raw_files:
        if not isinstance(pf, dict) or "path" not in pf:
            raise InitError("Invalid file entry in plan")
        p = pf["path"]
        if p in seen_paths:
            raise InitError(f"Duplicate path {p!r} in plan files")
        seen_paths.add(p)
        plan_files[p] = pf

    if seen_paths != set(MANAGED_FILES):
        raise InitError(f"Plan files mismatch expected {set(MANAGED_FILES)}, found {seen_paths}")

    # Verify self-consistency of each planned file's after_sha256
    for rel_path, pf in plan_files.items():
        f_content = pf.get("content")
        if not isinstance(f_content, str):
            raise InitError(f"Plan file {rel_path} content must be string")
        f_bytes = f_content.encode("utf-8")
        actual_sha = sha256_bytes(f_bytes)
        if pf.get("after_sha256") != actual_sha:
            raise InitError(f"Plan tampering detected: after_sha256 mismatch for {rel_path}")

    # Check disk state for stale plan or already-planned status
    disk_bytes: dict[str, bytes | None] = {}
    disk_shas: dict[str, str | None] = {}
    for rel_path, pf in plan_files.items():
        target = _safe_resolve(root, rel_path)
        cur_b = target.read_bytes() if target.is_file() else None
        disk_bytes[rel_path] = cur_b
        disk_shas[rel_path] = sha256_bytes(cur_b)

    all_current = all(
        disk_bytes[rp] is not None and disk_shas[rp] == pf.get("after_sha256")
        for rp, pf in plan_files.items()
    )

    if not all_current:
        for rel_path, pf in plan_files.items():
            if disk_shas[rel_path] != pf.get("before_sha256"):
                raise InitError(f"Stale plan: {rel_path} before SHA256 mismatch (expected {pf.get('before_sha256')}, got {disk_shas[rel_path]})")

    # Tamper check: deterministic rendering from cfg and baseline disk state must match plan content
    expected = render_managed(root, cfg)
    for rel_path, exp_bytes in expected.items():
        pf = plan_files[rel_path]
        f_bytes = pf["content"].encode("utf-8")
        if f_bytes != exp_bytes:
            raise InitError(f"Plan tampering detected: content of {rel_path} altered")

    if all_current:
        return 2, "Workspace already in planned state. No changes written."

    # Identify files that actually need changing
    changed_files: dict[str, tuple[Path, bytes, bytes | None]] = {}
    for rel_path, pf in plan_files.items():
        target = _safe_resolve(root, rel_path)
        cur_b = disk_bytes[rel_path]
        target_bytes = pf["content"].encode("utf-8")
        if cur_b != target_bytes:
            changed_files[rel_path] = (target, target_bytes, cur_b)

    if not changed_files:
        return 2, "Workspace already in planned state. No changes written."

    # Preflight and write changed files atomically
    temp_files: list[Path] = []
    backups: dict[Path, bytes | None] = {}
    try:
        for rel_path, (target, target_bytes, cur_b) in changed_files.items():
            if target.exists() and not target.is_file():
                raise InitError(f"Target {rel_path} exists and is not a regular file")
            target.parent.mkdir(parents=True, exist_ok=True)
            if _is_reparse_or_link(target.parent):
                raise InitError(f"Parent directory of {rel_path} is a reparse point")
            backups[target] = cur_b

            tmp = target.parent / f".tmp_{target.name}_{os.getpid()}_{len(temp_files)}"
            temp_files.append(tmp)
            tmp.write_bytes(target_bytes)

        for (rel_path, (target, target_bytes, cur_b)), tmp in zip(changed_files.items(), temp_files):
            os.replace(tmp, target)

        temp_files.clear()
        return 0, f"Successfully applied plan to {root}"
    except Exception as exc:
        rollback_errors = []
        for target, prev_bytes in backups.items():
            try:
                if prev_bytes is None:
                    if target.exists():
                        target.unlink()
                else:
                    target.write_bytes(prev_bytes)
            except Exception as r_exc:
                rollback_errors.append(f"failed to restore {target}: {r_exc}")
        for tmp in temp_files:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception as r_exc:
                rollback_errors.append(f"failed to delete temp file {tmp}: {r_exc}")

        if rollback_errors:
            raise InitError(f"Write failure; rollback partially failed ({'; '.join(rollback_errors)}), original error: {exc}") from exc
        raise InitError(f"Write failure, rolled back: {exc}") from exc


def get_status(root: Path) -> dict[str, Any]:
    """Check workspace status, honestly supporting legacy v1 and v2 without auto-conversion."""
    root = root.resolve()
    if not root.is_dir() or _is_reparse_or_link(root):
        return {"status": "invalid", "root": str(root), "errors": ["Root directory invalid, non-existent, or reparse point"]}

    override_path = root / "AGENTS.override.md"
    if override_path.is_file() and len(override_path.read_bytes().strip()) > 0:
        return {"status": "invalid", "root": str(root), "errors": ["Root AGENTS.override.md is present and non-empty"]}

    cfg_file = root / ".setting/config.md"
    if not cfg_file.is_file():
        return {"status": "uninitialized", "root": str(root)}

    runtime_file = root / ".setting/boss-orchestrator.md"
    if not runtime_file.is_file():
        return {"status": "invalid", "root": str(root), "errors": [".setting/boss-orchestrator.md runtime policy missing"]}

    agents_file = root / "AGENTS.md"
    if not agents_file.is_file():
        return {"status": "invalid", "root": str(root), "errors": ["AGENTS.md pointer missing"]}

    ag_bytes = agents_file.read_bytes()
    if MARKER_BEGIN.encode("utf-8") not in ag_bytes or MARKER_END.encode("utf-8") not in ag_bytes:
        return {"status": "invalid", "root": str(root), "errors": ["AGENTS.md pointer markers missing or corrupt"]}

    try:
        cfg = parse_config_md(cfg_file.read_bytes().decode("utf-8"))
        ver = cfg.get("schema_version")
        if type(ver) is not int or isinstance(ver, bool):
            return {"status": "invalid", "root": str(root), "errors": ["schema_version must be an integer (1 or 2)"]}
        errs = validate_config(cfg, root)
        if errs:
            return {"status": "invalid", "root": str(root), "schema_version": ver, "state": cfg.get("state"), "errors": errs}

        state = cfg.get("state")
        is_legacy = (ver == 1)
        res = {
            "status": "active" if state == "enabled" else "inactive",
            "state": state,
            "schema_version": ver,
            "legacy": is_legacy,
            "root": str(root),
        }
        if is_legacy:
            res["notice"] = "Running on legacy schema_version 1 configuration. Migration to schema_version 2 available."
        return res
    except Exception as exc:
        return {"status": "invalid", "root": str(root), "errors": [str(exc)]}


def migrate_v1_to_v2(
    v1_cfg: dict[str, Any],
    selected_routes: dict[str, str] | None = None,
    ordered_worker_ids: list[str] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Draft a migration from v1 to v2. Requires explicit user decisions for conflicting routes."""
    if not isinstance(v1_cfg, dict):
        return None, ["v1 config must be a JSON object"]
    ver = v1_cfg.get("schema_version")
    if type(ver) is not int or isinstance(ver, bool) or ver != 1:
        return None, [f"schema_version must be integer 1 for migration, got {ver!r}"]

    errs = validate_config_v1(v1_cfg)
    if errs:
        return None, [f"Invalid v1 config: {'; '.join(errs)}"]

    selected_routes = selected_routes or {}
    workers = v1_cfg.get("workers", [])

    # Group enabled workers by provider_instance_id
    provider_workers: dict[str, list[dict[str, Any]]] = {}
    for w in workers:
        if w.get("enabled"):
            pid = w.get("provider_instance_id")
            provider_workers.setdefault(pid, []).append(w)

    conflicts: list[str] = []
    for pid, w_list in provider_workers.items():
        if len(w_list) > 1:
            if pid not in selected_routes:
                options_str = ", ".join(f"{w['id']} ({w['route_id']})" for w in w_list)
                conflicts.append(
                    f"Provider {pid!r} has multiple enabled routes [{options_str}]. "
                    f"Choose exactly one via --select-route {pid}=<route_id>"
                )
            else:
                chosen_route = selected_routes[pid]
                if not any(w["route_id"] == chosen_route for w in w_list):
                    conflicts.append(f"Selected route {chosen_route!r} does not match any worker for provider {pid!r}")

    if conflicts:
        return None, conflicts

    # Transform to v2
    v2_cfg = json.loads(json.dumps(v1_cfg))
    v2_cfg["schema_version"] = 2

    new_workers = []
    for w in v2_cfg.get("workers", []):
        pid = w.get("provider_instance_id")
        if pid in selected_routes:
            if w.get("route_id") == selected_routes[pid]:
                w["enabled"] = True
                w["disabled_reason"] = None
            else:
                w["enabled"] = False
                w["disabled_reason"] = "inactive provider route alternative"
                w["execution_evidence"] = None
        new_workers.append(w)

    # Reorder enabled workers if ordered_worker_ids provided
    if ordered_worker_ids:
        seen_order: set[str] = set()
        for wid in ordered_worker_ids:
            if wid in seen_order:
                return None, [f"Duplicate worker id {wid!r} in --order list"]
            seen_order.add(wid)

        worker_map = {w["id"]: w for w in new_workers}
        ordered = []
        for wid in ordered_worker_ids:
            if wid in worker_map:
                ordered.append(worker_map[wid])
            else:
                return None, [f"Ordered worker id {wid!r} not found in workers"]
        # Append remaining workers
        for w in new_workers:
            if w["id"] not in ordered_worker_ids:
                ordered.append(w)
        new_workers = ordered

    v2_cfg["workers"] = new_workers

    # Update boss block
    boss = v2_cfg.setdefault("boss", {})
    boss["priority"] = "provider_order"
    boss["retry_after_successful_tasks"] = 5
    if "fallback_workers" in boss:
        del boss["fallback_workers"]

    # Validate emitted draft
    draft_errs = validate_config_v2(v2_cfg)
    if draft_errs:
        return None, [f"Emitted v2 draft configuration failed validation: {'; '.join(draft_errs)}"]

    return v2_cfg, []


# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="boss-orchestrator-init local deterministic helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="Validate a config file (v1 or v2)")
    p_val.add_argument("--config", type=str, help="Path to config.md or '-' for stdin")
    p_val.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root")
    p_val.add_argument("--expected-version", type=int, choices=[1, 2], help="Require specific schema version")

    p_plan = sub.add_parser("plan", help="Render plan for initialization (emits v2)")
    p_plan.add_argument("--root", type=Path, required=True, help="Workspace root")
    p_plan.add_argument("--config", type=str, required=True, help="Path to config.md or '-' for stdin")
    p_plan.add_argument("--out", type=str, help="Optional output path for plan JSON or '-' for stdout")

    p_app = sub.add_parser("apply", help="Apply a generated plan")
    p_app.add_argument("--root", type=Path, required=True, help="Workspace root")
    p_app.add_argument("--plan", type=str, required=True, help="Path to plan JSON or '-' for stdin")
    p_app.add_argument("--confirmed", action="store_true", help="Actual user confirmation acknowledged")

    p_st = sub.add_parser("status", help="Check workspace orchestration status")
    p_st.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root")

    p_mig = sub.add_parser("migrate", help="Draft v2 migration from v1 config")
    p_mig.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root")
    p_mig.add_argument("--config", type=str, help="Path to config.md (defaults to .setting/config.md)")
    p_mig.add_argument("--select-route", action="append", help="Select route: provider_instance_id=route_id")
    p_mig.add_argument("--order", type=str, help="Comma-separated worker IDs in priority order")
    p_mig.add_argument("--out", type=str, help="Optional output path for draft config or '-' for stdout")

    args = parser.parse_args()
    try:
        if args.cmd == "validate":
            if args.config == "-":
                raw_text = sys.stdin.read()
            else:
                cpath = Path(args.config) if args.config else (args.root / ".setting/config.md")
                if not cpath.is_file():
                    raise InitError(f"Config file not found: {cpath}")
                raw_text = cpath.read_bytes().decode("utf-8")

            cfg = parse_config_md(raw_text)
            errs = validate_config(cfg, args.root.resolve(), expected_version=args.expected_version)
            if errs:
                sys.stderr.write("Validation errors:\n" + "\n".join(f"- {e}" for e in errs) + "\n")
                return 1
            ver = cfg.get("schema_version")
            print(f"OK: Config (schema_version {ver}) is valid.")
            return 0

        elif args.cmd == "plan":
            if args.config == "-":
                raw_text = sys.stdin.read()
            else:
                cpath = Path(args.config)
                if not cpath.is_file():
                    raise InitError(f"Config file not found: {cpath}")
                raw_text = cpath.read_bytes().decode("utf-8")

            plan_data = make_plan(args.root, raw_text)
            out_json = json.dumps(plan_data, indent=2)

            if args.out and args.out != "-":
                out_path = Path(args.out)
                root_res = args.root.resolve()
                try:
                    rel = out_path.resolve().relative_to(root_res)
                    if str(rel).replace("\\", "/") in MANAGED_FILES:
                        raise InitError(f"Cannot output plan directly to managed file {rel}")
                except ValueError:
                    pass

                if not out_path.parent.exists():
                    raise InitError(f"Parent directory for --out does not exist: {out_path.parent}")
                if _is_reparse_or_link(out_path.parent) or (out_path.exists() and _is_reparse_or_link(out_path)):
                    raise InitError("Symlink or reparse point rejected for --out")

                out_path.write_bytes(out_json.encode("utf-8"))
                print(f"Plan saved to {args.out}")
            else:
                print(out_json)
            return 0

        elif args.cmd == "apply":
            if args.plan == "-":
                raw_json = sys.stdin.read()
            else:
                ppath = Path(args.plan)
                if not ppath.is_file():
                    raise InitError(f"Plan file not found: {ppath}")
                raw_json = ppath.read_bytes().decode("utf-8")

            pdata = json.loads(raw_json)
            code, msg = apply_plan(args.root, pdata, args.confirmed)
            print(msg)
            return code

        elif args.cmd == "status":
            st = get_status(args.root)
            print(json.dumps(st, indent=2))
            return 0 if st.get("status") == "active" else 1

        elif args.cmd == "migrate":
            cpath = Path(args.config) if args.config else (args.root / ".setting/config.md")
            if not cpath.is_file():
                raise InitError(f"Config file not found: {cpath}")
            raw_text = cpath.read_bytes().decode("utf-8")
            cfg = parse_config_md(raw_text)

            ver = cfg.get("schema_version")
            if type(ver) is int and not isinstance(ver, bool) and ver == 2:
                print("Config is already schema_version 2. No migration needed.")
                return 0

            selected_map: dict[str, str] = {}
            if args.select_route:
                for item in args.select_route:
                    if "=" not in item:
                        raise InitError(f"Invalid --select-route format {item!r}; expected provider_id=route_id")
                    k, v = item.split("=", 1)
                    selected_map[k.strip()] = v.strip()

            order_list: list[str] | None = None
            if args.order:
                order_list = [x.strip() for x in args.order.split(",") if x.strip()]

            v2_draft, issues = migrate_v1_to_v2(cfg, selected_map, order_list)
            if issues:
                res = {
                    "status": "migration_choices_required",
                    "current_version": 1,
                    "target_version": 2,
                    "issues": issues,
                    "usage": "Run migrate with --select-route <provider>=<route_id> and --order <worker1,worker2,...>"
                }
                print(json.dumps(res, indent=2))
                return 1

            rendered_draft = f"{CONFIG_INTRO}\n```json\n{json.dumps(v2_draft, indent=2)}\n```\n"
            if args.out and args.out != "-":
                out_path = Path(args.out)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(rendered_draft.encode("utf-8"))
                print(f"Migration draft v2 config saved to {args.out}")
            else:
                print(rendered_draft)
            return 0

    except InitError as ie:
        sys.stderr.write(f"Error: {ie}\n")
        return 1
    except Exception as ex:
        sys.stderr.write(f"Unexpected error: {ex}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
