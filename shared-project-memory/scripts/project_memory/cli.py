"""memoryctl CLI。"""

import argparse
import json
import sys
import uuid
from pathlib import Path

from .bootstrap import initialize
from .io import MemoryError, atomic_json, encode, now
from .registry import bind, doctor, git_facts, register, resolve
from .store import begin, checkpoint, context, rebuild, session_path, snapshot


def parser():
    result = argparse.ArgumentParser(description="Claude/Codex 共用 project memory")
    result.add_argument("--binding-file", help="本機 workspace binding JSON（測試或便攜安裝）")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("context", "doctor", "rebuild", "snapshot", "begin", "draft", "checkpoint", "hook"):
        command = commands.add_parser(name)
        command.add_argument("--repo", default=".")
        command.add_argument("--project", help="明確指定已登記 project ID")
        if name in {"begin", "draft"}:
            command.add_argument("--provider", required=True)
            command.add_argument("--session", required=True)
        if name == "begin":
            command.add_argument("--task")
            command.add_argument("--scope", action="append", default=[])
            command.add_argument("--takeover", action="store_true")
        if name == "draft":
            command.add_argument("--output", required=True)
        if name == "checkpoint":
            command.add_argument("--input", required=True, help="JSON 檔案或 - 讀 stdin")
        if name == "hook":
            command.add_argument("--provider", choices=["claude", "codex"], required=True)
    command = commands.add_parser("init")
    command.add_argument("--repo", default=".")
    command.add_argument("--name")
    command.add_argument("--workspace-id")
    command.add_argument("--project-id")
    command.add_argument("--adopt-existing-agents", action="store_true")
    command.add_argument("--preserve-agents", action="store_true")
    command = commands.add_parser("bind")
    command.add_argument("--workspace-id", required=True)
    command.add_argument("--workspace", required=True)
    command = commands.add_parser("register")
    command.add_argument("--repo", default=".")
    command.add_argument("--project-id", required=True)
    command.add_argument("--path", required=True)
    command.add_argument("--name", required=True)
    command = commands.add_parser("install-user")
    command.add_argument("--workspace", required=True)
    command.add_argument("--home", help="測試安裝用 home；正常安裝使用目前使用者 home")
    command.add_argument("--dry-run", action="store_true")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "hook":
            from .hooks import run_hook
            try:
                payload = json.load(sys.stdin)
                output = run_hook(args.provider, payload, args.binding_file,
                                  launcher=Path(sys.argv[0]).resolve())
            except (MemoryError, OSError, ValueError, KeyError) as exc:
                # Hook 儲存失敗可見，但唔令研究／code 工作無限繼續。
                output = {"systemMessage": "Shared memory hook 失敗：" + str(exc)}
            print(encode(output), end="")
            return 0
        if args.command == "install-user":
            from .install import install_user
            print(encode(install_user(args.workspace, args.home, args.dry_run)), end="")
            return 0
        if args.command == "bind":
            bind(args.workspace_id, args.workspace, args.binding_file)
            print("Workspace binding 已保存。")
            return 0
        if args.command == "init":
            project = initialize(args.repo, args.binding_file, args.workspace_id, args.project_id,
                                 args.name, args.preserve_agents, args.adopt_existing_agents)
            print(encode({"project_id": project.project_id, "store": str(project.directory)}), end="")
            return 0
        project = resolve(args.repo, args.binding_file, getattr(args, "project", None))
        if args.command == "context":
            print(context(project))
        elif args.command == "doctor":
            issues = doctor(project)
            records = snapshot(project)
            from .store import events
            if len(events(project)) != records["sequence"]:
                issues.append("有未發布 checkpoint；執行 rebuild。")
            if any("resolved_by" not in c for c in records["conflicts"]):
                issues.append("有未解決 revision 衝突；先讀 snapshot 協調來源。")
            print(encode({"project_id": project.project_id, "store": str(project.directory),
                          "issues": issues, "sequence": records["sequence"]}), end="")
            return 1 if issues else 0
        elif args.command == "snapshot":
            print(encode(snapshot(project)), end="")
        elif args.command == "rebuild":
            print(encode({"sequence": rebuild(project)["sequence"]}), end="")
        elif args.command == "begin":
            print(encode(begin(project, args.provider, args.session, args.task, args.scope, args.takeover)), end="")
        elif args.command == "register":
            register(project.workspace, args.project_id, args.path, args.name)
            rebuild(project)
            print("Project 已登記，狀態為 not_bootstrapped。")
        elif args.command == "draft":
            current = snapshot(project)
            from .io import read_json
            runtime = read_json(session_path(project, args.provider, args.session), {})
            draft = {"schema_version": 1, "checkpoint_id": uuid.uuid4().hex,
                     "workspace_id": project.workspace_id, "project_id": project.project_id,
                     "provider": args.provider, "session_id": args.session, "created_at": now(),
                     "pending_turn": runtime.get("pending"),
                     "kind": "semantic", **git_facts(project.repo),
                     "completed": [], "in_progress": [], "attempts": [], "blockers": [],
                     "next_actions": [], "checks": [], "sources": [], "artifacts": [],
                     "base_entity_revisions": {k: v["revision"] for k, v in current["entities"].items()},
                     "task_updates": [], "decision_updates": [], "details_markdown": ""}
            atomic_json(Path(args.output), draft)
            print("Draft 已保存；先填寫語意紀錄，再用 checkpoint --input 提交。")
        elif args.command == "checkpoint":
            event = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
            receipt = checkpoint(project, event)
            print(encode(receipt), end="")
            return 2 if receipt["conflicts"] else 0
        return 0
    except (MemoryError, OSError, ValueError, KeyError) as exc:
        print("Shared memory：" + str(exc), file=sys.stderr)
        return 1
