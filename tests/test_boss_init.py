#!/usr/bin/env python3
"""Comprehensive stdlib unittest test suite for boss-orchestrator-init.

Covers:
- Legacy schema_version 1 backwards compatibility and status preservation.
- Schema_version 2 ordered-provider validation, uniqueness, and strict priority.
- Deterministic SessionRouter state machine (queueing, operational advance,
  structured handoff, 2-round quality escalation, 5-task accepted recovery trial,
  trial success/failure resets, multi-level failures, and session reset).
- Atomicity, plan tampering detection, stale plans, BOM/CRLF, and Matt Pocock coexistence.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "boss-orchestrator-init" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import boss_init
from boss_init import SessionRouter, HandoffBrief, RouteDecision


def make_valid_config_v2(root_path: Path, state: str = "draft") -> dict:
    return {
        "schema_version": 2,
        "state": state,
        "scope": {
            "kind": "workspace",
            "root": str(root_path.resolve()),
            "git": False,
        },
        "harness": {
            "allowlist": ["t3"],
            "unsupported": "cancel_before_writes",
        },
        "parent": {
            "selection": "current_active",
        },
        "workers": [
            {
                "id": "worker-1",
                "label": "Worker One (Priority 1)",
                "enabled": True,
                "disabled_reason": None,
                "provider_instance_id": "inst_1",
                "driver_kind": "driver_1",
                "route_id": "route_1",
                "options": {"thinking_level": "high"},
                "thinking": {
                    "mode": "explicit",
                    "option_key": "thinking_level",
                    "selected": "high",
                    "allowed_values": ["low", "medium", "high"],
                },
                "model_claim": {"name": "Test Model", "provenance": "user_declared"},
                "upstreams": {"mapping": None, "independence": "unknown"},
                "catalog_evidence": {
                    "level": "catalog_verified",
                    "source_ref": "catalog",
                    "observed_at": "2026-11-06",
                },
                "execution_evidence": {
                    "level": "execution_verified",
                    "source_ref": "test_run",
                    "observed_at": "2026-11-06",
                } if state == "enabled" else None,
            },
            {
                "id": "worker-2",
                "label": "Worker Two (Priority 2)",
                "enabled": True,
                "disabled_reason": None,
                "provider_instance_id": "inst_2",
                "driver_kind": "driver_2",
                "route_id": "route_2",
                "options": {"thinking_level": "high"},
                "thinking": {
                    "mode": "explicit",
                    "option_key": "thinking_level",
                    "selected": "high",
                    "allowed_values": ["low", "medium", "high"],
                },
                "model_claim": {"name": "Test Model 2", "provenance": "user_declared"},
                "upstreams": {"mapping": None, "independence": "unknown"},
                "catalog_evidence": {
                    "level": "catalog_verified",
                    "source_ref": "catalog",
                    "observed_at": "2026-11-06",
                },
                "execution_evidence": {
                    "level": "execution_verified",
                    "source_ref": "test_run_2",
                    "observed_at": "2026-11-06",
                } if state == "enabled" else None,
            },
            {
                "id": "worker-disabled",
                "label": "Disabled Worker",
                "enabled": False,
                "disabled_reason": "inactive provider route alternative",
                "provider_instance_id": "inst_1",
                "driver_kind": "driver_1",
                "route_id": "route_alt",
                "options": None,
                "thinking": {"mode": "disabled", "reason": "unsupported"},
                "model_claim": {"name": "Unresolved Model", "provenance": "user_declared"},
                "upstreams": {"mapping": None, "independence": "unknown"},
                "catalog_evidence": None,
                "execution_evidence": None,
            },
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
            "retry_after_successful_tasks": 5,
        },
        "confirmation": {"approved_at": "2026-11-06"} if state == "enabled" else None,
    }


def make_valid_config_v1(root_path: Path, state: str = "draft") -> dict:
    return {
        "schema_version": 1,
        "state": state,
        "scope": {
            "kind": "workspace",
            "root": str(root_path.resolve()),
            "git": False,
        },
        "harness": {
            "allowlist": ["t3"],
            "unsupported": "cancel_before_writes",
        },
        "parent": {
            "selection": "current_active",
        },
        "workers": [
            {
                "id": "worker-1",
                "label": "Worker One",
                "enabled": True,
                "disabled_reason": None,
                "provider_instance_id": "opencode",
                "driver_kind": "opencode",
                "route_id": "route_1",
                "options": {"thinking_level": "high"},
                "thinking": {
                    "mode": "explicit",
                    "option_key": "thinking_level",
                    "selected": "high",
                    "allowed_values": ["low", "medium", "high"],
                },
                "model_claim": {"name": "Test Model", "provenance": "user_declared"},
                "upstreams": {"mapping": None, "independence": "unknown"},
                "catalog_evidence": {
                    "level": "catalog_verified",
                    "source_ref": "catalog",
                    "observed_at": "2026-11-06",
                },
                "execution_evidence": {
                    "level": "execution_verified",
                    "source_ref": "test_run",
                    "observed_at": "2026-11-06",
                } if state == "enabled" else None,
            },
            {
                "id": "worker-2",
                "label": "Worker Two",
                "enabled": True,
                "disabled_reason": None,
                "provider_instance_id": "opencode",
                "driver_kind": "opencode",
                "route_id": "route_2",
                "options": {"thinking_level": "high"},
                "thinking": {
                    "mode": "explicit",
                    "option_key": "thinking_level",
                    "selected": "high",
                    "allowed_values": ["low", "medium", "high"],
                },
                "model_claim": {"name": "Test Model 2", "provenance": "user_declared"},
                "upstreams": {"mapping": None, "independence": "unknown"},
                "catalog_evidence": {
                    "level": "catalog_verified",
                    "source_ref": "catalog",
                    "observed_at": "2026-11-06",
                },
                "execution_evidence": {
                    "level": "execution_verified",
                    "source_ref": "test_run_2",
                    "observed_at": "2026-11-06",
                } if state == "enabled" else None,
            },
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
            "fallback_workers": ["worker-1", "worker-2"],
        },
        "confirmation": {"approved_at": "2026-11-06"} if state == "enabled" else None,
    }


# Backwards compatibility alias for existing tests
make_valid_config = make_valid_config_v2


def write_config_md(file_path: Path, cfg: dict):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"# Workspace Config\n\n```json\n{json.dumps(cfg, indent=2)}\n```\n"
    file_path.write_bytes(content.encode("utf-8"))


class TestBossInit(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir).resolve()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sample_config_template_validates(self):
        sample_path = Path(__file__).resolve().parent.parent / "skills" / "boss-orchestrator-init" / "templates" / "sample-config.md"
        self.assertTrue(sample_path.is_file())
        sample_cfg = boss_init.parse_config_md(sample_path.read_bytes().decode("utf-8"))
        self.assertEqual(sample_cfg["schema_version"], 2)
        errs = boss_init.validate_config(sample_cfg, root=None)
        self.assertEqual(errs, [])
        self.assertEqual(sample_cfg["boss"]["priority"], "provider_order")
        self.assertEqual(sample_cfg["boss"]["retry_after_successful_tasks"], 5)
        self.assertIsNone(sample_cfg["workers"][0]["execution_evidence"])
        self.assertIsNotNone(sample_cfg["workers"][0]["catalog_evidence"])

    # --------------------------------------------------------------------------
    # Legacy v1 Support Tests
    # --------------------------------------------------------------------------
    def test_legacy_v1_validation_and_status(self):
        v1_cfg = make_valid_config_v1(self.root, state="enabled")
        errs = boss_init.validate_config(v1_cfg, self.root)
        self.assertEqual(errs, [])

        # Write v1 config and check get_status preserves legacy active status
        cfg_path = self.root / ".setting" / "config.md"
        write_config_md(cfg_path, v1_cfg)
        (self.root / ".setting" / "boss-orchestrator.md").write_bytes(b"# Policy")
        (self.root / "AGENTS.md").write_bytes(f"{boss_init.MARKER_BEGIN}\nblock\n{boss_init.MARKER_END}\n".encode("utf-8"))

        st = boss_init.get_status(self.root)
        self.assertEqual(st["status"], "active")
        self.assertEqual(st["state"], "enabled")
        self.assertEqual(st["schema_version"], 1)
        self.assertTrue(st["legacy"])
        self.assertIn("legacy", st.get("notice", "").lower())

    def test_plan_rejects_raw_v1_and_requires_v2(self):
        v1_cfg = make_valid_config_v1(self.root)
        raw_v1 = f"# Config\n\n```json\n{json.dumps(v1_cfg, indent=2)}\n```\n"
        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.make_plan(self.root, raw_v1)
        self.assertIn("schema_version 1 (legacy)", str(cm.exception))

    def test_migrate_command_detects_conflicts_and_requires_user_choices(self):
        v1_cfg = make_valid_config_v1(self.root)
        v2_draft, issues = boss_init.migrate_v1_to_v2(v1_cfg)
        self.assertIsNone(v2_draft)
        self.assertTrue(any("Provider 'opencode' has multiple enabled routes" in issue for issue in issues))

        # Supply user decision resolving conflict and setting order
        v2_draft, issues = boss_init.migrate_v1_to_v2(
            v1_cfg,
            selected_routes={"opencode": "route_1"},
            ordered_worker_ids=["worker-1"]
        )
        self.assertEqual(issues, [])
        self.assertIsNotNone(v2_draft)
        self.assertEqual(v2_draft["schema_version"], 2)
        self.assertEqual(v2_draft["boss"]["priority"], "provider_order")
        self.assertEqual(v2_draft["boss"]["retry_after_successful_tasks"], 5)
        self.assertNotIn("fallback_workers", v2_draft["boss"])

        # Check worker-1 is enabled, worker-2 is disabled alternative
        w1 = next(w for w in v2_draft["workers"] if w["id"] == "worker-1")
        w2 = next(w for w in v2_draft["workers"] if w["id"] == "worker-2")
        self.assertTrue(w1["enabled"])
        self.assertFalse(w2["enabled"])
        self.assertEqual(w2["disabled_reason"], "inactive provider route alternative")

    # --------------------------------------------------------------------------
    # Schema Version 2 Ordered Validation Tests
    # --------------------------------------------------------------------------
    def test_v2_multiple_enabled_routes_same_provider_rejected(self):
        cfg = make_valid_config_v2(self.root)
        # Attempt to enable 2 routes under the same provider_instance_id "inst_1"
        cfg["workers"][1]["provider_instance_id"] = "inst_1"
        cfg["workers"][1]["enabled"] = True
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("provider_instance_id 'inst_1' already has an enabled worker route" in e for e in errs))

    def test_v2_different_named_provider_instances_allowed(self):
        cfg = make_valid_config_v2(self.root)
        # inst_1 and inst_2 are distinct providerInstanceIds (e.g. Lason vs Nia)
        self.assertEqual(cfg["workers"][0]["provider_instance_id"], "inst_1")
        self.assertEqual(cfg["workers"][1]["provider_instance_id"], "inst_2")
        errs = boss_init.validate_config(cfg, self.root)
        self.assertEqual(errs, [])

    def test_v2_numeric_and_boolean_validations(self):
        cfg = make_valid_config_v2(self.root)
        for bad_rst in [True, False, 0, -5, "5", None]:
            cfg["boss"]["retry_after_successful_tasks"] = bad_rst
            errs = boss_init.validate_config(cfg, self.root)
            self.assertTrue(any("retry_after_successful_tasks must be a positive integer" in e for e in errs))

        for bad_npr in [True, False, 0, -2, "2", None]:
            cfg["boss"]["no_progress_rounds"] = bad_npr
            errs = boss_init.validate_config(cfg, self.root)
            self.assertTrue(any("no_progress_rounds must be a positive integer" in e for e in errs))

    def test_v2_priority_must_be_provider_order(self):
        cfg = make_valid_config_v2(self.root)
        cfg["boss"]["priority"] = "equal"
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("boss.priority must be 'provider_order'" in e for e in errs))

    def test_v2_fallback_workers_strictly_matches_or_omitted(self):
        cfg = make_valid_config_v2(self.root)
        # Omitted fallback_workers is valid
        self.assertNotIn("fallback_workers", cfg["boss"])
        self.assertEqual(boss_init.validate_config(cfg, self.root), [])

        # Strictly matching fallback_workers is accepted
        cfg["boss"]["fallback_workers"] = ["worker-1", "worker-2"]
        self.assertEqual(boss_init.validate_config(cfg, self.root), [])

        # Non-matching or competing fallback_workers rejected
        cfg["boss"]["fallback_workers"] = ["worker-2", "worker-1"]
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("fallback_workers in schema_version 2 is redundant" in e for e in errs))

    # --------------------------------------------------------------------------
    # Deterministic Pure SessionRouter State Machine Tests
    # --------------------------------------------------------------------------
    def test_router_order_determines_priority(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        router = SessionRouter(cfg)
        decision = router.get_route_decision(capacity_available=True)
        self.assertEqual(decision.action, "dispatch")
        self.assertEqual(decision.worker_id, "worker-1")
        self.assertEqual(decision.priority_rank, 1)

    def test_router_queues_when_capacity_full_no_spill(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        router = SessionRouter(cfg)
        # Priority 1 has full capacity -> must QUEUE, not spill to worker-2
        decision = router.get_route_decision(capacity_available=False)
        self.assertEqual(decision.action, "queue")
        self.assertEqual(decision.worker_id, "worker-1")
        self.assertIn("capacity full; queueing without spilling", decision.reason)

    def test_router_operational_error_advances_to_next_priority(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        router = SessionRouter(cfg)

        router.record_task_dispatch("task-1", "worker-1")
        router.record_operational_error("task-1", "connection timeout")

        self.assertEqual(router.providers["worker-1"].state, "operational_failed")
        # Next decision should advance to worker-2 (Priority 2)
        decision = router.get_route_decision(capacity_available=True)
        self.assertEqual(decision.action, "dispatch")
        self.assertEqual(decision.worker_id, "worker-2")
        self.assertEqual(decision.priority_rank, 2)

    def test_router_handoff_brief_contract(self):
        router = SessionRouter(make_valid_config_v2(self.root, state="enabled"))
        brief = HandoffBrief(
            goal_acceptance="Implement router tests",
            files_or_diff="tests/test_boss_init.py",
            completed_steps=["Drafted test cases"],
            partial_steps=["Running verification"],
            test_evidence_revision="git:main0548b97",
            outstanding_errors=[],
            cancellation_uncertain_effects="None",
            exact_next_action="Execute test runner",
        )
        saved = router.create_handoff(brief)
        self.assertEqual(saved.goal_acceptance, "Implement router tests")

        # Incomplete brief fails validation
        bad_brief = HandoffBrief(
            goal_acceptance="",
            files_or_diff="",
            completed_steps=[],
            partial_steps=[],
            test_evidence_revision="",
            outstanding_errors=[],
            cancellation_uncertain_effects="",
            exact_next_action="",
        )
        with self.assertRaises(boss_init.InitError):
            router.create_handoff(bad_brief)

    def test_router_quality_rounds_two_round_escalation(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        router = SessionRouter(cfg)

        # Dispatch task-q1 on worker-1
        router.record_task_dispatch("task-q1", "worker-1")

        # Round 1: no progress
        router.record_quality_round("task-q1", "worker-1", measurable_progress=False)
        self.assertEqual(router.providers["worker-1"].state, "healthy")
        decision = router.get_route_decision()
        self.assertEqual(decision.worker_id, "worker-1")

        # Round 2: no progress -> marks worker-1 quality_exhausted
        router.record_quality_round("task-q1", "worker-1", measurable_progress=False)
        self.assertEqual(router.providers["worker-1"].state, "quality_exhausted")

        # Decision advances to worker-2
        decision = router.get_route_decision()
        self.assertEqual(decision.worker_id, "worker-2")

        # Exhausting worker-2 leads to escalation
        router.record_task_dispatch("task-q2", "worker-2")
        router.record_quality_round("task-q2", "worker-2", measurable_progress=False)
        router.record_quality_round("task-q2", "worker-2", measurable_progress=False)
        self.assertEqual(router.providers["worker-2"].state, "quality_exhausted")

        decision = router.get_route_decision()
        self.assertEqual(decision.action, "escalate")

    def test_router_accepted_task_counting_and_recovery_trials(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        router = SessionRouter(cfg)

        # Worker 1 fails operationally
        router.record_task_dispatch("t0", "worker-1")
        router.record_operational_error("t0", "quota exceeded")

        # 1. Cancelled or incomplete tasks on worker-2 do NOT count
        router.record_task_dispatch("t-cancel", "worker-2")
        router.record_task_completion("t-cancel", "worker-2", outcome="cancelled", parent_accepted=False)
        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 0)

        # 2. Run success without parent acceptance does NOT count
        router.record_task_dispatch("t-noaccept", "worker-2")
        router.record_task_completion("t-noaccept", "worker-2", outcome="success", parent_accepted=False)
        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 0)

        # 3. 4 Accepted completions increment counter to 4 (not yet eligible for trial)
        for i in range(1, 5):
            tid = f"task-acc-{i}"
            router.record_task_dispatch(tid, "worker-2")
            router.record_task_completion(tid, "worker-2", outcome="success", parent_accepted=True)
            self.assertEqual(router.providers["worker-1"].success_count_since_fail, i)

        # Duplicate task completion is rejected by terminal registry (replay rejected)
        with self.assertRaises(boss_init.InitError):
            router.record_task_completion("task-acc-1", "worker-2", outcome="success", parent_accepted=True)
        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 4)

        decision = router.get_route_decision()
        self.assertEqual(decision.action, "dispatch")
        self.assertEqual(decision.worker_id, "worker-2")

        # 4. 5th Accepted completion triggers recovery trial eligibility on worker-1
        router.record_task_dispatch("task-acc-5", "worker-2")
        router.record_task_completion("task-acc-5", "worker-2", outcome="success", parent_accepted=True)
        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 5)

        trial_decision = router.get_route_decision()
        self.assertEqual(trial_decision.action, "recovery_trial")
        self.assertEqual(trial_decision.worker_id, "worker-1")
        self.assertTrue(trial_decision.is_recovery_trial)

        # Dispatch the recovery trial
        router.record_task_dispatch("trial-task-1", "worker-1", is_recovery_trial=True)

        # While trial is pending, no second trial is flooded
        subsequent_decision = router.get_route_decision()
        self.assertEqual(subsequent_decision.action, "dispatch")
        self.assertEqual(subsequent_decision.worker_id, "worker-2")

        # Trial fails: counter resets to 0, stays on worker-2
        router.record_task_completion("trial-task-1", "worker-1", outcome="operational_error", parent_accepted=False)
        self.assertEqual(router.providers["worker-1"].state, "operational_failed")
        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 0)

        # Need 5 new accepted tasks
        for i in range(6, 11):
            tid = f"task-acc-{i}"
            router.record_task_dispatch(tid, "worker-2")
            router.record_task_completion(tid, "worker-2", outcome="success", parent_accepted=True)

        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 5)
        trial_decision_2 = router.get_route_decision()
        self.assertEqual(trial_decision_2.action, "recovery_trial")
        self.assertEqual(trial_decision_2.worker_id, "worker-1")

        # Trial succeeds and is accepted: worker-1 restored to healthy
        router.record_task_dispatch("trial-task-2", "worker-1", is_recovery_trial=True)
        router.record_task_completion("trial-task-2", "worker-1", outcome="success", parent_accepted=True)
        self.assertEqual(router.providers["worker-1"].state, "healthy")
        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 0)

        # New dispatches go back to Priority 1
        new_decision = router.get_route_decision()
        self.assertEqual(new_decision.action, "dispatch")
        self.assertEqual(new_decision.worker_id, "worker-1")
        self.assertEqual(new_decision.priority_rank, 1)

    def test_router_session_reset(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        router = SessionRouter(cfg)

        router.record_task_dispatch("t1", "worker-1")
        router.record_operational_error("t1", "quota")
        self.assertEqual(router.providers["worker-1"].state, "operational_failed")

        router.reset_session()
        self.assertEqual(router.providers["worker-1"].state, "healthy")
        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 0)
        self.assertEqual(router.in_flight_tasks, {})
        self.assertEqual(router.accepted_task_ids, set())
        decision = router.get_route_decision()
        self.assertEqual(decision.worker_id, "worker-1")

    def test_router_multiple_failed_priorities_recovery_order(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        # Add a third enabled worker (worker-3)
        w3 = json.loads(json.dumps(cfg["workers"][0]))
        w3["id"] = "worker-3"
        w3["label"] = "Worker Three (Priority 3)"
        w3["provider_instance_id"] = "inst_3"
        w3["route_id"] = "route_3"
        cfg["workers"].append(w3)

        router = SessionRouter(cfg)
        self.assertEqual(len(router.providers), 3)

        # Worker 1 fails
        router.record_task_dispatch("m-1", "worker-1")
        router.record_operational_error("m-1", "worker-1 error")

        # Worker 2 also fails
        router.record_task_dispatch("m-2", "worker-2")
        router.record_operational_error("m-2", "worker-2 error")

        # Worker 3 is healthy and executes 5 accepted tasks
        for i in range(1, 6):
            tid = f"m-w3-task-{i}"
            router.record_task_dispatch(tid, "worker-3")
            router.record_task_completion(tid, "worker-3", outcome="success", parent_accepted=True)

        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 5)
        self.assertEqual(router.providers["worker-2"].success_count_since_fail, 5)

        # Both worker-1 and worker-2 are eligible for trial.
        # Worker 1 (Rank 1, highest priority) MUST be chosen first!
        trial_decision = router.get_route_decision()
        self.assertEqual(trial_decision.action, "recovery_trial")
        self.assertEqual(trial_decision.worker_id, "worker-1")
        self.assertEqual(trial_decision.priority_rank, 1)

        # Dispatch trial on worker-1; trial fails
        router.record_task_dispatch("trial-w1", "worker-1", is_recovery_trial=True)
        router.record_task_completion("trial-w1", "worker-1", outcome="operational_error", parent_accepted=False)
        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 0)
        self.assertEqual(router.providers["worker-2"].success_count_since_fail, 5)

        # Next decision now gives worker-2 (Rank 2) the recovery trial!
        trial_decision_2 = router.get_route_decision()
        self.assertEqual(trial_decision_2.action, "recovery_trial")
        self.assertEqual(trial_decision_2.worker_id, "worker-2")
        self.assertEqual(trial_decision_2.priority_rank, 2)


    # --------------------------------------------------------------------------
    # General Parsing, Atomic Writes, Rollback & Tamper Protection Tests
    # --------------------------------------------------------------------------
    def test_empty_evidence_cannot_activate(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        cfg["workers"][0]["execution_evidence"] = {}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("execution_evidence cannot be empty object" in e for e in errs))

        cfg = make_valid_config_v2(self.root, state="enabled")
        cfg["workers"][0]["execution_evidence"] = None
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("execution_evidence required when state is enabled" in e for e in errs))

        cfg = make_valid_config_v2(self.root, state="draft")
        cfg["workers"][0]["catalog_evidence"] = {}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("catalog_evidence cannot be empty object" in e for e in errs))

    def test_required_fields_invalid_and_malformed_types(self):
        cfg = make_valid_config_v2(self.root)
        cfg["workers"][0]["provider_instance_id"] = {"nested": "dict"}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("provider_instance_id must be non-empty string" in e for e in errs))

        cfg = make_valid_config_v2(self.root)
        del cfg["boss"]["priority"]
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("boss: missing key 'priority'" in e for e in errs))

    def test_unknown_nested_keys(self):
        cfg = make_valid_config_v2(self.root)
        cfg["scope"]["unknown_scope_key"] = "bad"
        cfg["scope"]["git"] = "not_a_bool"
        cfg["parent"]["unknown_parent_key"] = "bad"
        cfg["workers"][0]["model_claim"]["unknown_claim_key"] = "bad"
        cfg["workers"][0]["upstreams"]["unknown_upstream_key"] = "bad"
        cfg["workers"][0]["catalog_evidence"]["unknown_evidence_key"] = "bad"
        cfg["boss"]["unknown_boss_key"] = "bad"

        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("scope: unknown key 'unknown_scope_key'" in e for e in errs))
        self.assertTrue(any("scope.git must be boolean" in e for e in errs))
        self.assertTrue(any("parent: unknown key 'unknown_parent_key'" in e for e in errs))
        self.assertTrue(any("model_claim: unknown key 'unknown_claim_key'" in e for e in errs))
        self.assertTrue(any("upstreams: unknown key 'unknown_upstream_key'" in e for e in errs))
        self.assertTrue(any("catalog_evidence: unknown key 'unknown_evidence_key'" in e for e in errs))
        self.assertTrue(any("boss: unknown key 'unknown_boss_key'" in e for e in errs))

    def test_thinking_selection_mismatch(self):
        cfg = make_valid_config_v2(self.root)
        cfg["workers"][0]["thinking"] = {"mode": "default"}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("thinking mode 'default' is not allowed for enabled worker" in e for e in errs))

        cfg = make_valid_config_v2(self.root)
        cfg["workers"][0]["thinking"] = {
            "mode": "explicit",
            "option_key": "thinking_level",
            "selected": "ultra",
            "allowed_values": ["low", "medium", "high"],
        }
        cfg["workers"][0]["options"] = {"thinking_level": "ultra"}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("selected 'ultra' not in allowed_values" in e for e in errs))

        cfg = make_valid_config_v2(self.root)
        cfg["workers"][0]["thinking"] = {
            "mode": "explicit",
            "option_key": "thinking_level",
            "selected": "high",
            "allowed_values": ["low", "medium", "high"],
        }
        cfg["workers"][0]["options"] = {"thinking_level": "low"}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("does not match thinking.selected" in e for e in errs))

    def test_raw_crlf_and_bom_preservation(self):
        bom = b"\xef\xbb\xbf"
        pre_content = b"Header with CRLF line 1\r\nHeader line 2\r\n\r\n"
        existing_marker = (
            f"{boss_init.MARKER_BEGIN}\r\n"
            f"Old Boss Content\r\n"
            f"{boss_init.MARKER_END}\r\n"
        ).encode("utf-8")
        post_content = b"Trailing user notes line 1\r\nTrailing line 2\r\n"

        initial_bytes = bom + pre_content + existing_marker + post_content
        agents_file = self.root / "AGENTS.md"
        agents_file.write_bytes(initial_bytes)

        cfg = make_valid_config_v2(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        code, msg = boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertEqual(code, 0)

        updated_bytes = agents_file.read_bytes()
        self.assertTrue(updated_bytes.startswith(bom))
        self.assertIn(pre_content, updated_bytes)
        self.assertTrue(updated_bytes.endswith(post_content))
        self.assertNotIn(b"\r\r\n", updated_bytes)

    def test_stale_newline_change_detected(self):
        initial_agents = "Line 1\nLine 2\n"
        agents_file = self.root / "AGENTS.md"
        agents_file.write_bytes(initial_agents.encode("utf-8"))

        cfg = make_valid_config_v2(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        agents_file.write_bytes("Line 1\r\nLine 2\r\n".encode("utf-8"))

        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertIn("Stale plan: AGENTS.md before SHA256 mismatch", str(cm.exception))

    def test_tampered_plan_rejected(self):
        cfg = make_valid_config_v2(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        plan["files"][0]["content"] = "# Tampered Content!"
        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertIn("Plan tampering detected", str(cm.exception))

        plan2 = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        plan2["files"][0]["after_sha256"] = "0" * 64
        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.apply_plan(self.root, plan2, confirmed=True)
        self.assertIn("Plan tampering detected", str(cm.exception))

    def test_duplicate_plan_paths_rejected(self):
        cfg = make_valid_config_v2(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        plan["files"].append(plan["files"][0].copy())

        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertIn("Duplicate path 'AGENTS.md' in plan files", str(cm.exception))

    def test_cli_stdin_plan_apply_status_exit(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        cfg_json_str = f"# Config\n\n```json\n{json.dumps(cfg, indent=2)}\n```\n"

        # 1. CLI Plan via stdin (emits schema_version 2)
        res_plan = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "boss_init.py"), "plan", "--root", str(self.root), "--config", "-"],
            input=cfg_json_str,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_plan.returncode, 0, f"Plan failed: {res_plan.stderr}")
        plan_json = res_plan.stdout
        self.assertIn('"version": 2', plan_json)

        # 2. CLI Apply via stdin
        res_apply = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "boss_init.py"), "apply", "--root", str(self.root), "--plan", "-", "--confirmed"],
            input=plan_json,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_apply.returncode, 0, f"Apply failed: {res_apply.stderr}")

        # 3. CLI Idempotent apply returns exit code 2
        res_apply2 = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "boss_init.py"), "apply", "--root", str(self.root), "--plan", "-", "--confirmed"],
            input=plan_json,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_apply2.returncode, 2)
        self.assertIn("already in planned state", res_apply2.stdout)

        # 4. CLI Status when enabled returns exit code 0 and status active
        res_st = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "boss_init.py"), "status", "--root", str(self.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_st.returncode, 0)
        st_data = json.loads(res_st.stdout)
        self.assertEqual(st_data["status"], "active")
        self.assertEqual(st_data["state"], "enabled")
        self.assertEqual(st_data["schema_version"], 2)

    def test_draft_config_not_activated(self):
        cfg = make_valid_config_v2(self.root, state="draft")
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        boss_init.apply_plan(self.root, plan, confirmed=True)

        st = boss_init.get_status(self.root)
        self.assertEqual(st["status"], "inactive")
        self.assertEqual(st["state"], "draft")

        res_st = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "boss_init.py"), "status", "--root", str(self.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_st.returncode, 1)

    def test_missing_runtime_status_invalid(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)
        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        boss_init.apply_plan(self.root, plan, confirmed=True)

        (self.root / ".setting/boss-orchestrator.md").unlink()
        st = boss_init.get_status(self.root)
        self.assertEqual(st["status"], "invalid")
        self.assertTrue(any("runtime policy missing" in e for e in st["errors"]))

    def test_agents_override_cancels_no_writes(self):
        (self.root / "AGENTS.override.md").write_bytes(b"# Conflicting override instructions")
        cfg = make_valid_config_v2(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        self.assertIn("AGENTS.override.md is present and non-empty", str(cm.exception))
        self.assertFalse((self.root / ".setting").exists())

    def test_claude_md_coexistence(self):
        (self.root / "CLAUDE.md").write_bytes(b"# Project Claude Instructions")
        cfg = make_valid_config_v2(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        code, _ = boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertEqual(code, 0)
        self.assertEqual((self.root / "CLAUDE.md").read_bytes(), b"# Project Claude Instructions")

    def test_preserve_user_prose_in_config(self):
        cfg = make_valid_config_v2(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        boss_init.apply_plan(self.root, plan, confirmed=True)

        setting_cfg = self.root / ".setting/config.md"
        custom_content = (
            "# Custom Team Config Notes\n\n"
            "Important team routing comments here.\n\n"
            "```json\n"
            + json.dumps(cfg, indent=2)
            + "\n```\n\n"
            "Footer team operations notes.\n"
        )
        setting_cfg.write_bytes(custom_content.encode("utf-8"))

        cfg["workers"][0]["label"] = "Updated Worker Label"
        write_config_md(cfg_path, cfg)
        plan2 = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        boss_init.apply_plan(self.root, plan2, confirmed=True)

        updated_text = setting_cfg.read_bytes().decode("utf-8")
        self.assertIn("# Custom Team Config Notes", updated_text)
        self.assertIn("Important team routing comments here.", updated_text)
        self.assertIn("Footer team operations notes.", updated_text)
        self.assertIn("Updated Worker Label", updated_text)

    def test_preserve_matt_skills_block(self):
        initial_agents = (
            "# My Existing Workspace\n\n"
            "## Agent skills\n"
            "- [research](file:///path/to/research/SKILL.md)\n"
            "- [code-review](file:///path/to/code-review/SKILL.md)\n\n"
            "Footer notes from developer.\n"
        )
        agents_file = self.root / "AGENTS.md"
        agents_file.write_bytes(initial_agents.encode("utf-8"))

        cfg = make_valid_config_v2(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        boss_init.apply_plan(self.root, plan, confirmed=True)

        updated = agents_file.read_bytes().decode("utf-8")
        self.assertTrue(updated.startswith(initial_agents))
        self.assertIn("## Agent skills", updated)

    def test_reparse_symlink_junction_rejection(self):
        with self.assertRaises(boss_init.InitError):
            boss_init._safe_resolve(self.root, "../escaped.txt")

        link_path = self.root / ".setting"
        try:
            outside_dir = tempfile.mkdtemp()
            os.symlink(outside_dir, link_path)
            with self.assertRaises(boss_init.InitError) as cm:
                boss_init._safe_resolve(self.root, ".setting/config.md")
            self.assertIn("Symlink, junction, or reparse point rejected", str(cm.exception))
        except (OSError, NotImplementedError):
            pass
        finally:
            shutil.rmtree(outside_dir, ignore_errors=True)

    def test_simulated_write_failure_rollback(self):
        orig_agents = b"# Original AGENTS content\n"
        agents_file = self.root / "AGENTS.md"
        agents_file.write_bytes(orig_agents)

        cfg = make_valid_config_v2(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)
        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))

        orig_replace = os.replace
        call_count = [0]

        def failing_replace(src, dst):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError("Simulated disk write failure during replace")
            orig_replace(src, dst)

        os.replace = failing_replace
        try:
            with self.assertRaises(boss_init.InitError) as cm:
                boss_init.apply_plan(self.root, plan, confirmed=True)
            self.assertIn("Write failure, rolled back", str(cm.exception))
        finally:
            os.replace = orig_replace

        self.assertEqual(agents_file.read_bytes(), orig_agents)
        tmp_files = list(self.root.rglob(".tmp_*"))
        self.assertEqual(tmp_files, [])

    def test_router_only_one_global_pending_recovery_trial(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        w3 = json.loads(json.dumps(cfg["workers"][0]))
        w3["id"] = "worker-3"
        w3["label"] = "Worker Three (Priority 3)"
        w3["provider_instance_id"] = "inst_3"
        w3["route_id"] = "route_3"
        cfg["workers"].append(w3)

        router = SessionRouter(cfg)
        self.assertEqual(len(router.providers), 3)

        # Worker 1 and Worker 2 fail
        router.record_task_dispatch("m1", "worker-1")
        router.record_operational_error("m1", "err1")
        router.record_task_dispatch("m2", "worker-2")
        router.record_operational_error("m2", "err2")

        # Worker 3 executes 5 accepted tasks
        for i in range(1, 6):
            tid = f"m3-task-{i}"
            router.record_task_dispatch(tid, "worker-3")
            router.record_task_completion(tid, "worker-3", outcome="success", parent_accepted=True)

        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 5)
        self.assertEqual(router.providers["worker-2"].success_count_since_fail, 5)

        # Decision selects worker-1 (highest priority failed provider) for recovery trial
        decision1 = router.get_route_decision()
        self.assertEqual(decision1.action, "recovery_trial")
        self.assertEqual(decision1.worker_id, "worker-1")

        # Dispatch recovery trial on worker-1
        router.record_task_dispatch("trial-w1", "worker-1", is_recovery_trial=True)
        self.assertEqual(router.providers["worker-1"].active_recovery_trial_task_id, "trial-w1")

        # Invariant: While trial on worker-1 is pending/in-flight, no second recovery trial is permitted
        # Even though worker-2 is eligible, router MUST NOT return recovery_trial for worker-2
        decision2 = router.get_route_decision(capacity_available=True)
        self.assertEqual(decision2.action, "dispatch")
        self.assertEqual(decision2.worker_id, "worker-3")

        # Attempting to dispatch a second concurrent recovery trial raises InitError
        with self.assertRaises(boss_init.InitError) as cm:
            router.record_task_dispatch("trial-w2", "worker-2", is_recovery_trial=True)
        self.assertIn("Only one global recovery trial", str(cm.exception))

        # Trial on worker-1 fails
        router.record_task_completion("trial-w1", "worker-1", outcome="operational_error", parent_accepted=False)
        self.assertIsNone(router.providers["worker-1"].active_recovery_trial_task_id)
        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 0)

        # Now that worker-1's trial settled, worker-2 is granted the recovery trial
        decision3 = router.get_route_decision()
        self.assertEqual(decision3.action, "recovery_trial")
        self.assertEqual(decision3.worker_id, "worker-2")

    def test_router_quality_exhaustion_clears_recovery_and_resets_counter(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        router = SessionRouter(cfg)

        # Worker 1 fails operationally
        router.record_task_dispatch("t-init", "worker-1")
        router.record_operational_error("t-init", "auth failure")

        # Worker 2 does 5 accepted tasks
        for i in range(1, 6):
            tid = f"t-w2-{i}"
            router.record_task_dispatch(tid, "worker-2")
            router.record_task_completion(tid, "worker-2", outcome="success", parent_accepted=True)

        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 5)

        # Dispatch recovery trial on worker-1
        router.record_task_dispatch("trial-task", "worker-1", is_recovery_trial=True)
        self.assertEqual(router.providers["worker-1"].active_recovery_trial_task_id, "trial-task")

        # Quality rounds on trial task: 2 consecutive no-progress rounds
        router.record_quality_round("trial-task", "worker-1", measurable_progress=False)
        self.assertEqual(router.providers["worker-1"].active_recovery_trial_task_id, "trial-task")
        router.record_quality_round("trial-task", "worker-1", measurable_progress=False)

        # Quality exhaustion: settles/clears recovery and resets counter
        self.assertEqual(router.providers["worker-1"].state, "quality_exhausted")
        self.assertIsNone(router.providers["worker-1"].active_recovery_trial_task_id)
        self.assertEqual(router.providers["worker-1"].success_count_since_fail, 0)

        # Next decision cleanly routes to worker-2
        next_dec = router.get_route_decision()
        self.assertEqual(next_dec.action, "dispatch")
        self.assertEqual(next_dec.worker_id, "worker-2")

    def test_router_in_flight_identity_worker_mismatch_and_terminal_registry(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        router = SessionRouter(cfg)

        # 1. Unknown task completion rejected
        with self.assertRaises(boss_init.InitError) as cm:
            router.record_task_completion("ghost-task", "worker-1", outcome="success", parent_accepted=True)
        self.assertIn("unknown task completion rejected", str(cm.exception).lower())

        # Unknown task operational error rejected
        with self.assertRaises(boss_init.InitError) as cm:
            router.record_operational_error("ghost-task", "err")
        self.assertIn("not in-flight", str(cm.exception))

        # 2. Worker mismatch rejected before mutation
        router.record_task_dispatch("task-val", "worker-1")
        with self.assertRaises(boss_init.InitError) as cm:
            router.record_task_completion("task-val", "worker-2", outcome="success", parent_accepted=True)
        self.assertIn("Worker mismatch", str(cm.exception))

        # Verify task is still in-flight on worker-1 (not mutated)
        self.assertIn("task-val", router.in_flight_tasks)
        self.assertEqual(router.in_flight_tasks["task-val"]["worker_id"], "worker-1")

        # Operational error worker mismatch rejected before mutation
        with self.assertRaises(boss_init.InitError) as cm:
            router.record_operational_error("task-val", "err", worker_id="worker-2")
        self.assertIn("Worker mismatch", str(cm.exception))
        self.assertIn("task-val", router.in_flight_tasks)

        # 3. Valid completion transitions to terminal registry
        router.record_task_completion("task-val", "worker-1", outcome="success", parent_accepted=True)
        self.assertNotIn("task-val", router.in_flight_tasks)
        self.assertIn("task-val", router.terminal_tasks)

        # 4. Terminal registry prevents all replay
        with self.assertRaises(boss_init.InitError) as cm:
            router.record_task_completion("task-val", "worker-1", outcome="success", parent_accepted=True)
        self.assertIn("replay rejected", str(cm.exception))

        with self.assertRaises(boss_init.InitError) as cm:
            router.record_operational_error("task-val", "err")
        self.assertIn("replay rejected", str(cm.exception))

    def test_router_quality_rounds_keyed_per_task(self):
        cfg = make_valid_config_v2(self.root, state="enabled")
        router = SessionRouter(cfg)

        router.record_task_dispatch("task-A", "worker-1")
        router.record_task_dispatch("task-B", "worker-1")

        # Worker mismatch rejected
        with self.assertRaises(boss_init.InitError) as cm:
            router.record_quality_round("task-A", "worker-2", measurable_progress=False)
        self.assertIn("Worker mismatch", str(cm.exception))

        # Unknown task rejected
        with self.assertRaises(boss_init.InitError) as cm:
            router.record_quality_round("task-ghost", "worker-1", measurable_progress=False)
        self.assertIn("not in-flight", str(cm.exception))

        # Keyed per task: task-A has 1 no-progress round, task-B has progress
        router.record_quality_round("task-A", "worker-1", measurable_progress=False)
        self.assertEqual(router.consecutive_no_progress["task-A"], 1)

        router.record_quality_round("task-B", "worker-1", measurable_progress=True)
        self.assertEqual(router.consecutive_no_progress["task-B"], 0)
        self.assertEqual(router.providers["worker-1"].state, "healthy")

        # Second no-progress round on task-A triggers quality exhaustion on worker-1
        router.record_quality_round("task-A", "worker-1", measurable_progress=False)
        self.assertEqual(router.providers["worker-1"].state, "quality_exhausted")

        # Complete task-B (terminal)
        router.record_task_completion("task-B", "worker-1", outcome="cancelled", parent_accepted=False)
        self.assertIn("task-B", router.terminal_tasks)

        # Quality round on terminated task rejected
        with self.assertRaises(boss_init.InitError) as cm:
            router.record_quality_round("task-B", "worker-1", measurable_progress=True)
        self.assertIn("terminal state", str(cm.exception))

    def test_handoff_brief_strict_field_and_type_validation(self):
        router = SessionRouter(make_valid_config_v2(self.root, state="enabled"))

        valid_brief = HandoffBrief(
            goal_acceptance="Complete feature",
            files_or_diff="file.py",
            completed_steps=["Step 1"],
            partial_steps=["Step 2"],
            test_evidence_revision="git:abc1234",
            outstanding_errors=[],
            cancellation_uncertain_effects="No remote side effects",
            exact_next_action="Run tests",
        )
        self.assertEqual(valid_brief.validate(), [])

        # Missing cancellation uncertainty
        b_no_cancel = HandoffBrief(
            goal_acceptance="Goal",
            files_or_diff="file.py",
            completed_steps=[],
            partial_steps=[],
            test_evidence_revision="rev1",
            outstanding_errors=[],
            cancellation_uncertain_effects="",
            exact_next_action="Action",
        )
        errs = b_no_cancel.validate()
        self.assertTrue(any("cancellation_uncertain_effects" in e for e in errs))
        with self.assertRaises(boss_init.InitError):
            router.create_handoff(b_no_cancel)

        # Non-string cancellation uncertainty
        b_type_cancel = HandoffBrief(
            goal_acceptance="Goal",
            files_or_diff="file.py",
            completed_steps=[],
            partial_steps=[],
            test_evidence_revision="rev1",
            outstanding_errors=[],
            cancellation_uncertain_effects={"uncertain": True},  # type: ignore
            exact_next_action="Action",
        )
        errs = b_type_cancel.validate()
        self.assertTrue(any("cancellation_uncertain_effects" in e for e in errs))

        # List fields containing non-strings
        b_bad_list = HandoffBrief(
            goal_acceptance="Goal",
            files_or_diff="file.py",
            completed_steps=[123],  # type: ignore
            partial_steps=["ok"],
            test_evidence_revision="rev1",
            outstanding_errors=[],
            cancellation_uncertain_effects="None",
            exact_next_action="Action",
        )
        errs = b_bad_list.validate()
        self.assertTrue(any("completed_steps elements must be non-empty strings" in e for e in errs))

    def test_strict_schema_version_int_type_rejection(self):
        cfg = make_valid_config_v2(self.root)

        # schema_version = True (bool)
        cfg_bool = json.loads(json.dumps(cfg))
        cfg_bool["schema_version"] = True
        errs = boss_init.validate_config(cfg_bool)
        self.assertTrue(any("schema_version must be an integer" in e for e in errs))

        # schema_version = 2.0 (float)
        cfg_float = json.loads(json.dumps(cfg))
        cfg_float["schema_version"] = 2.0
        errs = boss_init.validate_config(cfg_float)
        self.assertTrue(any("schema_version must be an integer" in e for e in errs))

        # schema_version = "2" (string)
        cfg_str = json.loads(json.dumps(cfg))
        cfg_str["schema_version"] = "2"
        errs = boss_init.validate_config(cfg_str)
        self.assertTrue(any("schema_version must be an integer" in e for e in errs))

        # make_plan rejects bool and float
        cfg_path = self.root / "config_bool.md"
        write_config_md(cfg_path, cfg_bool)
        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        self.assertIn("schema_version must be an integer", str(cm.exception))

        # apply_plan rejects bool version
        plan = {
            "version": True,
            "root": str(self.root),
            "config": cfg,
            "files": []
        }
        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertIn("Plan version mismatch", str(cm.exception))

        # migrate rejects bool and float schema_version
        v1_cfg = make_valid_config_v1(self.root)
        v1_bool = json.loads(json.dumps(v1_cfg))
        v1_bool["schema_version"] = True
        draft, issues = boss_init.migrate_v1_to_v2(v1_bool)
        self.assertIsNone(draft)
        self.assertTrue(any("schema_version must be integer 1" in i for i in issues))

    def test_migration_duplicate_order_and_draft_validation(self):
        v1_cfg = make_valid_config_v1(self.root)
        w2 = json.loads(json.dumps(v1_cfg["workers"][0]))
        w2["id"] = "worker-1-alt"
        w2["route_id"] = "route-alt"
        v1_cfg["workers"].append(w2)

        # 1. Duplicate worker in --order list is rejected
        draft, issues = boss_init.migrate_v1_to_v2(
            v1_cfg,
            selected_routes={"opencode": "route_1"},
            ordered_worker_ids=["worker-1", "worker-1"],
        )
        self.assertIsNone(draft)
        self.assertTrue(any("Duplicate worker id" in i for i in issues))

        # 2. Emitted draft passes validation
        draft_ok, issues_ok = boss_init.migrate_v1_to_v2(
            v1_cfg,
            selected_routes={"opencode": "route_1"},
            ordered_worker_ids=["worker-1"],
        )
        self.assertEqual(issues_ok, [])
        self.assertIsNotNone(draft_ok)
        self.assertEqual(boss_init.validate_config_v2(draft_ok), [])


if __name__ == "__main__":
    unittest.main()
