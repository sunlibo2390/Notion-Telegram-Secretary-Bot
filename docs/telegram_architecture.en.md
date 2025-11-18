# Telegram Bot Architecture

[Chinese Version](telegram_architecture.md)

## Background & Constraints
- The bot currently talks to users via Telegram mobile/desktop/web clients.
- We do **not** expose a public webhook yet, so long polling (`getUpdates`) handles message retrieval. Switching to webhooks later only requires swapping the transport layer.
- `getUpdates` returns user messages only. After every `sendMessage`/`sendPhoto`, persist the returned `message` object so the history contains both directions.

## Runtime Topology
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

## Module Overview

| Path | Description |
| --- | --- |
| `apps/telegram_bot/bot.py` | Entrypoint that builds `TelegramBotClient` and starts the long-poll loop. |
| `apps/telegram_bot/clients/telegram_client.py` | HTTP wrapper for the Bot API (retry/error handling + history persistence). |
| `apps/telegram_bot/history/history_store.py` | Persists both user updates and bot replies (JSONL or SQLite). |
| `apps/telegram_bot/handlers/` | Command router + agent bridge. |
| `apps/telegram_bot/dialogs/context_builder.py` | Builds the LLM prompt (history + Notion state + persona). |
| `core/llm/agent.py` | Tool-enabled Chat Completions loop. |
| `core/services/*` | Skills callable by the LLM (task summary, logbook, interventions...). |
| `core/workflows/daily_briefing.py` | Workflow that can be triggered by the agent. |
| `infra/scheduler/` | Optional APScheduler/cron hooks for proactive pushes. |
| `prompts/` | Persona, tool descriptions, system prompts. |

Jupyter prototypes from early experiments were merged into the client implementation, so `telegram_client.py` shows the minimal send/get logic.

## Conversation History Management
1. **Fetch user messages**: call `getUpdates(offset=last_update_id+1)` and append each user entry to `HistoryStore`. Mark `update_id` as consumed immediately.
2. **Send bot messages**: always go through `TelegramBotClient.send_message`, capture `resp["result"]`, and persist it. Suggested schema:
   ```python
   class TelegramBotClient:
       def send_message(self, chat_id, text, **kwargs):
           resp = requests.post(self.base_url + "/sendMessage", data={...})
           resp.raise_for_status()
           message = resp.json()["result"]
           self.history_store.append_bot(message)
           return message
   ```
   Fields to keep: `timestamp`, `chat_id`, `message_id`, `direction`, `text`, `entities`, `reply_to_message_id`.
3. **Rebuild context**: `history_store.get_history(chat_id, limit)` merges user/bot entries sorted by timestamp so prompts, visualization, and debugging see the same transcript.
4. **Persistence layer**: default is JSONL under `data_pipeline/storage/telegram_history`. Migrate to SQLite/Postgres when serving many users.

## LLM Secretary Agent
1. `context_builder` assembles `[system persona] + [user_profile] + [recent history] + [tasks/logs/projects snapshot] + [current input]`.
2. Agent calls OpenAI (e.g., `gpt-4o-mini`) with tool descriptions such as `summarize_tasks`, `enforce_focus`, `record_log`, `generate_briefing`, `query_memory`.
3. When the model emits `tool_call`, execute the mapped function in `core/services`, capture the observation, and continue the loop.
4. Every assistant reply is persisted; when tools change Notion data, processors pick it up during the next sync.

## Core Scenarios
- **Daily Briefing / Evening Review**: Scheduler triggers a workflow → agent composes summaries and action items → Telegram delivers the tone dictated by the persona.
- **Real-time monitoring**: `StatusGuard` exposes anomalies; the agent decides whether to threaten, cajole, or set reminders.
- **Commands & free text**: Slash commands (e.g., `/tasks`) are handled directly by `CommandRouter`; unrecognized inputs fall back to the agent.
- **Log capture**: Agent interprets user text, calls `LogbookService`, and returns success/failure.
- **Multi-turn coaching**: Agent may request more details, set timers, or leverage persona tags stored in `docs/user_profile_doc*.md`.

## Long-Poll Reliability
- Use `while True` + `sleep` loop; set the `offset` after each batch to avoid duplicates.
- Record the last successful poll timestamp in `logs/telegram_bot.log` for debugging.
- For multiple workers, store `offset` in Redis/DB so only one consumer processes updates.

## Future Upgrades
- **Webhook mode**: expose an HTTPS endpoint (server or cloud function) and reuse the same handlers.
- **Message queue**: decouple Notion events, LLM requests, and Telegram sends for higher throughput.
- **History persistence**: plug a vector DB to retrieve historical interventions when building context.

With these modules and history practices, the bot can rebuild accurate conversations even though Telegram doesn’t return bot messages by default, ensuring reliable context for the secretary persona.
