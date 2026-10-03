# Shared project memory 操作

此工具讓 Claude Code 同 Codex 共用 project 工作紀錄。Python standard library，支援 macOS／Linux。規則以 project 指定嘅 canonical 文件為準。

## 開始工作

安裝後入口係 `python3 ~/.local/share/shared-project-memory/memoryctl`。下文用 `memoryctl` 表示該完整指令；安裝不會改 shell PATH。

```bash
python3 ~/.local/share/shared-project-memory/memoryctl context --repo .
python3 ~/.local/share/shared-project-memory/memoryctl doctor --repo .
```

策略工作將 `--repo` 指向策略 folder。原 checkout 同各個 worktree 透過 `.ai-project.json` 嘅 ID，從本機 `~/.config/shared-project-memory/registry.json` 找到同一份 canonical store。

新 project 冇規則檔時：

```bash
python3 ~/.local/share/shared-project-memory/memoryctl init --repo /absolute/project/path
```

Init 建立 `CLAUDE.md`、指向入口 `AGENTS.md`、project metadata、registry 同初始紀錄，唔會自行初始化 Git。已有 AGENTS.md 嘅 project 先讀原文，再決定遷移；`--adopt-existing-agents` 會保存原文到 canonical 文件，再建立 pointer。`--preserve-agents` 只供已確認現有入口正確嘅接入。

Workspace 搬位置之後，用 `bind --workspace-id <原ID> --workspace <新canonical路徑>` 更新本機 binding。唔喺 worktree 另做 init，亦唔將同一 workspace ID 綁去另一份 store。只有本機 file lock；跨機同時寫入要先建立跨機協調方案。

## 提交工作紀錄

Hook 會提供本次 provider 同 session ID。建立 draft：

```bash
python3 ~/.local/share/shared-project-memory/memoryctl draft --repo . --provider codex --session SESSION_ID --output /tmp/checkpoint.json
```

填寫 draft 嘅完成／未完成項目、嘗試、理由、檢查結果、來源、產物同下一步，再提交：

```bash
python3 ~/.local/share/shared-project-memory/memoryctl checkpoint --repo . --input /tmp/checkpoint.json
```

保留 draft 內 checkpoint ID、created_at 同 pending_turn；重試提交相同 payload 會去重。空白 draft 會拒絕保存。`dirty_paths` 只係當时 Git 狀態，唔表示全部由本 session 改動。

新增任務時，`task_updates` 加入 `{ "id": "task-id", "title": "任務內容", "status": "ready" }`，`base_entity_revisions` 加 `"task:task-id": 0`。更新已有 task 時，用 `snapshot --repo .` 或 context 提供嘅 revision。`done` 必須帶 `completion_scope`；等待用戶決定用 `blocked_user_decision`。

Project 目標／階段用 `state_update`，對應 revision key `state`；決策用 `decision_updates`，key 係 `decision:<id>`。Verified 更新需要成功 checks 或標明 verified 嘅來源。Git 狀態同測試 pass 本身唔代表已部署。

遇到 revision 衝突，receipt 會列兩邊來源，CLI exit code 2；保存紀錄保留，但衝突更新唔覆蓋現有狀態。重新讀 snapshot，按最新 revision 提交協調結果，再用 `resolves_conflicts` 指明 `{ "entity": "task:task-id", "checkpoint_id": "衝突checkpoint-id" }`。必須同時成功更新該實體先可以標記解決。

```bash
python3 ~/.local/share/shared-project-memory/memoryctl begin --repo . --provider codex --session SESSION_ID --task task-id --scope src/module.py
```

Task owner 有衝突會拒絕另一個 session claim。8 小時 expiry 只作重查提示；唔會默默接管。核實舊 session 同 dirty work 後先用 `--takeover`。Done／cancelled 成功更新會釋放該 owner 嘅 claim。Scope 係合作式紀錄；同時改 code 仍然用分開 worktree。

## Hooks 同恢復

全域 adapter 只處理已註冊 project，未知目錄保持安靜。SessionStart 載入 context；UserPromptSubmit 建立本輪 pending marker；Stop 檢查語意紀錄；PreCompact／SessionEnd／Codex Interrupt 保存未完成觀察。

缺 checkpoint 時，Stop 最多自動繼續一次提醒 agent 補記。同一輪仍失敗時保留 `incomplete` 事實紀錄同 warning，唔無限重試或推斷已完成。Transcript 內容唔會自動匯入。

Lifecycle API 及 trust 要按實際 runtime 驗證。[Codex hooks](https://learn.chatgpt.com/docs/hooks)；[Claude hooks](https://code.claude.com/docs/en/hooks)。Codex 要審閱及 trust 新 hook 定義；改過定義亦需要重新 review。CLI 可用 `/hooks`。全域設定修改唔代表目前已開嘅 session 即時重新載入。

Writer 先保存 append-only event，再生成同一代 views，最後 atomic 發布 `CURRENT.json`。發生儲存中斷後：

```bash
python3 ~/.local/share/shared-project-memory/memoryctl doctor --repo .
python3 ~/.local/share/shared-project-memory/memoryctl rebuild --repo .
```

Rebuild 保留 events 同歷史，重播後更新 views 同索引。若原始 event hash 不一致則拒絕重播，先核實被改動嘅紀錄。`.ai-memory/.runtime/` 有 session／claim／lock，Git ignore；原始事件、sessions、views 同 registry 可以由 workspace Git 版本保存。工具唔會自行 commit。

## 安裝及驗證

Repo 原始碼入口係 `python3 shared-project-memory/scripts/memoryctl`，可用 `--binding-file <JSON>` 指定便攜／測試 binding。

```bash
python3 shared-project-memory/scripts/memoryctl install-user --workspace . --dry-run
python3 shared-project-memory/scripts/memoryctl install-user --workspace .
python3 -m unittest discover -s shared-project-memory/scripts/project_memory/tests -v
```

Installer 保存共通 POLICY、兩個全域入口同 lifecycle adapter。原有設定欄位及其他 hooks 會保留；只更新本系統嘅 managed block。需要修改檔案時會先備份，receipt 喺 `~/.config/shared-project-memory/installation.json`。

回退時先讀 receipt 同 backup；只對照需要還原嘅 managed block／本系統 handlers。原檔若安裝後有其他修改，要保留那些修改再移除本系統入口。唔整份覆蓋其他新設定。既有 memory 仍可以用 repo-local CLI 讀取。

Automated tests 包括並行 writer、revision 衝突／解決、去重、crash recovery、真實 Git worktrees、read-only checkpoint、hooks bounded continuation、入口 drift、保留設定同重複安裝。這些係本地／adapter 驗證；真實 Claude → Codex → Claude 接手及 runtime trust 狀態另外記錄。
