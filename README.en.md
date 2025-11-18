# Notion Secretary

[中文版本 (Chinese Version)](README.md)

> Telegram-first assistant that mirrors Notion tasks/logs, persists user behavior, and keeps nudging through an LLM-driven control loop. Every command and follow-up goes through the Agent: the bot aggregates context, the model picks the proper skill, then the bot executes deterministically.

---

## 🌟 Key Features

| Capability | Description |
| --- | --- |
| Notion Sync | `database_collect.py` or `/update` pulls databases → processors normalize → repositories cache the result. |
| Telegram Bot | `/tasks`, `/logs`, `/track`, `/trackings`, `/board`, free-form chat; supports light views, batch delete, etc. |
| LLM Agent | `core/llm/agent.py` + `core/llm/tools.py` implement the ReAct/tool loop; every instruction is validated by the model. |
| Tracking Persistence | `TaskTracker` stores every tracking entry in `history_dir/tracker_entries.json` and restores it after restarts. |
| Rest / Focus Windows | `/blocks` creates rest or work blocks. `TaskTracker` and `ProactivityService` respect those windows. |
| Config & Logs | `config/settings.toml` drives Notion/Telegram/LLM/timezone; runtime logs live under `logs/`. |

More background: `docs/developer_overview.en.md` (architecture), `docs/development_guide.en.md` (contracts), `docs/user_manual.en.md` (deployment & commands).

---

## 🗂 Directory Structure

```
notion_secretary/
├── apps/telegram_bot/         # Bot runtime: handlers, tracker, session monitor
├── core/                      # Domain models, services, repositories, LLM glue
├── data_pipeline/             # Notion collectors/processors/transformers/storage
├── docs/                      # User & developer documentation
├── infra/                     # Config parsing, Notion sync orchestrator
├── scripts/                   # run_bot.py / sync_databases.py
├── tests/                     # Pytest suites
└── databases/                 # Runtime data (raw_json/json/telegram_history)
```

---

## ⚙️ Configuration (`config/settings.toml`)

```toml
[general]
timezone_offset_hours = 8              # Local timezone, default UTC+8, valid range -12~+14

[paths]
data_dir = "./databases"
database_ids_path = "database_ids.json"

[notion]
api_key = "secret_xxx"
sync_interval = 1800                    # Background sync interval for /update
force_update = false
api_version = "2022-06-28"

[telegram]
token = "123456:ABCDE"
poll_timeout = 25
admin_ids = [123456789]

[llm]
provider = "openai"
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
temperature = 0.3
api_key = "sk-..."

[tracker]
interval_seconds = 1500                 # Default tracking interval (seconds). Commands can override.
follow_up_seconds = 600

[proactivity]
state_check_seconds = 300
state_stale_seconds = 3600
state_prompt_cooldown_seconds = 600
question_follow_up_seconds = 600
state_unknown_retry_seconds = 120
```

> **Sensitive files** (`config/settings*.toml`, `docs/user_profile*.md`, `database_ids.json`, everything under `databases/**`, `tracker_entries.json`, etc.) already live in `.gitignore`. Keep them out of version control.

---

## 🗃️ Notion Database Fields

To keep processors and caches consistent, the following Notion properties must exist (case-sensitive):

### Tasks database
| Property | Type | Usage |
| --- | --- | --- |
| `Name` | title | Task title used by `TaskRepository` and Telegram outputs |
| `Priority` | select | Sorting and reminders |
| `Status` | status | Filter out Done/Dormant tasks |
| `Projects` | relation | `/tasks group` relies on this relation |
| `Due Date` | date | Deadline used by `/next` and proactive nudges |
| `Subtasks` | relation | Reverse lookup to show subtask names |

### Projects database
| Property | Type | Usage |
| --- | --- | --- |
| `Name` | title | Project title |
| `Status` | status | Whether the project is active |

### Logs database
| Property | Type | Usage |
| --- | --- | --- |
| `Name` | title | Log title / summary |
| `Status` | status | Hide Done/Dormant entries |
| `Task` | relation | Show related task inside `/logs`

Database IDs go into `database_ids.json` (ignored by git). Override the location with `[paths].database_ids_path` if needed.

---

## 🚀 Quick Start

1. **Install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Copy config template**
   ```bash
   cp config/settings.example.toml config/settings.toml
   ```
3. **Fill in Notion database IDs** in `database_ids.json`.
4. **Sync Notion data once**
   ```bash
   python scripts/sync_databases.py --force
   ```
5. **Launch Telegram bot**
   ```bash
   python scripts/run_bot.py
   ```

`/update` spawns a background sync worker, so command handling stays responsive.

---

## 💬 Commands

| Command | Description |
| --- | --- |
| `/tasks [N]` | Full list with status/priority/due date; self-created tasks have no hyperlinks. |
| `/tasks light [N]` / `/tasks group light [N]` | Minimal view: task name + project, optionally grouped by project. |
| `/tasks delete <indices...>` | Batch delete self-created tasks (Notion tasks stay read-only). |
| `/logs [N]` | Show latest logs (plain text only to avoid Telegram Markdown failures). |
| `/logs delete <indices...>` | Batch delete items from the last `/logs` output. |
| `/track <task/id/name> [minutes]` | Start tracking with any interval ≥5 minutes (LLM converts “8 hours” → 480 minutes). |
| `/trackings` | List tracking entries with next reminder time; `/untrack <index|keyword>` removes one. |
| `/next` | Overview of action/mental status, question tracking, tracking reminders, and time blocks. |
| `/board` | Same as `/next`, reserved for downstream integrations. |
| `/blocks` / `/blocks cancel <index>` | Show or cancel rest/work blocks. |
| `/update` | Trigger background Notion sync (returns immediately, results posted later).

More detail lives in `docs/user_manual.en.md`.

---

## 🔁 Data Flow

1. **Notion → local storage**: `NotionCollector` checks `last_updated.txt`, pulls data, runs processors, and writes to `databases/json`.
2. **Local cache → repositories**: `TaskRepository`, `LogRepository`, `ProjectRepository` read processed JSON plus local artifacts (`agent_tasks.json`, `agent_logs.json`).
3. **Agent loop**: `LLMAgent` assembles persona + context + repositories, calls OpenAI with tool calling, executes requested tools, and returns the final message.
4. **Tracking & rest**: `TaskTracker` persists entries, respects rest windows (only shifts reminders when they actually fall inside a rest block). `/trackings` and `/board` share the same formatter.
5. **Telemetry**: All Telegram conversations land under `databases/telegram_history/`; trackers in `history_dir/tracker_entries.json`.

---

## 🧪 Testing

```bash
python -m pytest
```

Notable suites:
- `tests/apps/telegram_bot/test_command_router_tasks.py`
- `tests/apps/telegram_bot/test_tracker.py`
- `tests/core/test_llm_agent.py`

---

## 📚 Documentation Index

| File | Description |
| --- | --- |
| [`docs/README.en.md`](docs/README.en.md) | Documentation navigator (links to EN/CN pairs; Chinese source: [`docs/README.md`](docs/README.md)). |
| [`docs/developer_overview.en.md`](docs/developer_overview.en.md) | Architecture, data flow, tracker persistence, extension notes. |
| [`docs/development_guide.en.md`](docs/development_guide.en.md) | API contracts and testing strategy. |
| [`docs/user_manual.en.md`](docs/user_manual.en.md) | Deployment steps and Telegram command reference. |
| [`docs/telegram_architecture.en.md`](docs/telegram_architecture.en.md) | Long-poll details, history stitching, proactivity logic. |

Both README files (`README.md` in Chinese / `README.en.md` in English) cross-link, and every document under `docs/` now exposes an `.en.md` English companion. Sensitive persona docs stay local only.

---

## ❓ FAQ

1. **Command stuck?** `/update` and heavy jobs run in background threads. If interaction still blocks, inspect your custom handlers.
2. **Telegram 400 when showing logs?** `/logs` is plain text by default. Re-enable Markdown only if you escape entities properly.
3. **Tracking vs rest windows?** `TaskTracker` only adjusts reminders that actually fall inside a rest block; otherwise it keeps user-provided intervals. `/trackings` and `/board` render the same “next reminder” timestamp.
4. **Timezones such as UTC-12?** Set `[general].timezone_offset_hours = -12` (or `TIMEZONE_OFFSET_HOURS=-12`). `core/utils/timezone.configure_timezone` applies it globally during startup.

---

## 🤝 Contribution Guide

1. Read `docs/developer_overview.en.md` + `docs/development_guide.en.md` before large changes.
2. Respect layer boundaries: collectors → processors → repositories → services → handlers → agent.
3. Long outputs should avoid Telegram Markdown pitfalls; prefer plain text if uncertain.
4. Any long-running operation (Notion sync, mass updates) must run off-thread to avoid blocking polling.
5. Run `pytest` before opening a PR and double-check that ignored sensitive files remain untracked.

Enjoy building with Notion Secretary!
