# Installation and onboarding

Default installation is end-to-end. From the package repo run `python3 shared-project-memory/scripts/setup.py --repo <project>` (from the skill directory use `python3 scripts/setup.py`). This installs skill files for both providers, onboards, merges runtime/hooks, verifies installed CLI checkpoint write/read and runs doctor. Add `--dry-run` to preview, `--adopt-existing-agents` after rule review, and `--workspace <parent>` for a child. Do not stop at a copied skill or preview unless the user explicitly requested copy-only. Global files are included in a request to install this mechanism; normal host permissions still apply.

A skill directory has no executable post-install trigger. A generic installer that only copies files must be followed by this setup entrypoint or an agent reading SKILL.md and completing it. User hook trust and actual fresh-session dispatch remain separate validation requirements. The lower-level commands below are for manual operation.


Requirements: Python 3.10+, Git only when using Git/worktrees, macOS or Linux with local `fcntl` locks. No Python packages, database server, API key or model call is required by the memory tool itself. Windows and simultaneous cross-machine writes are not supported by this release.

Place the `shared-project-memory/` skill folder in your provider's skill location, or keep a downloaded checkout and point an agent to its SKILL.md. For Codex, a user skill can live under `~/.codex/skills/shared-project-memory`; for Claude Code, use `~/.claude/skills/shared-project-memory`. The same folder contents can serve both. Hooks and memory remain separate from skill discovery.

From the skill directory, for a standalone project:

```bash
python3 scripts/onboard.py --repo /absolute/path/to/project --dry-run
python3 scripts/onboard.py --repo /absolute/path/to/project
python3 scripts/memoryctl install-user --workspace /absolute/path/to/project --dry-run
python3 scripts/memoryctl install-user --workspace /absolute/path/to/project
```

Onboarding creates project identity, canonical instructions, an AGENTS pointer and initial memory. Installation copies the runtime to `~/.local/share/shared-project-memory`, merges provider hooks and global instruction wrappers, and registers the workspace in `~/.config/shared-project-memory/registry.json`. Hooks run automatically only after the provider loads them and required trust is established. Review new Codex definitions with `/hooks` in the CLI; then open a fresh session in the surface you actually use.

For another independent project, run onboarding there; if global hooks already exist, onboarding's binding is enough to make the installed runtime locate its store. Do not reinstall global hooks just to add another project. If upgrading the packaged runtime, review changed hook definitions and validate the runtime again.

For a project inside an existing workspace:

```bash
python3 scripts/onboard.py --repo /absolute/workspace/subproject --workspace /absolute/workspace
```

This registers a child ID and writes its metadata while storing memory under the parent `.ai-memory/`. It does not create another workspace store. Existing instruction files need the same review/migration as standalone projects. `--project-id` can supply a desired stable ID. IDs and metadata go into version control; machine-local bindings/runtime locks do not.

If AGENTS.md already exists, first read it and any canonical Claude file. Add `--adopt-existing-agents` only after that review. The helper backs up original rules, preserves their full text in the canonical file and replaces AGENTS.md with a loader. Both files containing conflicting instructions must be reconciled semantically by the agent; a text-preservation helper cannot select the right rule. Repeated onboarding of the same ID is a no-op and does not re-import progress.

Import existing progress with a normal semantic checkpoint after auditing actual sources. The helper initializes identity and workflow only; it deliberately does not guess the project's objective, completed work or live status. Keep detailed source documents in place. A workspace memory can cover ordinary notes/research folders without making every directory a separate project.

Installation retains unrelated settings and backups. It does not delete memories, make commits, publish a repository, deploy code, start services or repair provider installations. For rollback, inspect `installation.json` and its backups; remove only this mechanism's managed blocks and hook handlers, preserving later user changes. Do not restore entire settings files blindly.
