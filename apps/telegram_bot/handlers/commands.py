from __future__ import annotations

import re
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from types import SimpleNamespace

from apps.telegram_bot.clients import TelegramBotClient
from apps.telegram_bot.history import HistoryStore
from apps.telegram_bot.proactivity import ProactivityService, QUESTION_EVENT, STATE_EVENT
from apps.telegram_bot.rest import RestScheduleService, RestWindow
from apps.telegram_bot.session_monitor import TaskSessionMonitor
from apps.telegram_bot.tracker import TaskTracker, escape_md
from apps.telegram_bot.user_state import UserStateService
from core.llm.agent import LLMAgent
from core.repositories import LogRepository, TaskRepository
from core.utils.timezone import format_beijing
from infra.notion_sync import NotionSyncService


class CommandRouter:
    def __init__(
        self,
        client: TelegramBotClient,
        history_store: HistoryStore,
        agent: Optional[LLMAgent] = None,
        task_repo: Optional[TaskRepository] = None,
        log_repo: Optional[LogRepository] = None,
        tracker: Optional[TaskTracker] = None,
        proactivity: Optional[ProactivityService] = None,
        user_state: Optional[UserStateService] = None,
        rest_service: Optional[RestScheduleService] = None,
        session_monitor: Optional[TaskSessionMonitor] = None,
        notion_sync: Optional[NotionSyncService] = None,
    ):
        self._client = client
        self._history = history_store
        self._agent = agent
        self._task_repo = task_repo
        self._log_repo = log_repo
        self._tracker = tracker
        self._proactivity = proactivity
        self._user_state = user_state
        self._rest_service = rest_service
        self._session_monitor = session_monitor
        self._notion_sync = notion_sync
        self._log_snapshot: Dict[int, List[str]] = {}
        self._rest_snapshot: Dict[int, List[str]] = {}
        if self._proactivity:
            self._proactivity.set_event_handler(self._handle_proactive_event)

    def handle(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            self._history.record_update_checkpoint(update.get("update_id"))
            return
        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        self._history.append_user(update)
        if self._proactivity:
            should_interrupt = self._proactivity.record_user_message(chat_id, text)
            if should_interrupt:
                return
        lowered = text.lower()
        if lowered.startswith("/clear"):
            self._history.clear_chat(chat_id)
            if self._tracker:
                self._tracker.clear(chat_id)
            if self._proactivity:
                self._proactivity.reset(chat_id)
            self._log_snapshot.pop(chat_id, None)
            self._send_message(chat_id, escape_md("历史记录已归档，进入新的会话。"))
            return
        if lowered.startswith("/track "):
            self._handle_track(chat_id, text)
            return
        if lowered.startswith("/untrack"):
            self._handle_untrack(chat_id)
            return
        if lowered.startswith("/trackings"):
            self._handle_list_trackings(chat_id)
            return
        if lowered.startswith("/help"):
            self._handle_help(chat_id)
            return
        if lowered.startswith("/state"):
            self._handle_state(chat_id)
            return
        if lowered.startswith("/next"):
            self._handle_next(chat_id)
            return
        if lowered.startswith("/blocks") or lowered.startswith("/rest"):
            self._handle_blocks(chat_id, text)
            return
        if lowered.startswith("/logs"):
            self._handle_logs(chat_id, text)
            return
        if lowered.startswith("/update"):
            self._handle_update(chat_id)
            return
        if self._tracker:
            enriched = self._tracker.consume_reply(chat_id, text)
            if enriched:
                text = enriched
        if not self._agent:
            raise RuntimeError("LLM Agent 未配置，无法处理消息。")
        responses = self._agent.handle(chat_id, text)
        for resp in responses:
            if resp and resp.strip():
                self._send_message(chat_id, resp)

    def _handle_track(self, chat_id: int, text: str) -> None:
        if not self._tracker or not self._task_repo:
            self._send_message(chat_id, escape_md("暂不支持跟踪功能。"))
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            self._send_message(chat_id, escape_md("用法：/track 任务ID"))
            return
        task_id = parts[1].strip()
        interval_minutes: Optional[int] = None
        if len(parts) >= 3:
            for token in parts[2:]:
                if token.isdigit():
                    interval_minutes = int(token)
                    break
        task = self._task_repo.get_task(task_id)
        if not task:
            self._send_message(chat_id, escape_md("未找到该任务ID，请检查。"))
            return
        self._tracker.start_tracking(chat_id, task, interval_minutes=interval_minutes)

    def _handle_untrack(self, chat_id: int) -> None:
        if not self._tracker:
            self._send_message(chat_id, escape_md("暂无跟踪任务。"))
            return
        entry = self._tracker.stop_tracking(chat_id)
        if not entry:
            self._send_message(chat_id, escape_md("当前没有正在跟踪的任务。"))
            return
        self._send_message(
            chat_id,
            f"已取消跟踪 [{escape_md(entry.task_name)}]({entry.task_url})。",
        )

    def _handle_list_trackings(self, chat_id: int) -> None:
        if not self._tracker:
            self._send_message(chat_id, escape_md("暂无跟踪任务。"))
            return
        entries = self._tracker.list_active(chat_id)
        if not entries:
            self._send_message(chat_id, escape_md("当前没有跟踪任务。"))
            return
        lines = [
            f"- [{escape_md(entry.task_name)}]({entry.task_url}) ｜等待反馈:{'是' if entry.waiting else '否'}"
            for entry in entries
        ]
        self._send_message(chat_id, "\n".join(lines))

    def _handle_update(self, chat_id: int) -> None:
        if not self._notion_sync:
            self._send_message(chat_id, escape_md("Notion 同步未配置。"))
            return
        self._send_message(chat_id, escape_md("正在从 Notion 拉取最新任务与日志..."))
        result = self._notion_sync.sync(actor=f"command:{chat_id}")
        prefix = "✅" if result.success else "⚠️"
        self._send_message(chat_id, f"{prefix} {result.message}", markdown=False)

    def _handle_logs(self, chat_id: int, text: str) -> None:
        if not self._log_repo:
            self._send_message(chat_id, escape_md("日志功能暂不可用。"))
            return
        lowered = text.lower()
        logs = self._log_repo.list_logs()
        if " delete" in lowered:
            self._handle_delete_log(chat_id, text, logs)
            return
        if " update" in lowered:
            self._handle_update_log(chat_id, text, logs)
            return
        parts = text.split()
        limit = 5
        group_by_task = False
        for token in parts[1:]:
            lowered_token = token.lower()
            if lowered_token in {"task", "tasks", "bytask"}:
                group_by_task = True
                continue
            try:
                limit = max(1, min(20, int(token)))
            except ValueError:
                continue
        if not logs:
            self._send_message(chat_id, escape_md("当前没有日志记录。"))
            return
        if group_by_task:
            self._render_logs_grouped(chat_id, logs, limit)
            return
        snippet = logs[-limit:]
        display_entries = list(reversed(snippet))
        self._log_snapshot[chat_id] = [entry.id for entry in display_entries]
        lines: List[str] = []
        for idx, entry in enumerate(display_entries, start=1):
            task_label = self._format_task_label(entry)
            lines.append(f"{idx}. {escape_md(entry.name)} ｜任务:{task_label}")
            content_lines = [line.strip() for line in entry.content.splitlines() if line.strip()]
            if not content_lines:
                lines.append(f"  · {escape_md('(无内容)')}")
            else:
                for line in content_lines:
                    lines.append(f"  · {escape_md(line)}")
            lines.append("")
        lines.append(escape_md("如需操作：/logs delete <序号> 或 /logs update <序号> <新内容>"))
        self._send_message(chat_id, "\n".join(lines), markdown=True)

    def _render_logs_grouped(self, chat_id: int, logs: List, limit: int, per_task_limit: int = 3) -> None:
        groups: List[Dict[str, Any]] = []
        seen: Dict[str, Dict[str, Any]] = {}
        for entry in reversed(logs):
            key = entry.task_id or f"local:{entry.task_name or '未关联'}"
            group = seen.get(key)
            if not group:
                group = {
                    "task_id": entry.task_id,
                    "task_name": entry.task_name,
                    "task_url": getattr(entry, "task_url", None),
                    "logs": [],
                }
                seen[key] = group
                groups.append(group)
            if len(group["logs"]) < per_task_limit:
                group["logs"].append(entry)
        if not groups:
            self._send_message(chat_id, escape_md("暂无可分组的日志记录。"))
            return
        groups.sort(key=lambda g: g["logs"][0].name, reverse=True)
        lines: List[str] = []
        for idx, group in enumerate(groups[:limit], start=1):
            stub = SimpleNamespace(
                task_name=group["task_name"],
                task_id=group["task_id"],
                task_url=group["task_url"],
            )
            task_label = self._format_task_label(stub)
            lines.append(f"{idx}. {task_label} ｜最近记录 {len(group['logs'])} 条")
            for log_entry in group["logs"]:
                content_lines = [line.strip() for line in log_entry.content.splitlines() if line.strip()]
                summary = content_lines[0] if content_lines else "(无内容)"
                lines.append(f"  - {escape_md(log_entry.name)} ｜ {escape_md(summary)}")
                for extra in content_lines[1:]:
                    lines.append(f"    {escape_md(extra)}")
            lines.append("")
        lines.append(escape_md("提示：使用 /logs tasks [N] 可按任务归并，默认每个任务展示 3 条。"))
        self._send_message(chat_id, "\n".join(lines), markdown=True)

    def _handle_delete_log(self, chat_id: int, text: str, logs: list) -> None:
        snapshot = self._log_snapshot.get(chat_id)
        if not snapshot:
            self._send_message(chat_id, escape_md("请先使用 /logs 查看当前列表，再执行删除。"))
            return
        index = self._extract_index(text)
        if index is None:
            self._send_message(chat_id, escape_md("用法：/logs delete 序号"))
            return
        if index < 1 or index > len(snapshot):
            self._send_message(chat_id, escape_md("序号超出范围，请重新查看 /logs。"))
            return
        target_id = snapshot[index - 1]
        target = next((entry for entry in logs if entry.id == target_id), None)
        if not target:
            self._send_message(chat_id, escape_md("未找到该日志，请重新查看 /logs。"))
            return
        success = self._log_repo.delete_log(target.id) if self._log_repo else False
        if success:
            self._log_snapshot[chat_id] = [log_id for log_id in snapshot if log_id != target_id]
            self._send_message(
                chat_id,
                escape_md(f"已删除日志：{target.name} ｜任务:{target.task_name or target.task_id or '未关联'}"),
            )
        else:
            self._send_message(chat_id, escape_md("删除失败，未找到该日志。"))

    def _handle_update_log(self, chat_id: int, text: str, logs: list) -> None:
        snapshot = self._log_snapshot.get(chat_id)
        if not snapshot:
            self._send_message(chat_id, escape_md("请先使用 /logs 查看当前列表，再执行更新。"))
            return
        match = re.search(r"/logs\s+update\s+(\d+)\s*(.*)", text, flags=re.IGNORECASE)
        if not match:
            self._send_message(chat_id, escape_md("用法：/logs update 序号 内容"))
            return
        index = int(match.group(1))
        if index < 1 or index > len(snapshot):
            self._send_message(chat_id, escape_md("序号超出范围，请重新查看 /logs。"))
            return
        note_text = match.group(2).strip()
        if not note_text:
            self._send_message(chat_id, escape_md("请提供需要更新的内容。"))
            return
        target_id = snapshot[index - 1]
        target = next((entry for entry in logs if entry.id == target_id), None)
        if not target:
            self._send_message(chat_id, escape_md("未找到该日志，请重新查看 /logs。"))
            return
        task_hint, formatted_note = self._extract_task_from_text(note_text)
        updated_entry = self._log_repo.update_log(
            target.id,
            content=formatted_note or target.content,
            task_id=None,
            task_name=task_hint,
        )
        if updated_entry:
            self._send_message(
                chat_id,
                escape_md(f"日志已更新：{updated_entry.name} ｜任务:{updated_entry.task_name or updated_entry.task_id or '未关联'}"),
            )
        else:
            self._send_message(chat_id, escape_md("更新失败，未找到该日志。"))

    def _handle_blocks(self, chat_id: int, text: str) -> None:
        if not self._rest_service:
            self._send_message(chat_id, escape_md("未启用时间块功能。"))
            return
        parts = text.split()
        lowered = parts[1].lower() if len(parts) > 1 else ""
        if len(parts) >= 3 and lowered == "cancel":
            snapshot = self._rest_snapshot.get(chat_id)
            if not snapshot:
                self._send_message(chat_id, escape_md("请先使用 /blocks 查看当前列表，再执行取消。"))
                return
            try:
                index = int(parts[2])
            except ValueError:
                self._send_message(chat_id, escape_md("用法：/blocks cancel 序号"))
                return
            if index < 1 or index > len(snapshot):
                self._send_message(chat_id, escape_md("序号超出范围，请重新 /blocks 查看。"))
                return
            window_id = snapshot[index - 1]
            window = self._rest_service.get_window(window_id)
            success = self._rest_service.cancel_window(window_id)
            if success:
                self._rest_snapshot[chat_id] = [wid for wid in snapshot if wid != window_id]
                if self._session_monitor and window and window.session_type == "task":
                    self._session_monitor.cancel(window_id)
                self._send_message(chat_id, escape_md(f"已取消第 {index} 条时间块安排。"))
            else:
                self._send_message(chat_id, escape_md("取消失败，时间块已过期或不存在。"))
            return
        windows = self._rest_service.list_windows(chat_id, include_past=False)
        if not windows:
            self._rest_snapshot.pop(chat_id, None)
            self._send_message(chat_id, escape_md("暂无时间块安排。可以对我说“14:00-16:00 专注 Magnet 代码”或“13:00-14:00 想休息”。"))
            return
        self._rest_snapshot[chat_id] = [window.id for window in windows]
        lines = ["时间块安排："]
        for idx, window in enumerate(windows, start=1):
            lines.append(f"{idx}. {self._format_rest_window(window)}")
        lines.append("")
        lines.append("使用 `/blocks cancel <序号>` 可撤销。")
        self._send_message(chat_id, "\n".join(lines), markdown=False)

    def _handle_help(self, chat_id: int) -> None:
        lines = [
            "*指令列表*",
            "/help - 查看所有命令说明",
            "/state - 查看当前记录的行动/心理状态",
            "/next - 查看下一次主动提醒的时间与条件",
            "/blocks [cancel <序号>] - 查看或取消时间块（休息/任务）",
            "/track <任务ID> [分钟] - 开启跟踪提醒，可自定义首个提醒间隔（默认25分钟）",
            "/trackings - 查看当前正在跟踪的任务",
            "/untrack - 取消当前跟踪提醒",
            "/logs [N] - 查看最近 N 条日志（默认 5）",
            "/logs tasks [N] - 按任务归并查看最近日志（默认展示 5 个任务，每个最多 3 条）",
            "/logs delete <序号> - 删除最近一次 /logs 输出中的对应日志",
            "/logs update <序号> <内容> - 更新对应日志，可包含“任务 XXX：...”重绑任务",
            "/update - 立即同步 Notion 项目/任务/日志数据",
            "/clear - 清空上下文与定时器",
        ]
        self._send_message(chat_id, "\n".join(lines))

    def _handle_state(self, chat_id: int) -> None:
        if not self._user_state:
            self._send_message(chat_id, escape_md("暂无状态记录。"))
            return
        has_tracker = bool(self._tracker and self._tracker.list_active(chat_id))
        is_resting = self._rest_service.is_resting(chat_id) if self._rest_service else None
        state = self._user_state.get_state(
            chat_id,
            has_active_tracker=has_tracker,
            is_resting=is_resting,
        )
        lines = [
            "当前状态：",
            f"- 行动：{escape_md(state.action)}（更新于 {self._fmt_time(state.action_updated_at)}）",
            f"- 心理：{escape_md(state.mental)}（更新于 {self._fmt_time(state.mental_updated_at)}）",
        ]
        self._send_message(chat_id, "\n".join(lines))

    def _handle_next(self, chat_id: int) -> None:
        lines = ["下一次主动提醒预估："]
        if self._proactivity:
            desc = self._proactivity.describe_next_prompts(chat_id)
            lines.append(f"- 行动状态：{self._format_state_desc(desc.get('action'))}")
            lines.append(f"- 心理状态：{self._format_state_desc(desc.get('mental'))}")
            question = desc.get("question", {})
            if question.get("pending"):
                lines.append(f"- 提问追踪：{self._format_due(question.get('due_time'))} 将再次提醒")
            else:
                lines.append("- 提问追踪：暂无")
            rest = desc.get("rest", {})
            next_start = rest.get("next_window_start")
            next_end = rest.get("next_window_end")
            if rest.get("active"):
                lines.append(f"- 休息：进行中，结束于 {self._format_due(rest.get('current_end'))}")
                if next_start and next_end and rest.get("current_end") != next_end:
                    lines.append(f"  后续：{self._format_due(next_start)} ~ {self._format_due(next_end)}")
            elif next_start and next_end:
                lines.append(f"- 休息：计划 {self._format_due(next_start)} ~ {self._format_due(next_end)}")
            else:
                lines.append("- 休息：暂无安排")
        else:
            lines.append("- 状态提醒：未启用")
        if self._tracker:
            info = self._tracker.next_event(chat_id)
            if info:
                suffix = "（等待回复）" if info.get("waiting") else ""
                lines.append(
                    f"- 跟踪任务：{escape_md(info['task_name'])} → {self._format_due(info.get('due_time'))}{suffix}"
                )
            else:
                lines.append("- 跟踪任务：暂无")
        else:
            lines.append("- 跟踪任务：未启用")
        self._send_message(chat_id, "\n".join(lines), markdown=False)

    def _handle_proactive_event(self, chat_id: int, event: Dict[str, Any]) -> None:
        if not self._agent:
            return
        event_type = event.get("type")
        if event_type == STATE_EVENT:
            missing = event.get("missing", [])
            labels = {"action": "行动状态", "mental": "心理状态"}
            human = "、".join(labels.get(key, key) for key in missing) or "状态"
            prompt = (
                f"系统提醒：用户的{human}超过设定时间未更新。"
                "请结合当前上下文，用自然语言与用户进行交互询问，以获取用户状态信息。"
            )
        elif event_type == QUESTION_EVENT:
            question = event.get("question", "")
            prompt = (
                f"系统提醒：之前向用户提出的问题“{question}”未收到回复。"
                "请再次追问，说明必须得到反馈，并给出具体要求。"
            )
        else:
            return
        responses = self._agent.handle(chat_id, prompt)
        for resp in responses:
            if resp and resp.strip():
                self._send_message(chat_id, resp)

    def _send_message(self, chat_id: int, text: str, markdown: bool = True) -> None:
        parse_mode = "Markdown" if markdown else None
        self._client.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        if self._proactivity:
            self._proactivity.record_agent_message(chat_id, text)

    @staticmethod
    def _extract_index(text: str) -> Optional[int]:
        for token in text.split():
            if token.isdigit():
                return int(token)
        return None

    @staticmethod
    def _extract_task_from_text(text: str) -> tuple[Optional[str], str]:
        task_pattern = re.compile(r"任务\s*([^\s：:]+)\s*[：:]\s*(.+)")
        match = task_pattern.search(text)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        marker = re.search(r"task\s*=\s*([\w-]+)", text, re.IGNORECASE)
        if marker:
            task_name = marker.group(1).strip()
            cleaned = (text[: marker.start()] + text[marker.end():]).strip()
            return task_name, cleaned
        return None, text.strip()

    @staticmethod
    def _format_task_label(entry) -> str:
        task_label = escape_md(entry.task_name or entry.task_id or "未关联")
        url = getattr(entry, "task_url", None)
        task_id = getattr(entry, "task_id", None)
        if not url and task_id:
            clean_id = task_id.replace("-", "")
            if len(clean_id) == 32 and all(ch in string.hexdigits for ch in clean_id):
                url = f"https://www.notion.so/{clean_id}"
        if url:
            return f"[{task_label}]({url})"
        return task_label

    @staticmethod
    def _fmt_time(value: Optional[datetime]) -> str:
        if not value:
            return "未知"
        return format_beijing(value)

    @staticmethod
    def _format_due(value: Optional[str]) -> str:
        if not value:
            return "未计划"
        try:
            return format_beijing(datetime.fromisoformat(value))
        except ValueError:
            return value

    @staticmethod
    def _format_state_desc(data: Optional[Dict[str, Any]]) -> str:
        if not data:
            return "未启用"
        status = data.get("value", "未知")
        due_raw = data.get("due_time")
        due_text = CommandRouter._format_due(due_raw)
        immediate = False
        if due_raw:
            try:
                due_dt = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
                now = datetime.utcnow().replace(tzinfo=timezone.utc)
                immediate = due_dt <= now
            except ValueError:
                pass
        if data.get("pending"):
            if immediate:
                return f"{status}｜等待反馈，立即追问"
            return f"{status}｜等待反馈，将在 {due_text} 追问"
        return f"{status}｜记录有效，将在 {due_text} 再次确认"

    @staticmethod
    def _format_rest_window(window: RestWindow) -> str:
        note = f"｜备注:{window.note}" if window.note else ""
        start = format_beijing(window.start, "%m-%d %H:%M")
        end = format_beijing(window.end, "%m-%d %H:%M")
        status_map = {"pending": "待确认", "approved": "已批准", "cancelled": "已取消", "rejected": "已拒绝"}
        status = status_map.get(window.status, window.status)
        if window.session_type == "task":
            task_label = window.task_name or window.task_id or "未命名任务"
            prefix = f"[任务] {task_label}"
        else:
            prefix = "[休息]"
        return f"{prefix} {start} ~ {end} ｜状态:{status}{note}"
