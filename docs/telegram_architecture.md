# Telegram Bot 架构

[English Version](telegram_architecture.en.md)

## 背景与约束
- Bot 目前通过 Telegram 手机 / 桌面 / Web 客户端与用户交互。
- 尚未开放公网 webhook，因此采用 **long polling (`getUpdates`)** 拉取消息；后续若切换 webhook，只需替换传输层。
- `getUpdates` 只返回用户消息。每次 `sendMessage` / `sendPhoto` 后都要把 Telegram 返回的 `message` 对象持久化，才能拼出完整的对话历史。

## 运行拓扑
```
┌──────────────┐    ┌───────────────────┐    ┌─────────────────────┐    ┌─────────────────┐
│ data_pipeline│ -> │ repositories/memory│ -> │ LLM Agent (core/llm)│ -> │ apps/telegram_bot│
└──────────────┘    └───────────────────┘    └─────────────────────┘    └─────────────────┘
                                                          │                       │
                                                          ▼                       ▼
                                                skills/core/services      Telegram Bot API
                                                          │                       │
                                                          ▼                       ▼
                                               Notion updates / actions   Telegram Client (user)
```

## 模块划分

| 路径 | 说明 |
| --- | --- |
| `apps/telegram_bot/bot.py` | 入口脚本，构建 `TelegramBotClient` 并启动长轮询。 |
| `apps/telegram_bot/clients/telegram_client.py` | Bot API 封装，负责重试 / 错误处理 / 历史记录。 |
| `apps/telegram_bot/history/history_store.py` | 持久化用户 update 与 Bot 回复（JSONL 或 SQLite）。 |
| `apps/telegram_bot/handlers/` | 命令路由 + Agent 桥接层。 |
| `apps/telegram_bot/dialogs/context_builder.py` | 构建 LLM Prompt：历史 + Notion 状态 + 画像。 |
| `core/llm/agent.py` | 带工具调用的 Chat Completions loop。 |
| `core/services/*` | 供 LLM 调用的技能（任务摘要、日志、干预等）。 |
| `core/workflows/daily_briefing.py` | 可被 Agent 触发的工作流。 |
| `infra/scheduler/` | 可选的 APScheduler/cron 主动推送。 |
| `prompts/` | Persona、工具描述、系统提示词。 |

Jupyter 原型已经合并进正式客户端，可在 `telegram_client.py` 查看最小 `send/get` 实现。

## 对话历史管理
1. **拉取用户消息**：`getUpdates(offset=last_update_id+1)`，逐条写入 `HistoryStore` 并立刻标记 `update_id`。
2. **发送 Bot 消息**：统一走 `TelegramBotClient.send_message`，成功后记录 `resp["result"]`。推荐保存字段：`timestamp`, `chat_id`, `message_id`, `direction`, `text`, `entities`, `reply_to_message_id`。
3. **拼装上下文**：`history_store.get_history(chat_id, limit)` 将用户/机器人消息按时间排序，供 prompt、可视化与调试使用。
4. **持久化介质**：默认 `data_pipeline/storage/telegram_history/*.jsonl`，如需多用户可迁移到 SQLite/Postgres。

## LLM Secretary Agent
1. `context_builder` 组装 `[system persona] + [user_profile] + [history] + [tasks/logs/projects 摘要] + [当前输入]`。
2. Agent 调用 OpenAI（如 `gpt-4o-mini`），暴露 `summarize_tasks`、`enforce_focus`、`record_log`、`generate_briefing`、`query_memory` 等工具。
3. 模型输出 `tool_call` 时执行对应服务，记录 observation，再次进入循环。
4. 每条 Bot 回复都会持久化；工具若修改 Notion 数据，下一次同步会拾取最新结果。

## 核心场景
- **Daily Briefing / Evening Review**：调度器触发工作流 → Agent 生成总结与行动要求 → Telegram 以画像语气推送。
- **实时监控**：`StatusGuard` 暴露异常，Agent 决定是否讽刺/威胁或设置追问。
- **命令与自由文本**：`/tasks` 等命令由 `CommandRouter` 直接处理；无法匹配的输入回落到 Agent。
- **日志记录**：Agent 解析文本，调用 `LogbookService` 并回传结果。
- **多轮辅导**：可继续追问细节、设置倒计时、引用画像标签制定策略。

## 长轮询可靠性
- 使用 `while True` + `sleep` 循环；每批次处理完立即更新 `offset`。
- 记录最近一次成功轮询时间到 `logs/telegram_bot.log` 便于排障。
- 若多实例部署，可把 `offset` 存在 Redis/DB，保证只有一个 worker 消费。

## 未来升级
- **Webhook 模式**：在可公网访问的服务器暴露 HTTPS 端点，复用现有 handler。
- **消息队列**：解耦 Notion 事件、LLM 请求与 Telegram 发送，提高吞吐。
- **历史检索**：接入向量数据库，根据对话内容检索过去的干预片段，提升上下文质量。

借助上述模块与历史管理策略，即便 Telegram 默认不返回 Bot 消息，也能重建完整对话，为 Secretary 的场景化推理提供可靠上下文。
