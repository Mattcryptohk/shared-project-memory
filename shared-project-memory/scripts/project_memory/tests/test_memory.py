"""測試持久化、並行、worktree、接手同非破壞式安裝。"""

import concurrent.futures
import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from project_memory.bootstrap import initialize
from project_memory.hooks import run_hook
from project_memory.install import install_user
from project_memory.io import MemoryError, atomic_json, now, read_json
from project_memory.registry import doctor, git_facts, resolve
from project_memory.store import begin, checkpoint, context, events, rebuild, session_path, snapshot

LAUNCHER = Path(__file__).resolve().parents[2] / "memoryctl"


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shared memory ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "Project with spaces"
        self.root.mkdir()
        self.bindings = Path(self.temp.name) / "bindings.json"
        self.project = initialize(self.root, self.bindings, "test.workspace", "test.project")

    def event(self, ident="checkpoint", provider="codex", **kwargs):
        return {"schema_version": 1, "checkpoint_id": ident, "project_id": "test.project",
                "workspace_id": "test.workspace", "provider": provider, "session_id": "session-" + provider,
                "created_at": now(), "details_markdown": "完成文件檢查；未修改 live runtime。", **kwargs}

    def cli_checkpoint(self, event, repo=None):
        return subprocess.run([sys.executable, str(LAUNCHER), "--binding-file", str(self.bindings),
                               "checkpoint", "--repo", str(repo or self.root), "--input", "-"],
                              input=json.dumps(event), text=True, capture_output=True, timeout=20)

    def test_duplicate_is_idempotent_and_changed_payload_rejected(self):
        event = self.event()
        first = checkpoint(self.project, event)
        pointer = read_json(self.project.directory / "CURRENT.json")
        self.assertEqual(first, checkpoint(self.project, event))
        self.assertEqual(pointer, read_json(self.project.directory / "CURRENT.json"))
        changed = {**event, "details_markdown": "不同內容"}
        with self.assertRaises(MemoryError):
            checkpoint(self.project, changed)
        self.assertEqual(len(events(self.project)), 2)

    def test_parallel_writers_retain_every_distinct_task(self):
        drafts = [self.event(f"parallel-{i}", provider="claude" if i % 2 else "codex",
                   task_updates=[{"id": f"task-{i}", "title": f"任務 {i}", "status": "ready"}],
                   base_entity_revisions={f"task:task-{i}": 0}) for i in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outputs = list(pool.map(self.cli_checkpoint, drafts))
        self.assertTrue(all(r.returncode == 0 for r in outputs), [r.stderr for r in outputs])
        self.assertEqual(len(events(self.project)), 9)
        self.assertEqual(len([k for k in snapshot(self.project)["entities"] if k.startswith("task:")]), 8)

    def test_concurrent_same_task_conflict_and_explicit_resolution(self):
        checkpoint(self.project, self.event("create", task_updates=[{"id": "task", "status": "ready"}],
                                          base_entity_revisions={"task:task": 0}))
        drafts = [self.event(provider, provider=provider, task_updates=[{"id": "task", "status": "in_progress"}],
                            base_entity_revisions={"task:task": 1}) for provider in ["claude", "codex"]]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.cli_checkpoint, drafts))
        self.assertEqual(sorted(r.returncode for r in results), [0, 2])
        current = snapshot(self.project)
        conflict = current["conflicts"][0]
        checkpoint(self.project, self.event("resolve", task_updates=[{"id": "task", "status": "ready"}],
                   base_entity_revisions={"task:task": 2},
                   resolves_conflicts=[{"entity": "task:task", "checkpoint_id": conflict["checkpoint_id"]}]))
        self.assertEqual(snapshot(self.project)["conflicts"][0]["resolved_by"], "resolve")
        self.assertEqual(snapshot(self.project)["entities"]["task:task"]["revision"], 3)

    def test_crash_keeps_old_snapshot_and_rebuild_replays_saved_event(self):
        original = snapshot(self.project)
        from project_memory import store
        original_write = store.atomic_json
        def failing_write(path, data):
            if Path(path).name == "CURRENT.json":
                raise OSError("模擬發布前 crash")
            return original_write(path, data)
        with patch.object(store, "atomic_json", side_effect=failing_write):
            with self.assertRaises(OSError):
                checkpoint(self.project, self.event("crash"))
        self.assertEqual(snapshot(self.project), original)
        self.assertEqual(len(events(self.project)), 2)
        rebuild(self.project)
        self.assertEqual(snapshot(self.project)["sequence"], 2)

    def test_empty_semantic_and_bad_state_are_rejected_before_persistence(self):
        for event in [self.event("empty", details_markdown=""),
                      self.event("bad", state_update={"objective": 100}, base_entity_revisions={"state": 1}),
                      self.event("unsafe", checkpoint_id="../escape")]:
            with self.assertRaises(MemoryError):
                checkpoint(self.project, event)
        self.assertEqual(len(events(self.project)), 1)

    def test_verified_requires_successful_evidence(self):
        event = self.event(task_updates=[{"id": "task", "status": "ready", "verification": "verified"}],
                           base_entity_revisions={"task:task": 0}, checks=[{"command": "false", "exit_code": 1}])
        with self.assertRaises(MemoryError):
            checkpoint(self.project, event)
        event["checks"][0]["exit_code"] = 0
        checkpoint(self.project, event)

    def test_task_claim_blocks_another_owner_and_releases_on_done(self):
        begin(self.project, "codex", "session-codex", "task", ["src/"])
        with self.assertRaises(MemoryError):
            begin(self.project, "claude", "session-claude", "task")
        with self.assertRaises(MemoryError):
            checkpoint(self.project, self.event("other", provider="claude", task_updates=[{"id": "task", "status": "ready"}],
                                               base_entity_revisions={"task:task": 0}))
        checkpoint(self.project, self.event(task_updates=[{"id": "task", "status": "done",
                  "completion_scope": "validated_on_branch"}], base_entity_revisions={"task:task": 0}))
        begin(self.project, "claude", "session-claude", "task")

    def test_new_project_rules_and_existing_rules_are_preserved(self):
        self.assertTrue((self.root / "CLAUDE.md").is_file())
        self.assertIn("CLAUDE.md", (self.root / "AGENTS.md").read_text())
        other = Path(self.temp.name) / "existing"
        other.mkdir()
        (other / "AGENTS.md").write_text("既有指示：保留此內容。")
        with self.assertRaises(MemoryError):
            initialize(other, self.bindings)
        self.assertFalse((other / "CLAUDE.md").exists())
        initialize(other, self.bindings, adopt_agents=True)
        self.assertIn("既有指示：保留此內容。", (other / "CLAUDE.md").read_text())

    def test_missing_binding_does_not_create_another_store(self):
        with self.assertRaises(MemoryError):
            resolve(self.root, Path(self.temp.name) / "missing.json")
        self.assertEqual(len(events(self.project)), 1)

    def test_external_git_worktrees_share_memory_and_keep_branch_scope(self):
        def git(*args):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        git("init", "-q")
        git("config", "user.email", "memory-test@example.invalid")
        git("config", "user.name", "Memory Test")
        git("add", ".ai-project.json", "CLAUDE.md", "AGENTS.md", ".gitignore")
        git("commit", "-qm", "test fixture")
        for provider in ["claude", "codex"]:
            checkout = Path(self.temp.name) / (provider + " worktree")
            git("worktree", "add", "-qb", "test-" + provider, str(checkout))
            project = resolve(checkout, self.bindings)
            self.assertEqual(project.directory, self.project.directory)
            self.assertEqual(project.repo, checkout.resolve())
            event = self.event("worktree-" + provider, provider=provider, **git_facts(checkout))
            self.assertEqual(self.cli_checkpoint(event, checkout).returncode, 0)
        data = snapshot(self.project)
        self.assertEqual(data["sessions"]["claude:session-claude"]["branch"], "test-claude")
        self.assertEqual(data["sessions"]["codex:session-codex"]["branch"], "test-codex")

    def hook(self, name, **kwargs):
        return run_hook("codex", {"hook_event_name": name, "cwd": str(self.root),
                        "session_id": "hook-session", **kwargs}, self.bindings, LAUNCHER)

    def test_hook_stop_is_bounded_and_incomplete_is_idempotent(self):
        self.hook("SessionStart")
        self.hook("UserPromptSubmit", turn_id="turn-1")
        self.assertEqual(self.hook("Stop", turn_id="turn-1")["decision"], "block")
        self.assertIn("systemMessage", self.hook("Stop", turn_id="turn-1", stop_hook_active=True))
        self.assertEqual(len(events(self.project)), 2)
        self.assertEqual(snapshot(self.project)["entities"]["state"]["stage"], "initialized")

    def test_semantic_checkpoint_completes_hook_even_without_code_changes(self):
        self.hook("SessionStart")
        self.hook("UserPromptSubmit", turn_id="turn-1")
        checkpoint(self.project, self.event("research", session_id="hook-session", pending_turn="turn-1",
                                          completed=["Read-only 研究：確認現有接口。"], details_markdown="研究理由同來源。"))
        self.assertEqual(self.hook("Stop", turn_id="turn-1"), {})

    def test_old_turn_checkpoint_cannot_complete_new_turn(self):
        self.hook("SessionStart")
        self.hook("UserPromptSubmit", turn_id="turn-1")
        self.hook("UserPromptSubmit", turn_id="turn-2")
        checkpoint(self.project, self.event("old", session_id="hook-session", pending_turn="turn-1"))
        self.assertEqual(self.hook("Stop", turn_id="turn-2")["decision"], "block")

    def test_compact_and_interrupt_preserve_partial_without_new_authorization(self):
        self.hook("SessionStart")
        self.hook("UserPromptSubmit", turn_id="turn-1")
        self.assertEqual(self.hook("PreCompact"), {})
        self.assertEqual(self.hook("Interrupt", turn_id="turn-1"), {})
        self.assertEqual(len(events(self.project)), 3)
        self.assertTrue(all(r["payload"].get("kind") == "incomplete" for r in events(self.project)[1:]))

    def test_unregistered_hook_is_quiet(self):
        other = Path(self.temp.name) / "unknown"
        other.mkdir()
        self.assertEqual(run_hook("claude", {"hook_event_name": "Stop", "cwd": str(other),
                         "session_id": "session"}, self.bindings), {})
        self.assertEqual(list(other.iterdir()), [])

    def test_human_prompt_after_interrupted_stop_starts_new_pending_turn(self):
        self.hook("SessionStart")
        self.hook("UserPromptSubmit", turn_id="turn-1", prompt="原任務")
        response = self.hook("Stop", turn_id="turn-1")
        self.hook("UserPromptSubmit", turn_id="continuation", prompt=response["reason"])
        runtime_file = session_path(self.project, "codex", "hook-session")
        self.assertEqual(read_json(runtime_file)["pending"], "turn-1")
        self.hook("UserPromptSubmit", turn_id="turn-2", prompt="新用戶要求")
        self.assertEqual(read_json(runtime_file)["pending"], "turn-2")

    def test_workspace_id_cannot_silently_fork_canonical_store(self):
        other = Path(self.temp.name) / "another"
        other.mkdir()
        with self.assertRaises(MemoryError):
            initialize(other, self.bindings, workspace_id="test.workspace")
        self.assertEqual(list(other.iterdir()), [])

    def test_doctor_detects_entry_drift_but_allows_canonical_edits(self):
        (self.root / "CLAUDE.md").write_text("新規則寫喺 canonical 文件。")
        self.assertEqual(doctor(self.project), [])
        with (self.root / "AGENTS.md").open("a") as stream:
            stream.write("\n錯誤新增行為規則")
        self.assertTrue(doctor(self.project))

    def test_doctor_detects_metadata_canonical_mismatch(self):
        meta = read_json(self.root / ".ai-project.json")
        (self.root / "README.md").write_text("普通文件")
        atomic_json(self.root / ".ai-project.json", {**meta, "canonical_rules": "README.md"})
        self.assertTrue(any("指向不一致" in issue for issue in doctor(self.project)))

    def test_historical_author_is_not_task_owner_and_claims_are_visible(self):
        checkpoint(self.project, self.event("history", provider="import", task_updates=[{"id": "task", "status": "ready"}],
                                          base_entity_revisions={"task:task": 0}))
        self.assertIn("owner=未分配", context(self.project))
        begin(self.project, "codex", "owner-session", "task")
        self.assertIn("codex:owner-session", context(self.project))

    def test_context_reads_one_generation_during_parallel_publication(self):
        def writer():
            for i in range(8):
                checkpoint(self.project, self.event("generation-" + str(i)))
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(writer)
            for _ in range(15):
                text = context(self.project, limit=100000)
                generations = re.findall(r"Generation：([^；]+)", text)
                self.assertEqual(len(set(generations)), 1)
            future.result()

    def test_install_preserves_settings_uses_override_and_is_repeatable(self):
        home = Path(self.temp.name) / "fake home"
        (home / ".claude").mkdir(parents=True)
        (home / ".codex").mkdir()
        settings = {"enabledPlugins": {"example": True}, "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "existing-hook"}]}]}}
        atomic_json(home / ".claude/settings.json", settings)
        (home / ".codex/AGENTS.md").write_text("非生效入口，保留。")
        (home / ".codex/AGENTS.override.md").write_text("原有全域規則。\n")
        receipt = install_user(self.root, home)
        self.assertTrue(Path(receipt["backup"]).exists())
        install_user(self.root, home)
        merged = read_json(home / ".claude/settings.json")
        self.assertEqual(merged["enabledPlugins"], settings["enabledPlugins"])
        self.assertEqual(len(merged["hooks"]["Stop"]), 2)
        self.assertIn("原有全域規則。", (home / ".codex/AGENTS.override.md").read_text())
        self.assertEqual((home / ".codex/AGENTS.md").read_text(), "非生效入口，保留。")
        result = subprocess.run([sys.executable, str(home / ".local/share/shared-project-memory/memoryctl"),
                                 "--binding-file", str(home / ".config/shared-project-memory/registry.json"),
                                 "doctor", "--repo", str(self.root)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
