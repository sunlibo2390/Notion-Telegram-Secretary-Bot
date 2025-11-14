from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from core.domain import LogEntry
from core.repositories import LogRepository, TaskRepository
from core.utils.timezone import beijing_now, format_beijing


@dataclass(slots=True)
class LogRecordResult:
    message: str
    task_name: Optional[str]
    stored: bool


class LogbookService:
    def __init__(self, log_repository: LogRepository, task_repository: TaskRepository):
        self._log_repo = log_repository
        self._task_repo = task_repository

    def _parse_log(self, raw_text: str) -> tuple[str, Optional[str]]:
        content = raw_text.replace("#log", "", 1).strip()
        task_marker = None
        for token in content.split():
            if token.startswith("task="):
                task_marker = token.split("=", 1)[1]
                content = content.replace(token, "").strip()
                break
        return content or "空白日志", task_marker

    def record_log(self, raw_text: str) -> LogRecordResult:
        content, task_id = self._parse_log(raw_text)
        return self.record_structured_log(content=content, task_id=task_id)

    def record_structured_log(
        self,
        content: str,
        task_name: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> LogRecordResult:
        normalized = (content or "空白日志").strip()
        if not normalized:
            normalized = "空白日志"
        matched_task = None
        if task_id:
            matched_task = self._task_repo.get_task(task_id)
        if not matched_task and task_name:
            matched_task = self._task_repo.find_by_name(task_name)
        if not matched_task:
            inferred_name = task_name or f"临时任务-{beijing_now():%Y%m%d%H%M}"
            matched_task = self._task_repo.ensure_task(inferred_name, content)
        resolved_task_id = matched_task.id
        resolved_task_name = matched_task.name
        entry = LogEntry(
            id=str(uuid4()),
            name=format_beijing(beijing_now()),
            status="Captured",
            content=normalized,
            task_id=resolved_task_id,
            task_name=resolved_task_name,
        )
        self._log_repo.add_local_log(entry)
        display = f"{entry.name} ｜ 任务: {resolved_task_name}\n{normalized}"
        return LogRecordResult(
            message=display,
            task_name=resolved_task_name,
            stored=True,
        )

    def delete_log(self, log_id: str) -> LogRecordResult:
        success = self._log_repo.delete_log(log_id)
        message = "日志已删除。" if success else "未找到对应的日志。"
        return LogRecordResult(message=message, task_name=None, stored=success)

    def update_log(
        self,
        log_id: str,
        content: Optional[str] = None,
        task_name: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> LogRecordResult:
        normalized = content.strip() if content else None
        matched_task = None
        if task_id:
            matched_task = self._task_repo.get_task(task_id)
        if not matched_task and task_name:
            matched_task = self._task_repo.find_by_name(task_name)
        resolved_task_id = matched_task.id if matched_task else task_id
        resolved_task_name = matched_task.name if matched_task else task_name
        entry = self._log_repo.update_log(
            log_id,
            content=normalized,
            task_id=resolved_task_id,
            task_name=resolved_task_name,
        )
        if not entry:
            return LogRecordResult(
                message="未找到对应的日志。",
                task_name=None,
                stored=False,
            )
        return LogRecordResult(
            message=f"日志已更新：{entry.name} ｜任务:{entry.task_name or entry.task_id or '未关联'}",
            task_name=entry.task_name,
            stored=True,
        )
