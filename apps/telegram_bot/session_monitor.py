from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict

from apps.telegram_bot.clients import TelegramBotClient
from apps.telegram_bot.rest import RestScheduleService, RestWindow
from core.utils.timezone import format_beijing


def _utcnow() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)


class TaskSessionMonitor:
    def __init__(self, client: TelegramBotClient, rest_service: RestScheduleService):
        self._client = client
        self._rest_service = rest_service
        self._timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        self._bootstrap()

    def _bootstrap(self) -> None:
        for window in self._rest_service.iter_windows(include_past=False):
            self.schedule(window)

    def schedule(self, window: RestWindow) -> None:
        if window.session_type != "task":
            return
        with self._lock:
            self._cancel_locked(window.id)
            now = _utcnow()
            if window.end <= now:
                self._notify(window)
                self._rest_service.delete_window(window.id)
                return
            delay = max(1.0, (window.end - now).total_seconds())
            timer = threading.Timer(delay, self._handle_expiry, args=(window.id,))
            timer.daemon = True
            timer.start()
            self._timers[window.id] = timer

    def cancel(self, window_id: str) -> None:
        with self._lock:
            self._cancel_locked(window_id)

    def _cancel_locked(self, window_id: str) -> None:
        timer = self._timers.pop(window_id, None)
        if timer:
            timer.cancel()

    def _handle_expiry(self, window_id: str) -> None:
        window = self._rest_service.get_window(window_id)
        if not window:
            with self._lock:
                self._cancel_locked(window_id)
            return
        self._notify(window)
        self._rest_service.delete_window(window_id)
        with self._lock:
            self._cancel_locked(window_id)

    def _notify(self, window: RestWindow) -> None:
        task_label = window.task_name or window.note or "（未命名任务）"
        end_time = format_beijing(window.end)
        text = (
            f"⏰ 任务专注窗口已结束：{task_label}\n"
            f"结束时间：{end_time}\n"
            "请确认是否完成该任务，必要时重新规划新的时间段。"
        )
        self._client.send_message(chat_id=window.chat_id, text=text)
