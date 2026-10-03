# Shared Project Memory

讓 **Claude Code 與 Codex 共用專案進度、決策及交接紀錄**的可移植 Skill 與 Python 工具。適用於單一專案，也適用於一個工作區內包含多個獨立 Git repo 的結構。

Agent 開始工作時讀取同一份記憶；完成有意義的步驟時提交 checkpoint；另一個 agent 接手時，從持久化紀錄了解已完成事項、證據、阻礙與下一步。

本 repo 提供機制及安裝流程。**安裝 Skill、初始化專案、安裝全域 hooks 是三個不同步驟**；只下載 Skill 並不會立即啟用 hooks。

## 目錄

- [功能與設計](#功能與設計)
- [系統需求](#系統需求)
- [快速開始](#快速開始)
- [已有規則的專案](#已有規則的專案)
- [其他專案與子專案](#其他專案與子專案)
- [日常工作與交接](#日常工作與交接)
- [Hooks 與自動保存](#hooks-與自動保存)
- [同時工作與衝突](#同時工作與衝突)
- [儲存位置與版本控制](#儲存位置與版本控制)
- [驗證與測試](#驗證與測試)
- [疑難排解](#疑難排解)
- [更新與回退](#更新與回退)
- [支援範圍與授權](#支援範圍與授權)

## 功能與設計

| 元件 | 用途 |
| --- | --- |
| Skill | 教導 agent 初始化、讀取、保存、交接及維護規則 |
| `memoryctl` | 管理記憶、產生 context、保存 checkpoint、檢查及重建狀態 |
| `onboard.py` | 保留現有規則，建立專案身份與入口；支援子專案 |
| Canonical 規則檔 | 專案規則的單一權威來源，通常為 `CLAUDE.md` |
| `AGENTS.md` | Codex 的載入入口，指向 canonical 規則檔 |
| `.ai-project.json` | 固定 workspace／project ID，以及規則位置 |
| `.ai-memory/` | 工作區的 canonical memory store；包含事件、狀態、任務及決策 |
| 全域 hooks | 在已註冊專案載入 context、追蹤本輪保存狀態並處理漏存 |

主要特性：

- Claude Code 與 Codex 讀寫相同格式的本機檔案。
- 以 append-only events 保留歷史；產生可閱讀的狀態、任務、決策與 session 紀錄。
- 以實體 revision 檢查更新衝突，避免較舊狀態覆蓋另一個 agent 的成果。
- 原 checkout 與外置 Git worktree 可透過固定 ID 共用同一份記憶。
- 安裝器保留其他 hooks、設定與規則，修改前備份既有內容。
- 不需要資料庫服務、模型 API 呼叫或 API key。

這套機制保存的是整理過的工作記憶，不會自動匯入完整聊天紀錄。歷史記憶也不會賦予 agent 新的執行授權。

## 系統需求

- macOS 或 Linux。
- Python 3.10 或以上；runtime 僅使用 standard library。
- 使用 Git／worktree 功能時需安裝 Git。
- 使用自動 hooks 時，需有支援相關 lifecycle events 的 Claude Code／Codex runtime。
- 從 Private GitHub repo 下載時，帳戶需有讀取權限。

目前使用本機 `fcntl` file locks；Windows 與跨機同時寫入尚未支援。

## 快速開始

### 1. 下載套件

```bash
git clone https://github.com/Mattcryptohk/shared-project-memory.git
cd shared-project-memory
```

也可以從 GitHub 下載 ZIP。以下指令均假設目前位於此 repo 根目錄；請將範例路徑換成自己的實際路徑。包含空格的路徑必須加引號。

### 2. 讓 agent 使用 Skill

Skill 位於 [`shared-project-memory/SKILL.md`](shared-project-memory/SKILL.md)。可以直接將此檔案的絕對路徑交給 agent，要求它依照流程接入專案。

若要安裝為個人 Skill，可以將整個 `shared-project-memory/` 子目錄放入 provider 的 skills 目錄，例如：

```text
~/.codex/skills/shared-project-memory/
~/.claude/skills/shared-project-memory/
```

複製時需保留 `scripts/`、`references/` 與 `agents/`。目標已存在時，先核對版本與本地修改再更新，避免產生多層巢狀目錄。新 session 再確認 Skill 已載入。

可直接向 agent 提出：

> 請使用 shared-project-memory Skill 將目前專案接入 Claude Code／Codex 共用記憶。先讀取並保留既有規則，預覽初始化變更，根據實際來源匯入進度；如果尚未安裝全域 hooks，完成安裝及驗證。

### 3. 初始化專案

對沒有既有 `AGENTS.md` 的專案，先預覽，再執行：

```bash
python3 shared-project-memory/scripts/onboard.py \
  --repo "/absolute/path/to/project" --dry-run

python3 shared-project-memory/scripts/onboard.py \
  --repo "/absolute/path/to/project"
```

初始化會建立或補充 canonical 規則、`AGENTS.md`、`.ai-project.json`、工作區 registry、本機 binding 與初始記憶。**專案目標及歷史進度需要後續根據來源整理**，工具不會猜測已完成工作或部署狀態。

同一身份的專案重複 onboarding 會回報已註冊，不會再次匯入歷史進度。專案資料夾必須已存在；工具不會自行建立 Git repo。

### 4. 安裝全域 runtime 與 hooks

每部電腦首次使用時：

```bash
python3 shared-project-memory/scripts/memoryctl install-user \
  --workspace "/absolute/path/to/project" --dry-run

python3 shared-project-memory/scripts/memoryctl install-user \
  --workspace "/absolute/path/to/project"
```

安裝器會合併 Claude／Codex 設定與全域入口，保留無關欄位及 handlers。實際修改清單、備份位置與安裝結果記錄於 `installation.json`。

Codex 需要審閱並 trust 新增的 hooks。CLI 可使用 `/hooks`；核對來源與 command 後完成審閱，再開啟新 session。修改 hook 定義後也可能需要重新審閱。Claude 設定完成後，同樣應在新 session 驗證實際觸發。

### 5. 檢查與首次交接

```bash
python3 ~/.local/share/shared-project-memory/memoryctl context \
  --repo "/absolute/path/to/project"

python3 ~/.local/share/shared-project-memory/memoryctl doctor \
  --repo "/absolute/path/to/project"
```

先讓一個 agent 根據現有文件保存一個明確 checkpoint，再讓另一個 provider 的全新 session 讀取同一段紀錄。完整驗證流程見 [validation.md](shared-project-memory/references/validation.md)。

## 已有規則的專案

新專案預設使用 `CLAUDE.md`；已有 `Claude.MD` 等大小寫不同的 canonical 文件會保留其真實檔名。沒有 Claude 規則檔也可由 Codex 先初始化。

若已有 `AGENTS.md`，helper 會要求先審閱原文。審閱 canonical 文件與 AGENTS 規則後，再執行：

```bash
python3 shared-project-memory/scripts/onboard.py \
  --repo "/absolute/path/to/project" \
  --adopt-existing-agents --dry-run

python3 shared-project-memory/scripts/onboard.py \
  --repo "/absolute/path/to/project" \
  --adopt-existing-agents
```

helper 會備份原文，將舊 AGENTS 內容保留於 canonical 文件，再建立載入入口。**文字保留不等於語意衝突已解決**；兩份文件有相反指示時，需要 agent 根據現行要求整合。canonical 文件反向引用 `@AGENTS.md` 或有多個候選檔案時，需先處理歧義。

接入後，規則修改集中於 metadata 指定的 canonical 文件。`AGENTS.md` 只作入口，避免兩邊各自維護一套規則。

## 其他專案與子專案

### 另一個獨立專案

全域 hooks 已安裝時，只需為新專案執行 onboarding：

```bash
python3 shared-project-memory/scripts/onboard.py \
  --repo "/absolute/path/to/Other Project" --dry-run

python3 shared-project-memory/scripts/onboard.py \
  --repo "/absolute/path/to/Other Project"
```

它會有自己的 ID 與 `.ai-memory/`，並新增本機 binding。**不需要為每個專案重新安裝全域 hooks**。若有既有 AGENTS，仍需按上一節處理。

### 大工作區內的子專案

先初始化父工作區，再指定子專案的 owning workspace：

```bash
python3 shared-project-memory/scripts/onboard.py \
  --repo "/absolute/workspace/strategies/My Strategy" \
  --workspace "/absolute/workspace" --dry-run

python3 shared-project-memory/scripts/onboard.py \
  --repo "/absolute/workspace/strategies/My Strategy" \
  --workspace "/absolute/workspace"
```

子專案有自己的身份與狀態，記憶集中在父工作區 `.ai-memory/`，不會另建一份 store。可用 `--project-id` 指定穩定 ID；同一 ID 已指向其他路徑時會拒絕覆蓋。

一般資料、課程或參考文件目錄可沿用父工作區記憶。只有需要獨立目標、backlog 或長期交接的目錄，才需要註冊成子專案。

## 日常工作與交接

正常情況下 agent 按規則與 hooks 執行以下流程，使用者不必每次手動要求 save：

1. 開始工作：讀 canonical 規則與 `context`，了解相關 tasks、decisions、來源及限制。
2. 有意義的進展：整理完成／未完成事項、理由、失敗嘗試、檢查結果、產物及下一步。
3. 保存：提交語意 checkpoint；只讀研究也應記錄，除非使用者明確禁止記憶寫入。
4. 交接：另一個 agent 開新 session，讀取同一 project ID 對應的記憶。

手動或排查時可以建立 draft：

```bash
python3 ~/.local/share/shared-project-memory/memoryctl draft \
  --repo "/absolute/path/to/project" \
  --provider codex --session ACTUAL_SESSION_ID \
  --output /tmp/checkpoint.json
```

由 agent 填寫 JSON，再提交：

```bash
python3 ~/.local/share/shared-project-memory/memoryctl checkpoint \
  --repo "/absolute/path/to/project" --input /tmp/checkpoint.json
```

Claude 使用 `--provider claude`。保留 draft 的 checkpoint ID、pending token 與實際 session ID；相同 payload 重試可去重。沒有 hook session 資訊時，使用自行建立的唯一 ID，並記錄 dispatch 尚未驗證。

檢查過才標記 `verified`；舊報告與未重驗 runtime 保持 `reported`。任務完成需區分 `research_documented`、`implemented_on_branch`、`validated_on_branch`、`merged` 及 `deployed_verified`。

## Hooks 與自動保存

| 事件 | Adapter 行為 |
| --- | --- |
| `SessionStart` | 載入已註冊專案 context |
| `UserPromptSubmit` | 建立本輪 pending marker 並提示保存規則 |
| `Stop` | 檢查語意 checkpoint；漏存時最多提醒 agent 自動繼續一次 |
| `PreCompact`／`SessionEnd` | 保存必要的未完成觀察 |
| Codex `Interrupt` | 記錄中斷時的未完成觀察 |

再次漏存時會保留 `incomplete` 事實與 warning，不會無限重試，也不會把未完成工作推斷為完成。

自動保存由 **agent 遵循規則 + runtime 實際觸發 hooks** 共同完成，不是背景定時同步服務。hooks 未 trust、被停用、尚未重新載入或平台不支援時，不能保證提醒會觸發。未知、未註冊目錄的 adapter 保持安靜。

平台行為以 [Codex hooks 文件](https://learn.chatgpt.com/docs/hooks)及 [Claude Code hooks 文件](https://code.claude.com/docs/en/hooks)為準。Adapter fixture tests 通過不代表所有版本及使用介面的真實 lifecycle 已通過。

## 同時工作與衝突

共用記憶可以讓兩個 agent 接手或並行工作；同時修改 code 仍應使用不同 branch／worktree，並記錄 task owner：

```bash
python3 ~/.local/share/shared-project-memory/memoryctl begin \
  --repo "/absolute/path/to/worktree" \
  --provider codex --session ACTUAL_SESSION_ID \
  --task task-id --scope src/module.py
```

原 checkout 與 worktree 透過同一身份解析到 canonical store。不要在同一 project 的 worktree 再建立新的 workspace 記憶。

更新 task、decision 或 state 時，使用最新 `base_entity_revisions`。遇到衝突會保留事件並回傳 receipt（exit code 2），衝突更新不覆蓋當前狀態；重新讀取 snapshot，協調後以新 checkpoint 解決。詳見 [操作文件](shared-project-memory/references/operations.md)。

Task claims 是合作式協調，不能防止其他程序修改檔案。claim 到期也不代表可以忽略原 session 的未完成修改直接接管。

## 儲存位置與版本控制

```text
本 repo/
├── README.md
├── PACKAGE-MANIFEST.json
└── shared-project-memory/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── references/
    └── scripts/
        ├── onboard.py
        ├── memoryctl
        └── project_memory/

專案或父工作區/
├── CLAUDE.md                  # 保留既有 canonical 檔名
├── AGENTS.md                  # 載入入口
├── .ai-project.json           # 穩定身份
└── .ai-memory/                # canonical store 與 views

本機使用者目錄/
├── .local/share/shared-project-memory/  # runtime 與 POLICY.md
├── .config/shared-project-memory/      # bindings、receipt、backups
├── .codex/hooks.json
└── .claude/settings.json
```

- 固定身份、專案規則及所需的 memory events／views 可由專案 Git 管理；工具不會自行 commit。
- `.ai-memory/.runtime/` 是本機 session／claim／lock 資料，應保持 Git ignored。
- 使用者全域設定與 binding 不應複製成其他人的機器設定。
- 不保存 secrets、API keys 或完整 raw transcripts；Private repo 也不應包含此類資料。
- Skill repo 只包含通用工具、指引及測試 fixtures；各專案的記憶留在其自己的 workspace。

## 驗證與測試

在套件 repo 根目錄執行：

```bash
python3 -m unittest discover \
  -s shared-project-memory/scripts/project_memory/tests -v
```

目前包含 27 項測試，涵蓋並行 writer、revision 衝突及解決、去重、中斷後重建、Git worktrees、只讀 checkpoint、漏存提醒次數上限、規則保留、重複安裝、子專案 routing 及 ID 衝突。

`PACKAGE-MANIFEST.json` 提供可發佈來源檔案的 SHA-256。修改來源後，應重新產生 manifest；它不包含自己或 Git metadata。

實際使用仍需完成 fresh-session 驗證：讓 provider A 保存唯一標記，由 provider B 的新 session 讀取；另外核對 pending marker、checkpoint 與 hook 事件。參閱 [完整驗證流程](shared-project-memory/references/validation.md)。

## 疑難排解

| 情況 | 處理方式 |
| --- | --- |
| Skill 看得到，但沒有自動讀寫 | 檢查 project onboarding、runtime 安裝、hooks trust／啟用與新 session 載入 |
| 出現 hooks need review | 核對本工具 command 與來源，完成 provider trust review |
| 有已保存事件但 view 尚未發佈 | 先 `doctor`，確認事件完整性後 `rebuild` |
| 規則入口 drift | 保留新增內容，將有效規則整合回 canonical 文件，再修復 AGENTS 入口 |
| 找不到 binding | 核對 workspace ID 及 canonical 路徑；不要另建同 ID 的第二份 store |
| workspace 搬位置 | 使用原 workspace ID 執行 `bind` 更新本機路徑 |
| revision conflict | 讀最新 snapshot，保留另一邊成果，再提交協調 checkpoint |
| 首次接入沒有詳細進度 | 正常；需要 agent 審閱來源後提交語意匯入紀錄 |

```bash
python3 ~/.local/share/shared-project-memory/memoryctl doctor --repo .
python3 ~/.local/share/shared-project-memory/memoryctl rebuild --repo .

python3 ~/.local/share/shared-project-memory/memoryctl bind \
  --workspace-id ORIGINAL_WORKSPACE_ID \
  --workspace "/new/canonical/path"
```

不要直接修改產生的 STATE／TASKS／DECISIONS、sessions 或舊 events。修正紀錄應用新 checkpoint；原始事件 hash 不一致時，先調查來源，不要直接強行重建。

## 更新與回退

更新套件前先保留本地修改。下載新版本、執行 tests，再預覽 `install-user --dry-run`；確認後安裝。新增專案只需 onboarding；升級 runtime 才需要重新安裝全域工具並重新驗證 hooks。

安裝器保留已有 `POLICY.md`，因此新版政策變更需另行審閱及整合，不會默默覆蓋使用者自訂規則。

回退時讀取 `~/.config/shared-project-memory/installation.json` 及對應 backups，只移除或還原本機制的 managed blocks／handlers，保留安裝後其他修改。不要整份覆蓋設定檔，也不要刪除既有 memory。移除 hooks 後，仍可用 repo-local `memoryctl` 讀取記憶。

## 支援範圍與授權

此版本是本機檔案機制；不提供跨機鎖、雲端同步服務、完整聊天匯入或模型行為保證。這個 Private repo 用於授權帳戶間分享及維護，尚未附上開源授權。若日後公開發布或授權第三方散佈，應先決定適用 license。

更多細節：

- [Skill 指引](shared-project-memory/SKILL.md)
- [安裝與 onboarding](shared-project-memory/references/setup.md)
- [CLI 與記憶操作](shared-project-memory/references/operations.md)
- [真實 lifecycle 與交接驗證](shared-project-memory/references/validation.md)
