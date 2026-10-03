import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'onboard.py'
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location('onboard', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='portable-memory-')
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name).resolve()
        self.root = self.base / 'Other project with spaces'
        self.root.mkdir()
        self.binding = self.base / 'bindings.json'

    def test_dry_run_changes_nothing(self):
        module.onboard(self.root, binding_file=self.binding, dry_run=True)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertFalse(self.binding.exists())

    def test_rules_from_both_files_survive_and_repeat_is_noop(self):
        (self.root / 'Claude.MD').write_text('Canonical rule A\n')
        (self.root / 'AGENTS.md').write_text('Existing local rule B\n')
        with self.assertRaises(module.MemoryError):
            module.onboard(self.root, binding_file=self.binding)
        self.assertEqual((self.root / 'AGENTS.md').read_text(), 'Existing local rule B\n')
        result = module.onboard(self.root, binding_file=self.binding, adopt=True)
        text = (self.root / 'Claude.MD').read_text()
        self.assertTrue(text.startswith('Canonical rule A\n'))
        self.assertIn('Existing local rule B\n', text)
        self.assertEqual((Path(result['backup']) / 'AGENTS.before.md').read_text(), 'Existing local rule B\n')
        again = module.onboard(self.root, binding_file=self.binding)
        self.assertTrue(again['already_registered'])
        self.assertEqual((self.root / 'Claude.MD').read_text(), text)

    def test_child_shares_parent_store(self):
        module.onboard(self.root, binding_file=self.binding)
        child = self.root / 'Independent module'
        child.mkdir()
        result = module.onboard(child, self.root, self.binding)
        project = module.resolve(child, self.binding)
        self.assertEqual(project.workspace, self.root)
        self.assertTrue(str(project.directory).startswith(str(self.root / '.ai-memory')))
        self.assertFalse((child / '.ai-memory').exists())
        self.assertEqual(module.doctor(project), [])
        self.assertEqual(module.onboard(child, self.root, self.binding)['project_id'], result['project_id'])

    def test_child_id_collision_does_not_modify_rules(self):
        module.onboard(self.root, binding_file=self.binding)
        a, b = self.root / 'A', self.root / 'B'
        a.mkdir(); b.mkdir()
        module.onboard(a, self.root, self.binding, project_id='shared.child')
        with self.assertRaises(module.MemoryError):
            module.onboard(b, self.root, self.binding, project_id='shared.child')
        self.assertEqual(list(b.iterdir()), [])

    def test_reverse_import_is_rejected_without_writes(self):
        (self.root / 'CLAUDE.md').write_text('@AGENTS.md\n')
        (self.root / 'AGENTS.md').write_text('Rule\n')
        with self.assertRaises(module.MemoryError):
            module.onboard(self.root, binding_file=self.binding, adopt=True)
        self.assertFalse((self.root / '.ai-memory').exists())


if __name__ == '__main__':
    unittest.main()
