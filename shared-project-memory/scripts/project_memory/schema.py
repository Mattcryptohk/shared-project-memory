"""Checkpoint 格式同狀態更新驗證。"""

from datetime import datetime

from .io import MemoryError, safe_id

TASK_STATUSES = {"ready", "in_progress", "blocked", "blocked_user_decision", "done", "cancelled"}
VERIFICATIONS = {"verified", "reported", "hypothesis", "superseded"}
SCOPES = {"implemented_on_branch", "validated_on_branch", "merged", "deployed_verified", "research_documented"}
LIST_FIELDS = ("completed", "in_progress", "attempts", "blockers", "next_actions", "checks", "artifacts", "sources")


def validate(event):
    if not isinstance(event, dict) or event.get("schema_version") != 1:
        raise MemoryError("Checkpoint 必須係 schema_version 1 JSON object。")
    for field in ("checkpoint_id", "workspace_id", "project_id"):
        safe_id(event.get(field))
    for field in ("provider", "session_id", "created_at"):
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise MemoryError(f"Checkpoint 缺少 {field}。")
    try:
        if datetime.fromisoformat(event["created_at"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError()
    except ValueError:
        raise MemoryError("created_at 必須係包含 timezone 嘅 ISO timestamp。")
    for field in LIST_FIELDS:
        if field in event and not isinstance(event[field], list):
            raise MemoryError(f"{field} 必須係 list。")
    if not isinstance(event.get("details_markdown", ""), str):
        raise MemoryError("details_markdown 必須係文字。")
    revisions = event.get("base_entity_revisions", {})
    if not isinstance(revisions, dict) or any(type(v) is not int or v < 0 for v in revisions.values()):
        raise MemoryError("base_entity_revisions 必須係非負整數 mapping。")
    updates = [("state", event["state_update"])] if event.get("state_update") is not None else []
    for field, prefix in (("task_updates", "task:"), ("decision_updates", "decision:")):
        if not isinstance(event.get(field, []), list):
            raise MemoryError(f"{field} 必須係 list。")
        seen = set()
        for update in event.get(field, []):
            if not isinstance(update, dict):
                raise MemoryError("實體更新必須係 object。")
            ident = safe_id(update.get("id"))
            if ident in seen:
                raise MemoryError("同一 checkpoint 唔可以重複更新相同實體。")
            seen.add(ident)
            if prefix == "task:":
                if update.get("status") not in TASK_STATUSES:
                    raise MemoryError("Task status 無效。")
                if update["status"] == "done" and update.get("completion_scope") not in SCOPES:
                    raise MemoryError("完成 task 必須指明 completion_scope。")
            updates.append((prefix + ident, update))
    for key, update in updates:
        if not isinstance(update, dict) or key not in revisions:
            raise MemoryError(f"更新 {key} 必須提供 base_entity_revisions。")
        verification = update.get("verification", "reported")
        if verification not in VERIFICATIONS:
            raise MemoryError("verification 無效。")
        successful = any(isinstance(c, dict) and c.get("exit_code") == 0 and c.get("command") for c in event.get("checks", []))
        verified_source = any(isinstance(s, dict) and s.get("verification") == "verified" and s.get("path") for s in event.get("sources", []))
        if verification == "verified" and not successful and not verified_source:
            raise MemoryError("Verified 更新必須附 checks 或 sources。")
    if not isinstance(event.get("resolves_conflicts", []), list):
        raise MemoryError("resolves_conflicts 必須係 list。")
    for resolution in event.get("resolves_conflicts", []):
        if not isinstance(resolution, dict) or not isinstance(resolution.get("entity"), str):
            raise MemoryError("衝突解決需提供 entity 同 checkpoint_id。")
        safe_id(resolution.get("checkpoint_id"))
    if event.get("kind", "semantic") not in {"semantic", "incomplete", "bootstrap"}:
        raise MemoryError("Checkpoint kind 無效。")
    if event.get("kind", "semantic") == "incomplete" and updates:
        raise MemoryError("Incomplete 觀察唔可以改 task、decision 或 project 狀態。")
    if event.get("kind", "semantic") == "semantic" and not updates and not event.get("details_markdown", "").strip() and not any(event.get(k) for k in LIST_FIELDS):
        raise MemoryError("空白 draft 唔係語意 checkpoint；先填寫工作結果同理由。")
    if event.get("state_update") is not None:
        for field in ("objective", "stage"):
            if field in event["state_update"] and not isinstance(event["state_update"][field], str):
                raise MemoryError(f"state_update.{field} 必須係文字。")
        for field in ("blockers", "next_actions", "read_first"):
            if field in event["state_update"] and not isinstance(event["state_update"][field], list):
                raise MemoryError(f"state_update.{field} 必須係 list。")
    return event
