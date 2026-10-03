import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'setup.py'
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location('memory_setup', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / 'Project with spaces'
        self.repo.mkdir()
        self.home = self.root / 'User with spaces'

    def test_preview_has_no_project_or_home_writes(self):
        result = module.setup(self.repo, home=self.home, dry_run=True)
        self.assertTrue(result['dry_run'])
        self.assertEqual(list(self.repo.iterdir()), [])
        self.assertFalse(self.home.exists())

    def test_full_setup_installed_cli_reads_and_repeat_preserves_settings(self):
        settings = self.home / '.claude/settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({'model': 'keep-this', 'hooks': {}}))
        (self.repo / 'CLAUDE.md').write_text('Existing canonical rule\n')
        (self.repo / 'AGENTS.md').write_text('Existing agent rule\n')
        first = module.setup(self.repo, home=self.home, adopt=True)
        self.assertEqual(first['verification']['checkpoint_write_read'], 'passed')
        self.assertEqual(first['runtime_dispatch'], 'unverified')
        for provider in ('.claude', '.codex'):
            self.assertTrue((self.home / provider / 'skills/shared-project-memory/SKILL.md').is_file())
            self.assertTrue((self.home / provider / 'skills/shared-project-memory/scripts/setup.py').is_file())
        identity = (self.repo / '.ai-project.json').read_text()
        rules = (self.repo / 'CLAUDE.md').read_text()
        self.assertIn('Existing canonical rule', rules)
        self.assertIn('Existing agent rule', rules)
        second = module.setup(self.repo, home=self.home)
        self.assertEqual(second['verification']['doctor'], 'passed')
        self.assertEqual(identity, (self.repo / '.ai-project.json').read_text())
        self.assertEqual(rules, (self.repo / 'CLAUDE.md').read_text())
        data = json.loads(settings.read_text())
        self.assertEqual(data['model'], 'keep-this')
        self.assertEqual(len(data['hooks']['Stop']), 1)

    def test_shared_skill_symlink_keeps_target_and_backs_up_changes(self):
        target = self.home / '.claude/skills/shared-project-memory'
        target.mkdir(parents=True)
        (target / 'SKILL.md').write_text('old version')
        (target / 'local-note.txt').write_text('retain local file')
        link = self.home / '.codex/skills/shared-project-memory'
        link.parent.mkdir(parents=True)
        link.symlink_to(target, target_is_directory=True)
        result = module.setup(self.repo, home=self.home)
        self.assertTrue(link.is_symlink())
        self.assertEqual((target / 'local-note.txt').read_text(), 'retain local file')
        backup = Path(result['skills']['backup']) / '.claude/SKILL.md'
        self.assertEqual(backup.read_text(), 'old version')
        self.assertEqual((link / 'SKILL.md').read_text(), (target / 'SKILL.md').read_text())

    def test_rule_review_failure_does_not_install_global_hooks(self):
        (self.repo / 'AGENTS.md').write_text('Review me first\n')
        with self.assertRaises(module.MemoryError):
            module.setup(self.repo, home=self.home)
        self.assertFalse(self.home.exists())
        self.assertFalse((self.repo / '.ai-project.json').exists())


if __name__ == '__main__':
    unittest.main()
