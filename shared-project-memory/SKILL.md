---
name: shared-project-memory
description: Set up or maintain shared file-based project memory for Claude Code and Codex, including project onboarding, existing-rule migration, checkpoints, worktree handoffs, and lifecycle hooks. Use when asked to share agent progress or adopt this memory mechanism in a project.
---

# Shared project memory

Use the bundled Python tool to keep one canonical memory store per workspace and stable IDs per project. The tool records semantic checkpoints, entity revisions and incomplete observations. It does not synchronize raw chat transcripts, execute historical next steps, or establish that deployed code is healthy.

## Set up a project

Read its existing instructions and the user's authorized scope first. Locate this skill's `scripts/` directory; never assume the skill was installed under a particular user's home.

Run `python3 <skill>/scripts/onboard.py --repo <project> --dry-run` to inspect the proposed onboarding. Then run the same command without `--dry-run` within the user's requested setup scope. For a child project sharing an existing parent store, add `--workspace <parent>`. A non-Git folder can be a project. Ordinary reference/output folders can inherit the parent's memory instead of getting their own ID.

The helper preserves existing canonical filename case. If AGENTS.md exists, inspect it before using `--adopt-existing-agents`: this backs up and migrates its content before replacing it with a pointer. When both instruction files contain rules, reconcile conflicts with the user's instructions; the helper preserves both texts but cannot decide their meaning. Reverse imports or ambiguous canonical files require manual reconciliation before onboarding.

Global hook installation is a separate scope: use `python3 <skill>/scripts/memoryctl install-user --workspace <canonical-workspace> --dry-run`, then apply after authorization covers those user-level files. It merges unrelated settings and retains backups. Installing a downloaded skill alone does **not** install hooks. Do not bypass Codex hook trust or edit the trust database; the user reviews installed definitions through the supported hook review surface.

Use [setup.md](references/setup.md) for installation, existing-rule migration and cross-project use. Use [operations.md](references/operations.md) for checkpoints, conflicts, ownership and recovery. Use [validation.md](references/validation.md) to test real lifecycle dispatch.

## Work and hand off

- Read `memoryctl context --repo <current-project>` and canonical rules at session start or handoff. Read relevant source documents and session records rather than treating the generated overview as exhaustive.
- At meaningful milestones and before ending a turn, create a `draft`, fill results, unfinished work, decisions, failed attempts, evidence and next steps, then submit `checkpoint`. Read-only work still has a memory checkpoint unless the user explicitly forbids memory writes.
- Use the actual provider/session ID supplied by hooks. Without one, use a unique ID and state that hook dispatch is unverified. Never attribute another agent's work to yourself.
- Task/decision/state updates use current `base_entity_revisions`; re-read and resolve conflicts rather than overwriting another agent's update. Preserve the draft's checkpoint ID and pending-turn token on retry.
- For simultaneous code edits, use separate checkouts/worktrees and `begin` to record task ownership/scope. Claims are cooperative coordination, not a file-edit lock.
- Keep source pointers and provenance. Historical reports are `reported`; tests, code changes, merge and live deployment are separate completion scopes. Do not copy secrets or full raw transcripts into memory.
- End with `doctor`; use `rebuild` only for unpublished generations/recovery. Never directly edit old events or generated views/sessions.

Checkpoint rules remain in the project's canonical instructions; AGENTS.md is its loader. After installation, global POLICY.md is the common bootstrap authority. A skill is discoverable guidance, not a background timer or a guarantee that an agent will comply. State actual validation coverage honestly.
