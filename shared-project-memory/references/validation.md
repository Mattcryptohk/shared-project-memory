# Verify the installed mechanism

The included automated suite exercises concurrent writes, revision conflicts, crash recovery, duplicate rejection, ownership and real local Git worktrees. Those tests do not prove that Claude/Codex lifecycle hooks dispatch in a particular app version.

After reviewing/trusting hooks, open a fresh session in the actual Claude Code or Codex surface. Give a read-only task with a unique handoff marker, allowing routine memory maintenance but without explicitly asking it to save. Check:

1. SessionStart injects context and creates a runtime session observation.
2. UserPromptSubmit injects the actual provider/session ID and records a new pending token.
3. A semantic checkpoint contains the marker/results with the same session ID; its `pending_turn` matches runtime `pending` and `checkpoint_pending`.
4. Capture separate Stop dispatch evidence. A normal saved turn does not prove the missing-checkpoint reminder branch.
5. A fresh session in the other provider retrieves the marker from the saved file without being given the answer, and saves its own checkpoint.

Test missing-checkpoint Stop behavior in an isolated registered fixture, not a production strategy store. Expect one continuation request and then bounded incomplete observations if saving still fails. Test Interrupt/PreCompact separately when those recovery paths matter.

Do not manually call `memoryctl hook` and then claim platform dispatch was verified. Adapter payload tests, agent rule compliance, platform trust and actual lifecycle execution are different evidence.

The original pilot verified normal Claude/Codex context, prompt dispatch, checkpoint linkage and file-backed handoffs. Its missing-checkpoint Stop branch and some recovery events were fixture-tested only. Downloaders must run acceptance checks in their own runtime.

Official lifecycle references: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Claude Code hooks](https://code.claude.com/docs/en/hooks). Hook API/trust behavior can change; verify these primary sources when diagnosing a new runtime.
