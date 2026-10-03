"""Claude/Codex event adapter；保存事實，最多提醒一次補語意 checkpoint。"""

import shlex
import uuid
from pathlib import Path

from .io import MemoryError, atomic_json, digest, locked, now, read_json
from .registry import doctor, git_facts, resolve
from .store import begin, checkpoint, context, session_path


def additional(event, text):
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def run_hook(provider, event, binding_file=None, launcher=None):
    name = event.get("hook_event_name")
    cwd = event.get("cwd")
    session_id = event.get("session_id")
    if not isinstance(cwd, str) or not isinstance(session_id, str):
        raise MemoryError("Hook 缺少 cwd 或 session_id。")
    try:
        project = resolve(cwd, binding_file)
    except MemoryError as exc:
        if str(exc).startswith("UNREGISTERED"):
            return {}
        raise
    if project.entry["status"] == "not_bootstrapped":
        if name == "SessionStart":
            return additional(name, context(project))
        return {}
    launcher = str(launcher or Path.home() / ".local/share/shared-project-memory/memoryctl")
    command = "python3 " + shlex.quote(launcher)
    if binding_file:
        command += " --binding-file " + shlex.quote(str(binding_file))
    args = f" --repo {shlex.quote(str(project.repo))} --provider {shlex.quote(provider)} --session {shlex.quote(session_id)}"
    if name == "SessionStart":
        begin(project, provider, session_id)
        text = context(project) + "\n\n本次 session：" + session_id + "\n"
        text += "完成一輪前先產生 checkpoint draft，填寫結果同理由，再提交：\n"
        text += command + " draft" + args + " --output /tmp/memory-checkpoint-" + digest(session_id)[:12] + ".json\n"
        text += command + " checkpoint --repo " + shlex.quote(str(project.repo)) + " --input <已填寫嘅JSON檔>\n"
        return additional(name, text)
    runtime_path = session_path(project, provider, session_id)
    if name == "UserPromptSubmit":
        with locked(project.lock):
            runtime = read_json(runtime_path, {})
            # Stop 嘅自動 continuation 唔重新開一個 pending turn。
            continuation = runtime.get("continuation_expected") and runtime.get("expected_prompt_sha256") == digest(event.get("prompt", ""))
            if not continuation:
                runtime.update(pending=event.get("turn_id") or uuid.uuid4().hex,
                               prompted_pending=None, checkpoint_pending=None, audit_payloads={})
            runtime["continuation_expected"] = False
            atomic_json(runtime_path, runtime)
        return additional(name, f"本輪 session_id={session_id}；provider={provider}。完成前提交語意 checkpoint，包含 read-only 研究結果。")
    if name not in {"Stop", "PreCompact", "SessionEnd", "Interrupt"}:
        return {}
    with locked(project.lock):
        runtime = read_json(runtime_path, {})
        pending = runtime.get("pending") or event.get("turn_id") or "unknown-turn"
        complete = runtime.get("last_checkpoint") and runtime.get("checkpoint_pending") == pending
        issues = doctor(project) if name == "Stop" else []
        first_prompt = runtime.get("prompted_pending") != pending and not event.get("stop_hook_active")
        reason = "；".join(issues) if issues else "本輪未提交語意 checkpoint。"
        reason += " 先用 " + command + " draft" + args + " --output /tmp/memory-checkpoint-" + digest(session_id)[:12] + ".json，填寫結果、來源、理由及下一步，再用 checkpoint --input 保存。"
        if name == "Stop" and (not complete or issues) and first_prompt:
            runtime.update(prompted_pending=pending, continuation_expected=True, expected_prompt_sha256=digest(reason))
            atomic_json(runtime_path, runtime)
        elif name == "Stop":
            runtime["continuation_expected"] = False
            atomic_json(runtime_path, runtime)
        incomplete = None
        if not complete:
            audits = runtime.setdefault("audit_payloads", {})
            key = digest(pending + name)
            if key not in audits:
                audits[key] = {"schema_version": 1, "workspace_id": project.workspace_id,
                              "project_id": project.project_id, "checkpoint_id": "incomplete-" + digest(provider + session_id + pending + name)[:32],
                              "provider": provider, "session_id": session_id, "created_at": now(),
                              "kind": "incomplete", **git_facts(project.repo),
                              "blockers": ["handoff incomplete：未收到本輪語意 checkpoint。"],
                              "details_markdown": f"{name} 保存當時 Git facts。未推斷完成狀態，未複製 raw transcript。"}
            incomplete = audits[key]
            atomic_json(runtime_path, runtime)
    if not complete:
        checkpoint(project, incomplete)
    if name == "Stop" and (not complete or issues):
        if first_prompt:
            return {"decision": "block", "reason": reason}
        return {"systemMessage": "Shared memory 仍需交接補記；已保存 partial observations，同一輪唔再自動繼續。"}
    return {}
