"""新 project 初始化；已有入口需要明確接入，保留原文。"""

import uuid
from pathlib import Path

from .io import MemoryError, atomic_json, atomic_write, digest, now, read_json, safe_id
from .registry import Project, bind, bindings_path, register, resolve
from .store import checkpoint


def agents_template(canonical):
    return (f"# AGENTS.md\n\n本 project 嘅規則唯一來源係 `{canonical}`。\n"
            f"開始工作前先讀 `{canonical}`；新增或修改 project 規則只改該文件。\n"
            "本檔只作載入入口，唔喺本檔新增工作規則。\n"
            "若 canonical 文件缺失，先按 shared project memory 初始化流程修復。\n")


def initialize(repo, binding_file=None, workspace_id=None, project_id=None, name=None,
               preserve_agents=False, adopt_agents=False):
    root = Path(repo).expanduser().resolve()
    if not root.is_dir():
        raise MemoryError("Init 目錄必須已存在。")
    if (root / ".ai-project.json").exists():
        return resolve(root, binding_file)
    registry = root / ".ai-memory/registry.json"
    if registry.exists():
        raise MemoryError("已有 memory registry，唔覆蓋；先修復 project metadata。")
    candidates = [p.name for p in root.iterdir() if p.name.lower() == "claude.md"]
    if not candidates and (root / ".claude").is_dir():
        candidates = [".claude/" + p.name for p in (root / ".claude").iterdir() if p.name.lower() == "claude.md"]
    if len(candidates) > 1:
        raise MemoryError("有多份大小寫不同嘅 canonical 候選檔案，先確認權威來源。")
    canonical = candidates[0] if candidates else "CLAUDE.md"
    agents = root / "AGENTS.md"
    if agents.exists() and not preserve_agents and not adopt_agents:
        raise MemoryError("已有 AGENTS.md；先讀內容，再明確 --adopt-existing-agents 或保留既有入口。")
    workspace_id = workspace_id or "workspace-" + uuid.uuid4().hex[:16]
    project_id = project_id or workspace_id + ".workspace"
    safe_id(workspace_id)
    safe_id(project_id)
    bindings = read_json(bindings_path(binding_file), {"workspaces": {}})["workspaces"]
    if workspace_id in bindings and Path(bindings[workspace_id]).resolve() != root:
        raise MemoryError("Workspace ID 已綁定另一個 store；子 project 用 register，搬位置用 bind。")
    title = name or root.name
    policy = "python3 ~/.local/share/shared-project-memory/memoryctl"
    if not (root / canonical).exists():
        original = agents.read_text() if adopt_agents and agents.exists() else ""
        atomic_write(root / canonical, original + ("\n\n" if original else "") +
                     f"# {title}\n\n## Shared project memory\n\n"
                     f"- 開始工作先行 `{policy} context --repo .`，讀 project 狀態同相關 tasks。\n"
                     "- 本檔係 project 規則唯一來源；改規則只改本檔。\n"
                     "- 每個有意義步驟同完成一輪前，提交包含結果、理由、來源同下一步嘅 checkpoint。\n"
                     "- 先讀已有 code 同文件再填寫目標、build 指令同驗證方法；唔推斷部署狀態。\n")
    if not agents.exists() or adopt_agents:
        atomic_write(agents, agents_template(canonical))
    ignore = root / ".gitignore"
    text = ignore.read_text() if ignore.exists() else ""
    if ".ai-memory/.runtime/" not in text.splitlines():
        atomic_write(ignore, text.rstrip("\n") + "\n\n# Shared memory 短期鎖同 session 狀態\n.ai-memory/.runtime/\n")
    atomic_json(registry, {"schema_version": 1, "workspace_id": workspace_id,
                "canonical_rules": canonical, "projects": {}})
    register(root, project_id, ".", title, status="bootstrapped", metadata=True,
             canonical_rules=canonical, agents_hash=digest(agents.read_text()))
    bind(workspace_id, root, binding_file)
    project = Project(root, project_id, root)
    checkpoint(project, {"schema_version": 1, "workspace_id": workspace_id,
               "project_id": project_id, "checkpoint_id": "initialization-" + uuid.uuid4().hex,
               "provider": "memoryctl", "session_id": "bootstrap", "created_at": now(),
               "kind": "bootstrap", "base_entity_revisions": {"state": 0},
               "state_update": {"objective": f"{title}：目標待工作 agent 根據用戶要求填寫。",
                                "stage": "initialized", "verification": "reported"},
               "completed": ["建立 project ID、規則入口同 memory store。"],
               "details_markdown": "初始化只確認檔案存在，未驗證研究結論、code 測試或 runtime。"})
    return project
