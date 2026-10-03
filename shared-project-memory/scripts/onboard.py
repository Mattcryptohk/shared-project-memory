#!/usr/bin/env python3
"""Preserve instructions while onboarding a standalone or child project."""

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

from project_memory.bootstrap import agents_template, initialize
from project_memory.io import MemoryError, atomic_write, digest, now, read_json
from project_memory.registry import doctor, register, resolve
from project_memory.store import checkpoint


def onboard(repo, workspace=None, binding_file=None, adopt=False, dry_run=False,
            project_id=None):
    repo = Path(repo).expanduser().resolve()
    if not repo.is_dir():
        raise MemoryError('Project directory must already exist.')
    parent = resolve(workspace, binding_file) if workspace else None
    if parent and repo != parent.workspace and parent.workspace not in repo.parents:
        raise MemoryError('Child project must be inside its canonical workspace.')
    metadata = read_json(repo / '.ai-project.json')
    if metadata:
        project = resolve(repo, binding_file)
        if project_id and project_id != project.project_id:
            raise MemoryError('Existing project ID differs; do not fork its identity.')
        if parent and project.workspace != parent.workspace:
            raise MemoryError('Existing project belongs to a different workspace.')
        return {'already_registered': True, 'project_id': project.project_id,
                'issues': doctor(project), 'dry_run': dry_run}
    candidates = [p for p in repo.iterdir() if p.name.lower() == 'claude.md']
    if not candidates and (repo / '.claude').is_dir():
        candidates = [p for p in (repo / '.claude').iterdir()
                      if p.name.lower() == 'claude.md']
    if len(candidates) > 1:
        raise MemoryError('Ambiguous canonical files; reconcile them first.')
    canonical = candidates[0] if candidates else repo / 'CLAUDE.md'
    canonical_name = str(canonical.relative_to(repo))
    original_rules = canonical.read_text() if canonical.exists() else ''
    agents = repo / 'AGENTS.md'
    original_agents = agents.read_text() if agents.exists() else None
    pointer = agents_template(canonical_name)
    if '@AGENTS.md' in original_rules:
        raise MemoryError('Canonical file imports AGENTS.md; reconcile reverse imports first.')
    if original_agents is not None and original_agents != pointer and not adopt:
        raise MemoryError('Read AGENTS.md before rerunning with --adopt-existing-agents.')
    ident = project_id
    if parent:
        slug = re.sub(r'[^a-z0-9]+', '-', repo.name.lower()).strip('-') or 'project'
        ident = ident or parent.workspace_id + '.' + slug
        entry = parent.registry['projects'].get(ident)
        if entry and (parent.workspace / entry['path']).resolve() != repo:
            raise MemoryError('Project ID already belongs to another directory.')
    plan = {'repo': str(repo), 'workspace': str(parent.workspace) if parent else str(repo),
            'canonical_rules': canonical_name, 'existing_agents': original_agents is not None,
            'global_hooks_changed': False, 'dry_run': dry_run,
            'changes': ['canonical instructions', 'AGENTS pointer', 'project identity',
                        'workspace registry/binding', 'initial memory']}
    if dry_run:
        return plan
    destination = parent.workspace if parent else repo
    backup = destination / '.ai-memory/migrations' / ('onboard-' + uuid.uuid4().hex)
    if canonical.exists():
        atomic_write(backup / 'canonical.before.md', original_rules)
    if original_agents is not None:
        atomic_write(backup / 'AGENTS.before.md', original_agents)
    rules = original_rules
    if original_agents is not None and original_agents != pointer:
        rules += ('\n\n## Preserved previous AGENTS instructions\n\n' if rules else '') + original_agents
    if not rules:
        rules = '# ' + repo.name + '\n'
    marker = '<!-- shared-project-memory:project:start -->'
    if marker not in rules:
        rules += '\n\n' + marker + '''
## Shared project memory

- At startup/handoff run `python3 ~/.local/share/shared-project-memory/memoryctl context --repo .`; read canonical rules and relevant project memory. For a child project, also read the owning workspace rules returned by context.
- Before completing a turn and at meaningful milestones, submit a semantic checkpoint with results, evidence, unfinished work, decisions, attempts and next steps. Read-only project work still records memory unless the user explicitly forbids memory writes.
- Use the actual hook provider/session ID and preserve the draft's checkpoint ID/pending token. Without hook context, use a unique ID and mark dispatch unverified.
- Update task/decision/state entities with current base revisions; re-read conflicts. Use separate worktrees and task claims for simultaneous code edits.
- Change working rules here; AGENTS.md is only a loader. Do not directly rewrite generated memory views, sessions or old events.
- Historical sources are reported until verified. Memory does not authorize new work. Do not store secrets or full raw transcripts. Run memoryctl doctor before completing work.
<!-- shared-project-memory:project:end -->
'''
    atomic_write(canonical, rules)
    atomic_write(agents, pointer)
    if not parent:
        project = initialize(repo, binding_file, project_id=ident,
                             name=repo.name, preserve_agents=True)
    else:
        register(parent.workspace, ident, str(repo.relative_to(parent.workspace)), repo.name,
                 status='bootstrapped', metadata=True, canonical_rules=canonical_name,
                 agents_hash=digest(pointer))
        project = resolve(repo, binding_file)
        checkpoint(project, {'schema_version': 1, 'workspace_id': project.workspace_id,
            'project_id': ident, 'checkpoint_id': 'onboard-' + uuid.uuid4().hex,
            'provider': 'memoryctl', 'session_id': 'onboarding', 'created_at': now(),
            'kind': 'bootstrap', 'base_entity_revisions': {'state': 0},
            'state_update': {'objective': 'Await source-audited project objective.',
                            'stage': 'initialized', 'verification': 'reported'},
            'completed': ['Connected identity, canonical instructions and shared memory.'],
            'details_markdown': 'Preserved existing rules. No progress or deployment inferred.'})
    issues = doctor(project)
    if issues:
        raise MemoryError('Onboarding needs reconciliation: ' + '; '.join(issues))
    return {**plan, 'project_id': project.project_id, 'store': str(project.directory),
            'backup': str(backup), 'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--workspace')
    parser.add_argument('--binding-file')
    parser.add_argument('--project-id')
    parser.add_argument('--adopt-existing-agents', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        result = onboard(args.repo, args.workspace, args.binding_file,
                         args.adopt_existing_agents, args.dry_run, args.project_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (MemoryError, OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
