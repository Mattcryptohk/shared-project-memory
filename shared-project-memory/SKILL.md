---
name: shared-project-memory
description: Set up or maintain shared file-based project memory for Claude Code and Codex, including project onboarding, existing-rule migration, checkpoints, worktree handoffs, and lifecycle hooks. Use when asked to install this skill, enable persistent project memory, share agent progress, or adopt this mechanism in a project, including single-provider use.
---

# Shared project memory

Use the bundled Python tool to keep one canonical memory store per workspace and stable IDs per project. The tool records semantic checkpoints, entity revisions and incomplete observations. It does not synchronize raw chat transcripts, execute historical next steps, or establish that deployed code is healthy.

## Install means complete setup

A request to install/use this memory mechanism in the current or named project means end-to-end setup: skill availability, project onboarding, canonical rule migration, user runtime/hooks configuration, local write/read verification and a source-audited progress checkpoint. Do not end at copying skill files or a dry-run, and do not ask the user to repeat “initialize” after they requested installation. An explicit “download/copy only; do not change project or hooks” limits that scope.

A generic skill installer does not automatically execute this file or scripts. If you are handling installation, read this SKILL.md immediately after copying and continue setup in the same turn. If loading it in a later session, check project metadata and complete pending setup within the user's existing authorization; do not install into unrelated projects merely because the skill is discoverable.

Locate this skill's scripts directory; do not assume a home path. Read project instructions and inspect the requested scope. Reconcile actual contradictions in existing rules before migration, preserving user instructions and both original texts. Do not treat the existence of AGENTS.md as a reason to stop for another confirmation. The helper preserves filename case and backs up originals; reverse imports or ambiguous canonical files require reconciliation first.

Run `python3 <skill>/scripts/setup.py --repo <project> --dry-run`, then apply without `--dry-run`. After reading AGENTS.md, add `--adopt-existing-agents` when necessary. Add `--workspace <parent>` for a child sharing the owning store. This command installs both provider skill folders, onboards, installs/merges user runtime and hooks, runs the installed CLI, writes and reads a verification checkpoint, then checks doctor. Repeated setup retains identity, rules and unrelated settings. Use the host's normal approval mechanism if filesystem permissions require it; no extra permission conversation for steps already covered by the installation request.

After setup, audit project source documents and save a real progress checkpoint with provenance. This is part of installation; the helper's setup marker is not a historical-progress import. Preserve existing memory rather than re-importing it. Ordinary reference folders can inherit parent memory. A non-Git folder can be a project. A single provider can use the mechanism without a second account/tool.

Do not bypass provider hook trust or edit its trust database. Complete all permitted work first; report only the concrete trust/fresh-session action still needed. Separate `local write/read verified`, `hooks configured`, and `actual lifecycle dispatch verified`; do not claim fully automatic hooks solely from setup checks. Skill files alone have no install-time execution trigger.

Use [setup.md](references/setup.md) for detailed migration and cross-project use, [operations.md](references/operations.md) for memory operations, and [validation.md](references/validation.md) for real lifecycle verification.

## Work and hand off

- Read `memoryctl context --repo <current-project>` and canonical rules at session start or handoff. Read relevant source documents and session records rather than treating the generated overview as exhaustive.
- At meaningful milestones and before ending a turn, create a `draft`, fill results, unfinished work, decisions, failed attempts, evidence and next steps, then submit `checkpoint`. Read-only work still has a memory checkpoint unless the user explicitly forbids memory writes.
- Use the actual provider/session ID supplied by hooks. Without one, use a unique ID and state that hook dispatch is unverified. Never attribute another agent's work to yourself.
- Task/decision/state updates use current `base_entity_revisions`; re-read and resolve conflicts rather than overwriting another agent's update. Preserve the draft's checkpoint ID and pending-turn token on retry.
- For simultaneous code edits, use separate checkouts/worktrees and `begin` to record task ownership/scope. Claims are cooperative coordination, not a file-edit lock.
- Keep source pointers and provenance. Historical reports are `reported`; tests, code changes, merge and live deployment are separate completion scopes. Do not copy secrets or full raw transcripts into memory.
- End with `doctor`; use `rebuild` only for unpublished generations/recovery. Never directly edit old events or generated views/sessions.

Checkpoint rules remain in the project's canonical instructions; AGENTS.md is its loader. After installation, global POLICY.md is the common bootstrap authority. A skill is discoverable guidance, not a background timer or a guarantee that an agent will comply. State actual validation coverage honestly.
