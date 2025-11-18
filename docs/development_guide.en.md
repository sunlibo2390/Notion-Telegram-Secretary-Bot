# Development Guide

[Chinese Version](development_guide.md)

This guide details the interfaces, flows, configuration, and testing strategy that back the Telegram long-polling bot and Notion sync routine. Read `docs/developer_overview.md` first if you need the big picture, then return here for concrete contracts.

## 1. Interface Contracts

### 1.1 TelegramBotClient (`apps/telegram_bot/clients/telegram_client.py`)
```python
class TelegramBotClient:
    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[Update]: ...
    def send_message(self, chat_id: int, text: str, **kwargs) -> BotMessage: ...
    def send_photo(self, chat_id: int, photo: bytes | str, caption: str | None = None) -> BotMessage: ...
```
- `get_updates` wraps `https://api.telegram.org/bot{TOKEN}/getUpdates`, accepts `offset` + `timeout`, and returns parsed updates.
- Every `send_*` call must persist `resp["result"]` via `HistoryStore.append_bot`.
- Failures (network / 4xx / 5xx) raise `TelegramAPIError`; callers decide retry/backoff.

### 1.2 HistoryStore (`apps/telegram_bot/history/history_store.py`)
```python
class HistoryStore:
    def append_user(self, update: Update) -> None: ...
    def append_bot(self, message: BotMessage) -> None: ...
    def get_history(self, chat_id: int, limit: int = 50) -> list[HistoryEntry]: ...
    def last_update_id(self) -> int | None: ...
```
- Fields per entry: `timestamp`, `chat_id`, `message_id`, `direction`, `text`, `entities`, `reply_to_message_id`.
- Recommended storage: `data_pipeline/storage/telegram_history/{chat_id}.jsonl` + `metadata.json` for `last_update_id`; can be swapped with SQLite later.
- `append_*` must be idempotent (same `message_id` should not be written twice).

### 1.3 Repositories (`core/repositories`)
- `TaskRepository`: `list_active_tasks()`, `get_task(task_id)`.
- `LogRepository`: `list_logs(from_date, to_date)`, `create_log(text, related_task_id)`.
- `ProjectRepository`: `list_active_projects()`.
All repositories read from `data_pipeline/storage/processed/*.json` plus local custom-task caches.

### 1.4 Services & Workflows
- `TaskSummaryService.build_today_summary()` aggregates tasks, schedules, persona tags for the LLM tool `summarize_tasks`.
- `StatusGuard.evaluate()` returns `[Intervention]` items to decide proactive escalations.
- `LogbookService.record_log(raw_text)` parses `#log...` directives or LLM-generated drafts.
- `DailyBriefingWorkflow.run(chat_id)` runs when the agent selects the `generate_briefing` tool.

### 1.5 LLM Agent Contracts (`core/llm`)
- `AgentContextBuilder.build(chat_id, latest_update)` merges persona, profile, conversation history, repositories, and the incoming text into prompt fragments.
- `ToolRegistry.register(name, schema, executor)` exposes each skill to the LLM.
- `AgentLoop.run(chat_id, user_input)`:
  1. Build context and call OpenAI Chat Completions (with function calling).
  2. When the model emits a tool call, execute the executor and record the observation.
  3. Feed the observation back and continue until the assistant returns a final answer or the loop hits the cap.
  4. Return the final text, tool usage, and token stats.

## 2. Scenario Flows

### 2.1 Daily Briefing
1. Scheduler triggers `AgentLoop.run(chat_id, "/today")`.
2. The agent chooses whether to invoke `summarize_tasks`, `generate_briefing`, `status_guard`, etc.
3. The LLM assembles tone + action items according to the persona.
4. Telegram client sends the response and persists it.

### 2.2 Evening Review
1. Scheduler calls the agent with a “review” intent.
2. Agent fetches tasks/logs via `TaskSummaryService` and `LogRepository` tools.
3. The LLM may push the user to write missing logs or even draft them through `record_log`.

### 2.3 Real-Time Interventions
1. `StatusGuard.evaluate` inspects processed datasets (stale tasks, procrastination, etc.).
2. Agent receives `[Intervention]` objects and decides tone/follow-ups.

### 2.4 Commands & Free Text
1. Handlers no longer distinguish slash commands from free text; everything goes through the agent after minimal preprocessing.
2. The agent invokes tools for data needs, or responds directly for conversational outputs.

### 2.5 `#log` Entries
1. Handler detects `text.startswith("#log")`.
2. `LogbookService` parses date/task markers (regex + optional LLM assist).
3. Writes to Notion (or queues for later sync) and returns status to Telegram.

## 3. Configuration & Deployment

### 3.1 Notion Database Fields
Ensure the following properties exist (same as the README table):

#### Tasks
| Field | Type | Notes |
| --- | --- | --- |
| `Name` | title | Task name |
| `Priority` | select | Sorting + urgency |
| `Status` | status | Filter out Done/Dormant |
| `Projects` | relation | `/tasks group` relies on this |
| `Due Date` | date | Deadline for `/next` |
| `Subtasks` | relation | Used to render subtask names |

#### Projects
| Field | Type | Notes |
| --- | --- | --- |
| `Name` | title | Project title |
| `Status` | status | Only active projects remain |

#### Logs
| Field | Type | Notes |
| --- | --- | --- |
| `Name` | title | Log title |
| `Status` | status | Filter done/dormant |
| `Task` | relation | Show related task when printing logs |

### 3.2 `config/settings.toml`
```toml
[paths]
data_dir = "D:/Projects/codex_test/notion_secretary/databases"
database_ids_path = "database_ids.json"

[notion]
api_key = "secret_xxx"
sync_interval = 1800
force_update = false
api_version = "2022-06-28"

[telegram]
token = "8096:ABCDEF"
admin_ids = [6604771431]
poll_timeout = 25

[llm]
provider = "openai"
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
temperature = 0.3
api_key = "sk-..."
```
- Default path is `config/settings.toml`; override by setting `SECRETARY_CONFIG`.
- `database_ids.json` stores Tasks/Logs/Projects IDs.
- `data_dir` hosts `raw_json/`, `json/`, and `telegram_history/`.

### 3.3 Run Order
1. `python scripts/sync_databases.py --force`
2. `python scripts/run_bot.py`
   - Loads config, initializes repositories/services/client.
   - Executes `while True` long-poll loop with `offset=last_update_id+1`.
3. Use `pm2`, `supervisor`, or `systemd` for daemonization if needed.

### 3.4 Long-Poll Tips
- Telegram recommends `timeout <= 50s`; we use ~25s.
- Sleep 1-2s when `getUpdates` returns empty to avoid hammering.
- Persist `last_update_id` before shutdown to prevent duplicates.

## 4. Testing Strategy

### 4.1 Unit Tests
| Module | Coverage |
| --- | --- |
| `HistoryStore` | append/de-dup/history ordering. |
| `TelegramBotClient` | Use `responses`/`pytest-httpx` to test error handling + append_bot. |
| `TaskSummaryService` | Priority sorting & empty states. |
| `StatusGuard` | Intervention generation. |
| `LogbookService` | `#log` parsing and edge cases. |
| `AgentLoop` | Tool-calling loops, retries, max round enforcement. |

### 4.2 Integration Tests
- Mock Telegram server (or `responses`) to simulate `getUpdates` + `sendMessage`.
- Use sample `processed_tasks.json` to run `DailyBriefingWorkflow` end-to-end.

### 4.3 Regression Tests
- Provide a dry-run mode for `scripts/sync_databases.py` when touching Notion code.
- In CI, run `pytest tests/apps/telegram_bot` + `pytest tests/core` with mocked OpenAI.

---
By following these contracts, collaborators can extend the bot without breaking long-polling, history stitching, or tool protocols.
