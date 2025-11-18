# Notion Secretary User Manual

[中文版](user_manual.md)

This guide walks through environment prep, data sync, Telegram usage, and troubleshooting so end users can run the assistant confidently.

## 1. Environment Setup

1. **Install Python 3.10+**. Verify with `python --version`.
2. **Clone the repo** to a working directory (e.g., `D:\Projects\notion_secretary`).
3. **Create a virtualenv (optional)**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # PowerShell: .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
4. **Copy the config template**
   ```bash
   cp config/settings.example.toml config/settings.toml
   ```
   Fill in:
   - `[notion].api_key`: integration token with DB access.
   - `[notion].sync_interval`: seconds between background sync runs.
   - `[paths].data_dir`: where `raw_json/`, `json/`, `telegram_history/` live.
   - `[general].timezone_offset_hours`: local timezone offset (default 8 = UTC+8).
   - `[telegram].token`: returned by @BotFather; add `[telegram].admin_ids` via @userinfobot.
   - `[llm]` block: provider/base_url/model/api_key/temperature.

## 2. Data Sync

The bot relies on Notion Tasks / Projects / Logs. Run at least one full sync before starting the bot.

1. **Database IDs**
   Populate `database_ids.json`:
   ```json
   {
     "tasks": "29b2...d4",
     "logs": "29b2...a3",
     "projects": "2562...51"
   }
   ```
2. **Manual sync**
   ```bash
   python database_collect.py --force
   ```
   - Writes raw responses to `DATA_DIR/raw_json`.
   - Processors build `processed_tasks.json`, etc., under `DATA_DIR/json`.
3. **Continuous sync (optional)**
   ```bash
   python database_collect.py --loop
   ```
   Runs according to `NOTION_SYNC_INTERVAL`. When only running the Telegram bot, `/update` already launches a background thread using the same `last_updated.txt`, so an extra daemon is optional.

## 3. Start the Telegram Bot

1. **Launch**
   ```bash
   python -m apps.telegram_bot.bot
   ```
2. **Flow**
   - Load config, build `HistoryStore`, repositories, services.
   - Enter the long-poll loop (`getUpdates`).
   - Every outbound message is persisted in `DATA_DIR/telegram_history/<chat_id>.jsonl`.
3. **Clients**
   - Works with mobile/desktop/web Telegram via long polling—no public webhook needed.
   - To migrate to webhooks, see `docs/telegram_architecture.md`.

## 4. Commands & Scenarios

| Command/Input | Description |
| --- | --- |
| `/tasks` or `/today` | Task overview grouped by status & sorted by priority. |
| `/tasks light [N]` / `/tasks group light [N]` | Minimal view; second variant groups by project. |
| `/focus` | Triggers an immediate status scan; bot escalates if deadlines loom. |
| `#log ...` | Quick log entry. Append `task=<ID>` to bind a task. |
| `/trackings` | Show current tracking entries with indices; pair with `/untrack`. |
| `/untrack <index|keyword>` | Cancel a tracking entry. |
| `/logs delete <indices...>` | Remove entries referencing the last `/logs` output. |
| `/board` | Alias of `/next`, a global state board. |
| Free text | Currently routed to simple hints / agent replies. |

Typical flows:
- **Daily Briefing**: run `/today` or scheduler-driven `DailyBriefingWorkflow`.
- **Evening Review**: combine `/focus` with task/log stats to chase unfinished work.
- **Interventions**: `StatusGuard` surfaces risks; the agent chooses tone & follow-ups.

## 5. Data & Logs

- `DATA_DIR/raw_json`: raw Notion API payloads for debugging.
- `DATA_DIR/json`: processed files consumed by repositories.
- `DATA_DIR/telegram_history`: chat histories per `chat_id`.
- `databases/last_updated.txt`: timestamp of the last successful Notion sync.

## 6. Testing

After changes:
```bash
python -m pytest
```
Focus suites:
- `tests/apps/telegram_bot/test_history_store.py`
- `tests/apps/telegram_bot/test_telegram_client.py`
- `tests/core/test_task_summary_service.py`

## 7. FAQ

1. **Bot silent?** Check `[telegram].token`, proxy, and `HistoryStore` metadata. Remove `metadata.json` if you need to reset `update_id`.
2. **Notion data stale?** Ensure the integration has DB access and `database_collect.py --force` succeeds. Confirm `DATA_DIR` is writable.
3. **`#log` cannot bind a task?** Provide an ID present in `processed_tasks.json` (use `/tasks` or inspect the file).

## 8. Next Steps

- Follow `docs/development_guide.md` for extending handlers/workflows.
- Convert long polling to webhooks if hosting on a public server.
- Use `apscheduler` within `infra/scheduler` for automatic daily briefings or reviews.

Need more details? Refer to `README.en.md`, `docs/telegram_architecture.en.md`, and `docs/development_guide.en.md`.
