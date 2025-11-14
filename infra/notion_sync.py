from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

from core.repositories import LogRepository, ProjectRepository, TaskRepository
from database_collect import collector_from_settings
from infra.config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NotionSyncResult:
    success: bool
    message: str
    updated: bool
    duration_seconds: Optional[float] = None


class NotionSyncService:
    def __init__(
        self,
        settings: Settings,
        task_repository: TaskRepository,
        project_repository: ProjectRepository,
        log_repository: LogRepository,
    ):
        self._collector = collector_from_settings(settings, force=True)
        self._task_repo = task_repository
        self._project_repo = project_repository
        self._log_repo = log_repository
        self._lock = threading.Lock()

    def sync(self, actor: str = "manual") -> NotionSyncResult:
        if not self._lock.acquire(blocking=False):
            return NotionSyncResult(
                success=False,
                message="已有同步任务正在执行，请稍后再试。",
                updated=False,
                duration_seconds=None,
            )
        start = time.time()
        try:
            self._collector.collect_once()
            self._project_repo.refresh()
            self._task_repo.refresh()
            self._log_repo.refresh()
            duration = time.time() - start
            logger.info("Notion 数据同步完成，actor=%s，耗时 %.2fs", actor, duration)
            return NotionSyncResult(
                success=True,
                message=f"Notion 数据已更新（耗时 {duration:.1f} 秒）",
                updated=True,
                duration_seconds=duration,
            )
        except Exception as error:
            logger.exception("Notion 数据同步失败，actor=%s：%s", actor, error)
            return NotionSyncResult(
                success=False,
                message=f"同步失败：{error}",
                updated=False,
                duration_seconds=None,
            )
        finally:
            self._lock.release()
