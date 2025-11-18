# 开发者概览

[English Version](developer_overview.en.md)

本文总结 Notion Secretary 的当前架构、运行流程与约定。它与 `README.md`、`docs/development_guide.md`、`docs/user_manual.md` 互补，帮助你理解子系统之间如何协作、数据如何在流水线中流动，以及扩展功能时必须遵守的约束。

---

## 1. 顶层结构

```
notion_secretary/
├── apps/telegram_bot/        # Telegram 入口（bot、handlers、tracker、历史存储）
├── core/                     # 领域模型、仓库、服务、LLM 工具
├── data_pipeline/            # Notion 抽取/处理/转换/存储
├── docs/                     # 用户手册、开发文档、画像
├── infra/                    # 配置加载、Notion 同步调度
├── scripts/                  # 常用脚本（run bot / sync databases）
├── tests/                    # 单元 / 集成测试
└── databases/                # 运行期数据（raw_json/json/telegram_history/tracker）
```

关键惯例：
- 所有外部凭证（Telegram / Notion / LLM / WeCom）通过 `config/settings.toml` 或环境变量提供，绝不硬编码。
- Telegram Bot 以 **单进程长轮询** 运行，耗时任务（如 Notion 同步）必须在后台线程执行，避免阻塞命令处理。
- 数据采集 → 处理 → 缓存 的流程完全确定性：Collector 拉取 → Processor 生成结构化 JSON → Repository 读取；其他组件不得直接访问 Notion。
- 时区在 `[general].timezone_offset_hours` 配置（默认 8=UTC+8），`format_beijing` / `to_beijing` 等工具会自动使用该偏移。

---

## 2. 数据流水线

### 2.1 Collectors (`data_pipeline/collectors`)
- `NotionCollector` 负责读取 API Key、数据库 ID、存储目录以及更新策略（`duration_threshold_minutes`、`sync_interval_seconds`）。
- `update_needed()` 结合 `databases/last_updated.txt` 判断是否要重新拉取，避免频繁请求。
- `collect_once()` 逐个数据库抓取 → 将原始 JSON 写到 `databases/raw_json` → 调用 Processor → 更新 `last_updated`。

### 2.2 Processors (`data_pipeline/processors`)
- `ProjectsProcessor`: 过滤已完成项目，仅保留必要元数据。
- `TasksProcessor`: 关联项目、补齐 `page_url`、抓取块内容、解析子任务并生成 Markdown 文本。
- `LogsProcessor`: 解析块内容、关联任务、仅保存活跃日志。
- 所有 Processor 只处理本地文件（`raw_json → json/processed_*.json`），绝不直接调用 Telegram/LLM。

### 2.3 存储辅助
- `data_pipeline/storage/paths.py` 统一路径，`paths.configure()` 让脚本与运行时共用同一目录。
- `database_collect.py` 是 CLI 入口（`python scripts/sync_databases.py --force`）。

---

## 3. Telegram Bot 架构

### 3.1 入口 (`apps/telegram_bot/bot.py`)
- `build_runtime()` 读取配置、实例化仓库/服务、创建 Telegram Client。
- `TaskTracker` 使用 `history_dir/tracker_entries.json` 持久化，保证重启后跟踪恢复。
- `/update` 触发的 Notion 同步改为后台线程，不再阻塞主 loop。
- `BotRuntime.run_forever()` 负责长轮询；命令处理同步执行，耗时逻辑需自行开线程。

### 3.2 CommandRouter (`apps/telegram_bot/handlers/commands.py`)
- 所有命令 / 自然语言都会先尝试命令匹配，否则进入 LLM Agent。
- 关键命令：
  - `/trackings`：列出所有跟踪，包括“下次提醒时间”（只给有 Notion URL 的任务加链接）。
  - `/track <task> [minutes]`：≥5 分钟即可；若提醒落在休息块内才会顺延，否则保留原时间。
  - `/tasks` 及 `light/group light/delete`：自建任务 `page_url=None`，可批量删除。
  - `/logs`：纯文本输出以防 Telegram Markdown 解析失败；`/logs delete <indices...>` 可批量删除。
  - `/blocks`：休息/任务时间块；`/board` 与 `/next` 共用渲染逻辑。

### 3.3 主动 & Tracker 服务
- `ProactivityService` 基于 `state_*` 配置轮询状态、决定是否追问。
- `TaskTracker` 维护 `TrackerEntry`（`task_id`, `interval_minutes`, `next_fire_at`, `rest_resume_at`），并在 `history_dir/tracker_entries.json` 中持久化。

---

## 4. LLM Agent
- `AgentContextBuilder` 聚合 persona、用户画像、最近历史、任务/日志/项目摘要以及本次输入，生成 prompt。
- `AgentLoop` 负责 call OpenAI Chat Completions（带 tool calling）：若模型返回 `tool_call`，执行对应服务并把 observation 写回上下文，直到产出最终答复或达到最大回合。
- 已注册的技能包括任务摘要、日志写入、状态评估、briefing 生成等，扩展需在 `core/llm/tools.py` 注册。

---

## 5. 数据与日志持久化
- Telegram 历史：`databases/telegram_history/<chat_id>.jsonl` + `metadata.json`（记录 `last_update_id`）。
- Tracker 状态：`history_dir/tracker_entries.json`。
- Notion 同步时间：`databases/last_updated.txt`。
- 运行日志：`logs/*.log`，需注意敏感内容。

---

## 6. 主场景示例
1. **Daily Briefing**：调度器触发 → Agent 调用 `summarize_tasks` / `generate_briefing` → 推送总结与行动要求。
2. **Evening Review**：结合任务/日志状态提醒未完成事项，可直接生成日志草稿。
3. **强制干预**：`StatusGuard` 输出风险 → LLM 决定语气、是否设追问。
4. **常规命令**：`/tasks`、`/next`、`/trackings` 等先由 CommandRouter 处理；自由文本交给 Agent。
5. **休息/时间块**：`/blocks` 定义勿扰期间，Tracker/Proactivity 均会避开。

---

## 7. 测试与调试
- `tests/apps/telegram_bot/`：HistoryStore、CommandRouter、Tracker。
- `tests/core/`：LLM agent & tools。
- `tests/data_pipeline/`：Processor 与路径拼装。
- 修改跟踪/命令逻辑时务必补测试，确保提醒时间与渲染一致。

---

## 8. 扩展清单
1. 判断改动属于数据同步还是运行交互，保持分层。
2. 新增命令：
   - 逻辑放在 `CommandRouter`，必要时拆分 service。
   - 输出前使用 `escape_md` 或纯文本避免 Telegram 400。
   - 耗时逻辑放入线程或调度任务。
3. 修改跟踪：更新 `TrackerEntry`、持久化与测试。
4. 更新用户可见行为时，同步修改 README 与 User Manual。

保持以上约定，贡献者即可在不破坏现有行为的情况下扩展 Secretary。如需大幅调整架构，请在本文件追加说明，便于后来者理解动机与新约束。
