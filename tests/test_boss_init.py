#!/usr/bin/env python3
"""Comprehensive stdlib unittest test suite for boss-orchestrator-init."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "boss-orchestrator-init" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import boss_init


def make_valid_config(root_path: Path, state: str = "draft") -> dict:
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
                "id": "worker-disabled",
                "label": "Disabled Worker",
                "enabled": False,
                "disabled_reason": "unresolved exact model route",
                "provider_instance_id": "inst_2",
                "driver_kind": "driver_2",
                "route_id": "route_unresolved",
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
            "priority": "equal",
            "reliability_memory": "session",
            "parallel_scopes": "disjoint_only",
            "quality_feedback": "first",
            "no_progress_rounds": 2,
            "after_change": "escalate",
            "fallback_workers": ["worker-1"],
        },
        "confirmation": {"approved_at": "2026-11-06"} if state == "enabled" else None,
    }


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
        # Validate against dummy root since root is generic in sample
        errs = boss_init.validate_config(sample_cfg, root=None)
        self.assertEqual(errs, [])
        # Sample draft should have generic catalog evidence and null execution evidence
        self.assertIsNone(sample_cfg["workers"][0]["execution_evidence"])
        self.assertIsNotNone(sample_cfg["workers"][0]["catalog_evidence"])

    def test_empty_evidence_cannot_activate(self):
        # 1. Enabled state with empty {} execution_evidence
        cfg = make_valid_config(self.root, state="enabled")
        cfg["workers"][0]["execution_evidence"] = {}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("execution_evidence cannot be empty object" in e for e in errs))

        # 2. Enabled state with None execution_evidence
        cfg = make_valid_config(self.root, state="enabled")
        cfg["workers"][0]["execution_evidence"] = None
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("execution_evidence required when state is enabled" in e for e in errs))

        # 3. Enabled worker with empty {} catalog_evidence
        cfg = make_valid_config(self.root, state="draft")
        cfg["workers"][0]["catalog_evidence"] = {}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("catalog_evidence cannot be empty object" in e for e in errs))

    def test_required_fields_invalid_and_malformed_types(self):
        # Malformed provider_instance_id as dict (should NOT raise TypeError: unhashable type)
        cfg = make_valid_config(self.root)
        cfg["workers"][0]["provider_instance_id"] = {"nested": "dict"}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("provider_instance_id must be non-empty string" in e for e in errs))

        # Missing required fields in boss
        cfg = make_valid_config(self.root)
        del cfg["boss"]["priority"]
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("boss: missing key 'priority'" in e for e in errs))

        # Missing required field in scope
        cfg = make_valid_config(self.root)
        del cfg["scope"]["git"]
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("scope: missing key 'git'" in e for e in errs))

    def test_unknown_nested_keys(self):
        cfg = make_valid_config(self.root)
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
        # 1. Default mode disallowed for enabled worker
        cfg = make_valid_config(self.root)
        cfg["workers"][0]["thinking"] = {"mode": "default"}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("thinking mode 'default' is not allowed for enabled worker" in e for e in errs))

        # 2. Selected not in allowed_values
        cfg = make_valid_config(self.root)
        cfg["workers"][0]["thinking"] = {
            "mode": "explicit",
            "option_key": "thinking_level",
            "selected": "ultra",
            "allowed_values": ["low", "medium", "high"],
        }
        cfg["workers"][0]["options"] = {"thinking_level": "ultra"}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("selected 'ultra' not in allowed_values" in e for e in errs))

        # 3. Mismatch between thinking.selected and options[option_key]
        cfg = make_valid_config(self.root)
        cfg["workers"][0]["thinking"] = {
            "mode": "explicit",
            "option_key": "thinking_level",
            "selected": "high",
            "allowed_values": ["low", "medium", "high"],
        }
        cfg["workers"][0]["options"] = {"thinking_level": "low"}
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("does not match thinking.selected" in e for e in errs))

    def test_no_progress_rounds_invalid(self):
        for bad_val in [True, False, 0, -1, "2", None]:
            cfg = make_valid_config(self.root)
            cfg["boss"]["no_progress_rounds"] = bad_val
            errs = boss_init.validate_config(cfg, self.root)
            self.assertTrue(any("no_progress_rounds must be a positive integer" in e for e in errs))

        # Positive int 2 is valid
        cfg = make_valid_config(self.root)
        cfg["boss"]["no_progress_rounds"] = 2
        errs = boss_init.validate_config(cfg, self.root)
        self.assertEqual(errs, [])

    def test_all_equal_fallback_unordered(self):
        # Disabled worker in fallback_workers rejected
        cfg = make_valid_config(self.root)
        cfg["boss"]["fallback_workers"] = ["worker-disabled"]
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("not an enabled worker" in e for e in errs))

        # Duplicate worker id in fallback_workers rejected
        cfg = make_valid_config(self.root)
        cfg["boss"]["fallback_workers"] = ["worker-1", "worker-1"]
        errs = boss_init.validate_config(cfg, self.root)
        self.assertTrue(any("duplicate worker id 'worker-1'" in e for e in errs))

        # Valid unordered enabled workers accepted
        cfg = make_valid_config(self.root)
        cfg["boss"]["fallback_workers"] = ["worker-1"]
        self.assertEqual(boss_init.validate_config(cfg, self.root), [])

    def test_raw_crlf_and_bom_preservation(self):
        # File with UTF-8 BOM, CRLF, and trailing text after marker
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

        cfg = make_valid_config(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        code, msg = boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertEqual(code, 0)

        updated_bytes = agents_file.read_bytes()
        # Verify BOM preserved
        self.assertTrue(updated_bytes.startswith(bom))
        # Verify CRLF before marker preserved byte-for-byte
        self.assertIn(pre_content, updated_bytes)
        # Verify trailing content preserved byte-for-byte
        self.assertTrue(updated_bytes.endswith(post_content))
        # Verify no rogue \r\r\n
        self.assertNotIn(b"\r\r\n", updated_bytes)

    def test_stale_newline_change_detected(self):
        initial_agents = "Line 1\nLine 2\n"
        agents_file = self.root / "AGENTS.md"
        agents_file.write_bytes(initial_agents.encode("utf-8"))

        cfg = make_valid_config(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))

        # Alter newline style on disk from \n to \r\n
        agents_file.write_bytes("Line 1\r\nLine 2\r\n".encode("utf-8"))

        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertIn("Stale plan: AGENTS.md before SHA256 mismatch", str(cm.exception))

    def test_tampered_plan_rejected(self):
        cfg = make_valid_config(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))

        # 1. Tamper with file content
        plan["files"][0]["content"] = "# Tampered Content!"
        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertIn("Plan tampering detected", str(cm.exception))

        # 2. Tamper with after_sha256
        plan2 = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        plan2["files"][0]["after_sha256"] = "0" * 64
        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.apply_plan(self.root, plan2, confirmed=True)
        self.assertIn("Plan tampering detected", str(cm.exception))

    def test_duplicate_plan_paths_rejected(self):
        cfg = make_valid_config(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        # Duplicate AGENTS.md entry
        plan["files"].append(plan["files"][0].copy())

        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertIn("Duplicate path 'AGENTS.md' in plan files", str(cm.exception))

    def test_cli_stdin_plan_apply_status_exit(self):
        cfg = make_valid_config(self.root, state="enabled")
        cfg_json_str = f"# Config\n\n```json\n{json.dumps(cfg, indent=2)}\n```\n"

        # 1. CLI Plan via stdin
        res_plan = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "boss_init.py"), "plan", "--root", str(self.root), "--config", "-"],
            input=cfg_json_str,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_plan.returncode, 0, f"Plan failed: {res_plan.stderr}")
        plan_json = res_plan.stdout
        self.assertIn('"version": 1', plan_json)

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

    def test_draft_config_not_activated(self):
        cfg = make_valid_config(self.root, state="draft")
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        boss_init.apply_plan(self.root, plan, confirmed=True)

        st = boss_init.get_status(self.root)
        self.assertEqual(st["status"], "inactive")
        self.assertEqual(st["state"], "draft")

        # AGENTS.md explicit state==enabled check
        agents_content = (self.root / "AGENTS.md").read_bytes().decode("utf-8")
        self.assertIn("`state` is not `enabled`, workspace orchestration is\ninactive", agents_content)

        # CLI status on draft exits with 1 (inactive)
        res_st = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "boss_init.py"), "status", "--root", str(self.root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_st.returncode, 1)

    def test_missing_runtime_status_invalid(self):
        cfg = make_valid_config(self.root, state="enabled")
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)
        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        boss_init.apply_plan(self.root, plan, confirmed=True)

        # Remove runtime policy
        (self.root / ".setting/boss-orchestrator.md").unlink()
        st = boss_init.get_status(self.root)
        self.assertEqual(st["status"], "invalid")
        self.assertTrue(any("runtime policy missing" in e for e in st["errors"]))

    def test_agents_override_cancels_no_writes(self):
        # Create non-empty AGENTS.override.md
        (self.root / "AGENTS.override.md").write_bytes(b"# Conflicting override instructions")

        cfg = make_valid_config(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        with self.assertRaises(boss_init.InitError) as cm:
            boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        self.assertIn("AGENTS.override.md is present and non-empty", str(cm.exception))
        self.assertFalse((self.root / ".setting").exists())

    def test_claude_md_coexistence(self):
        # CLAUDE.md present should NOT block planning or application
        (self.root / "CLAUDE.md").write_bytes(b"# Project Claude Instructions")

        cfg = make_valid_config(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        code, _ = boss_init.apply_plan(self.root, plan, confirmed=True)
        self.assertEqual(code, 0)
        # Ensure CLAUDE.md is completely untouched
        self.assertEqual((self.root / "CLAUDE.md").read_bytes(), b"# Project Claude Instructions")

    def test_preserve_user_prose_in_config(self):
        cfg = make_valid_config(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        boss_init.apply_plan(self.root, plan, confirmed=True)

        # Add custom user notes outside json fence in .setting/config.md
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

        # Generate a new plan with an updated worker label
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

        cfg = make_valid_config(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)

        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))
        boss_init.apply_plan(self.root, plan, confirmed=True)

        updated = agents_file.read_bytes().decode("utf-8")
        self.assertTrue(updated.startswith(initial_agents))
        self.assertIn("## Agent skills", updated)

    def test_reparse_symlink_junction_rejection(self):
        # Traversal escaping root
        with self.assertRaises(boss_init.InitError):
            boss_init._safe_resolve(self.root, "../escaped.txt")

        # Symlink in root if supported
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
        # Write initial AGENTS.md
        orig_agents = b"# Original AGENTS content\n"
        agents_file = self.root / "AGENTS.md"
        agents_file.write_bytes(orig_agents)

        cfg = make_valid_config(self.root)
        cfg_path = self.root / "config.md"
        write_config_md(cfg_path, cfg)
        plan = boss_init.make_plan(self.root, cfg_path.read_bytes().decode("utf-8"))

        # Monkeypatch os.replace to fail on second file
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

        # Verify rollback restored exact original AGENTS.md
        self.assertEqual(agents_file.read_bytes(), orig_agents)
        # Verify no leftover .tmp_* files
        tmp_files = list(self.root.rglob(".tmp_*"))
        self.assertEqual(tmp_files, [])


if __name__ == "__main__":
    unittest.main()
