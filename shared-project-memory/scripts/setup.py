#!/usr/bin/env python3
"""Complete project onboarding, user hooks installation and local write/read checks."""
import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from onboard import onboard
from project_memory.install import install_user
from project_memory.io import MemoryError, atomic_write, now
from project_memory.registry import doctor, resolve
from project_memory.store import checkpoint


def install_skills(home):
    source = Path(__file__).resolve().parent.parent
    backup = home / '.config/shared-project-memory/backups' / ('skills-' + uuid.uuid4().hex)
    changed = []
    for provider in ('.claude', '.codex'):
        target = home / provider / 'skills/shared-project-memory'
        if not target.resolve().is_relative_to(home.resolve()):
            raise MemoryError('Skill symlink points outside selected home; reconcile it first.')
        for path in sorted(source.rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            dest = target / path.relative_to(source)
            data = path.read_text()
            if dest.exists() and dest.read_text() == data:
                continue
            if dest.exists():
                atomic_write(backup / provider / path.relative_to(source), dest.read_text())
            atomic_write(dest, data)
            changed.append(str(dest))
    return {'changed': changed, 'backup': str(backup), 'providers': ['claude', 'codex']}


def setup(repo, workspace=None, home=None, adopt=False, dry_run=False, project_id=None):
    home = Path(home).expanduser().resolve() if home else Path.home()
    binding = home / '.config/shared-project-memory/registry.json'
    plan = onboard(repo, workspace, binding, adopt, dry_run, project_id)
    if dry_run:
        return {'dry_run': True, 'onboarding': plan,
                'user_home': str(home), 'actions': ['install skill for both providers', 'onboard project', 'install/merge user runtime and hooks',
                'verify installed CLI and checkpoint write/read', 'doctor'],
                'runtime_dispatch': 'Requires fresh session and any provider trust review.'}
    project = resolve(repo, binding)
    issues = doctor(project)
    if issues:
        raise MemoryError('Reconcile project before user installation: ' + '; '.join(issues))
    skills = install_skills(home)
    installation = install_user(project.workspace, home)
    launcher = home / '.local/share/shared-project-memory/memoryctl'
    command = [sys.executable, str(launcher), '--binding-file', str(binding)]
    subprocess.run(command + ['doctor', '--repo', str(project.repo)], check=True, capture_output=True, text=True)
    marker = 'setup-check-' + uuid.uuid4().hex
    receipt = checkpoint(project, {'schema_version': 1, 'workspace_id': project.workspace_id,
        'project_id': project.project_id, 'checkpoint_id': marker, 'provider': 'memoryctl',
        'session_id': 'setup', 'created_at': now(), 'kind': 'semantic', 'base_entity_revisions': {},
        'completed': ['Configured project identity, canonical rules, user runtime and hook definitions.',
                      'Local setup verification marker: ' + marker],
        'checks': [{'command': 'installed memoryctl doctor', 'exit_code': 0}],
        'details_markdown': 'Setup verification only. No project progress inferred. '
                            'Provider trust and actual lifecycle dispatch remain unverified.'})
    output = subprocess.run(command + ['context', '--repo', str(project.repo)],
                            check=True, capture_output=True, text=True).stdout
    if marker not in output:
        raise MemoryError('Installed runtime did not read the setup checkpoint.')
    subprocess.run(command + ['doctor', '--repo', str(project.repo)], check=True, capture_output=True, text=True)
    return {'onboarding': plan, 'skills': skills, 'installation': installation,
            'verification': {'installed_cli': 'passed', 'checkpoint_write_read': 'passed',
                             'doctor': 'passed', 'checkpoint_id': receipt['checkpoint_id']},
            'runtime_dispatch': 'unverified',
            'remaining': ['Complete any provider hook trust review and open a fresh session.',
                          'Agent audits project sources and saves semantic progress; do not infer history.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--workspace')
    parser.add_argument('--home', help='Isolated home for tests; defaults to current user.')
    parser.add_argument('--project-id')
    parser.add_argument('--adopt-existing-agents', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        result = setup(args.repo, args.workspace, args.home, args.adopt_existing_agents,
                       args.dry_run, args.project_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (MemoryError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print('Setup incomplete: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
