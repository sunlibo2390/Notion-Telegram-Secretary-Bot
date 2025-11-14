from __future__ import annotations

from apps.telegram_bot.clients.telegram_client import TelegramBotClient
from core.services import StatusGuard, TaskSummaryService


class DailyBriefingWorkflow:
    def __init__(
        self,
        task_summary_service: TaskSummaryService,
        status_guard: StatusGuard,
        telegram_client: TelegramBotClient,
    ):
        self._task_summary = task_summary_service
        self._status_guard = status_guard
        self._client = telegram_client

    def run(self, chat_id: int) -> None:
        summary = self._task_summary.build_today_summary()
        self._client.send_message(chat_id=chat_id, text=summary)
        for intervention in self._status_guard.evaluate():
            self._client.send_message(chat_id=chat_id, text=intervention.message)
