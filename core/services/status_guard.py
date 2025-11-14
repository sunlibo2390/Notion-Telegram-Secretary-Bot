from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from core.domain import Intervention
from core.repositories import TaskRepository


class StatusGuard:
    def __init__(self, task_repository: TaskRepository):
        self._task_repo = task_repository

    def evaluate(self) -> List[Intervention]:
        interventions: List[Intervention] = []
        now = datetime.now()
        for task in self._task_repo.list_active_tasks():
            if not task.due_date:
                continue
            try:
                due = datetime.fromisoformat(task.due_date)
            except ValueError:
                continue
            if due - now <= timedelta(hours=24) and task.status != "Done":
                interventions.append(
                    Intervention(
                        level="warning",
                        message=f"任务《{task.name}》即将到期，别再拖。",
                        reason="due_soon",
                    )
                )
        return interventions
