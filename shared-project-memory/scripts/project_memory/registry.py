"""固定 project ID 同本機 canonical workspace binding。"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .io import MemoryError, atomic_json, locked, read_json, safe_id


def bindings_path(override=None):
    return Path(override or os.environ.get("SHARED_PROJECT_MEMORY_BINDINGS") or
                Path.home() / ".config/shared-project-memory/registry.json").expanduser()


def bind(workspace_id, root, binding_file=None):
    path = bindings_path(binding_file)
    with locked(path.with_suffix(".lock")):
        data = read_json(path, {"schema_version": 1, "workspaces": {}})
        data["workspaces"][safe_id(workspace_id)] = str(Path(root).resolve())
        atomic_json(path, data)


def git_facts(repo):
    def run(*args):
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                                text=True, timeout=3)
        return result.stdout.strip() if result.returncode == 0 else None
    try:
        root = run("rev-parse", "--show-toplevel")
        if not root:
            return {"repo": str(Path(repo).resolve()), "branch": None, "head": None, "dirty_paths": []}
        status = run("status", "--porcelain", "--untracked-files=normal") or ""
        return {"repo": root, "branch": run("branch", "--show-current"),
                "head": run("rev-parse", "HEAD"), "dirty_paths": status.splitlines()}
    except (subprocess.TimeoutExpired, OSError):
        return {"repo": str(repo), "branch": None, "head": None, "dirty_paths": [],
                "git_observation": "unavailable"}


@dataclass(frozen=True)
class Project:
    workspace: Path
    project_id: str
    repo: Path

    @property
    def registry(self):
        return read_json(self.workspace / ".ai-memory/registry.json")

    @property
    def workspace_id(self):
        return self.registry["workspace_id"]

    @property
    def entry(self):
        return self.registry["projects"][self.project_id]

    @property
    def directory(self):
        return self.workspace / ".ai-memory/projects" / safe_id(self.project_id)

    @property
    def runtime(self):
        return self.workspace / ".ai-memory/.runtime" / safe_id(self.project_id)

    @property
    def lock(self):
        return self.runtime / "project.lock"


def resolve(repo, binding_file=None, project_id=None):
    repo = Path(repo).expanduser().resolve()
    if not repo.is_dir():
        raise MemoryError("Repo 路徑不存在。")
    bindings = read_json(bindings_path(binding_file), {"workspaces": {}})["workspaces"]
    for directory in (repo, *repo.parents):
        meta = read_json(directory / ".ai-project.json")
        if not meta:
            continue
        root = bindings.get(meta["workspace_id"])
        if not root:
            raise MemoryError("此 workspace 未有本機 binding；先執行 memoryctl bind，唔建立副本。")
        workspace = Path(root).resolve()
        registry = read_json(workspace / ".ai-memory/registry.json")
        if not registry or registry["workspace_id"] != meta["workspace_id"]:
            raise MemoryError("Canonical workspace binding 已失效。")
        selected = project_id or meta["project_id"]
        # Parent session 進入未有薄入口嘅策略時，揀最接近嘅已登記路徑。
        if not project_id:
            matches = []
            for ident, entry in registry["projects"].items():
                target = (workspace / entry["path"]).resolve()
                if repo == target or target in repo.parents:
                    matches.append((len(target.parts), ident))
            if matches:
                selected = max(matches)[1]
        if selected not in registry["projects"]:
            raise MemoryError("Project ID 唔喺 workspace registry 入面。")
        # 已複製 metadata 嘅外置 worktree，repo 用該 metadata 所在目錄。
        checkout = directory if selected == meta["project_id"] else workspace / registry["projects"][selected]["path"]
        return Project(workspace, safe_id(selected), checkout.resolve())
    raise MemoryError("UNREGISTERED：此目錄未有 .ai-project.json；新 project 可執行 memoryctl init。")


def register(root, project_id, path, name, status="not_bootstrapped", metadata=False,
             canonical_rules=None, agents_hash=None):
    root = Path(root).resolve()
    target = (root / path).resolve()
    if target != root and root not in target.parents:
        raise MemoryError("初次 register 嘅路徑必須喺 workspace 入面。")
    safe_id(project_id)
    with locked(root / ".ai-memory/.runtime/registry.lock"):
        registry = read_json(root / ".ai-memory/registry.json")
        if not registry:
            raise MemoryError("先初始化 workspace。")
        entry = {"name": name, "path": str(target.relative_to(root)) or ".",
                 "kind": "git_repo" if (target / ".git").exists() else "directory",
                 "status": status, "canonical_rules": canonical_rules}
        if agents_hash:
            entry["agents_template_sha256"] = agents_hash
        registry["projects"][project_id] = entry
        atomic_json(root / ".ai-memory/registry.json", registry)
        if metadata:
            atomic_json(target / ".ai-project.json", {"schema_version": 1,
                        "workspace_id": registry["workspace_id"], "project_id": project_id,
                        "canonical_rules": canonical_rules})


def doctor(project):
    issues = []
    meta = read_json(project.repo / ".ai-project.json")
    if not meta:
        issues.append("尚未 bootstrap：缺少 project metadata。")
        return issues
    rules = meta.get("canonical_rules")
    if rules != project.entry.get("canonical_rules"):
        issues.append("Metadata 同 registry 嘅 canonical 規則指向不一致。")
    path = project.repo / (rules or "CLAUDE.md")
    if not rules or not path.is_file() or path.name not in {p.name for p in path.parent.iterdir()}:
        issues.append("Canonical 規則文件缺失或大小寫不一致。")
    agents = project.repo / "AGENTS.md"
    expected = project.entry.get("agents_template_sha256")
    from .io import digest
    if not agents.is_file():
        issues.append("缺少 AGENTS.md 入口。")
    elif expected and digest(agents.read_text()) != expected:
        issues.append("AGENTS.md 偏離已登記入口；新工作規則請移至 canonical 文件，保留新增原文。")
    if path.is_file() and "@AGENTS.md" in path.read_text():
        issues.append("Canonical 文件反向 import AGENTS.md，可能循環指向。")
    return issues
