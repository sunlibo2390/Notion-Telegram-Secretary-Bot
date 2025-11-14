from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from core.domain import Task
from core.repositories import LogRepository, ProjectRepository, TaskRepository

PRIORITY_ORDER = {"Urgent": 0, "High": 1, "Medium": 2, "Low": 3}
MD_SPECIAL = ["\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]


class TaskSummaryService:
    def __init__(
        self,
        task_repository: TaskRepository,
        project_repository: ProjectRepository,
        log_repository: LogRepository | None = None,
    ):
        self._task_repo = task_repository
        self._project_repo = project_repository
        self._log_repo = log_repository

    def _sort_tasks(self, tasks: List[Task]) -> List[Task]:
        return sorted(
            tasks,
            key=lambda task: (
                PRIORITY_ORDER.get(task.priority, 99),
                task.due_date or "9999-99-99",
                task.name,
            ),
        )

    def _build_logs_map(self) -> Dict[str, List[Dict[str, str]]]:
        logs_map: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        if not self._log_repo:
            return logs_map
        for log in self._log_repo.list_logs():
            if log.task_id:
                logs_map[log.task_id].append(
                    {
                        "id": log.id,
                        "name": log.name,
                        "status": log.status,
                        "content": log.content,
                    }
                )
        return logs_map

    def build_today_summary(self, limit: int = 10) -> str:
        tasks = self._task_repo.list_active_tasks()
        if not tasks:
            return "_今日暂无待办，保持节奏，找事做。_"
        logs_map = self._build_logs_map()
        items: List[str] = []
        for task in self._sort_tasks(tasks)[:limit]:
            url = task.page_url or f"https://www.notion.so/{task.id.replace('-', '')}"
            due = self._escape(task.due_date or "未设")
            priority = self._escape(task.priority)
            status = self._escape(task.status)
            content = self._escape(task.content or "")
            latest_log = (
                logs_map.get(task.id, [{}])[-1].get("content", "")
                if logs_map.get(task.id)
                else ""
            )
            log_text = f"｜最新：{self._escape(latest_log[:60])}" if latest_log else ""
            name = self._escape(task.name)
            line = f"- [{name}]({url}) ｜状态:{status} ｜优先级:{priority} ｜截止:{due} {log_text}\n  内容: {content}"
            items.append(line)
        return "\n".join(items) if items else "_今日暂无待办，保持节奏。_"

    def list_by_project(self) -> Dict[str, List[Task]]:
        tasks = self._task_repo.list_active_tasks()
        projects = {p.id: p for p in self._project_repo.list_active_projects()}
        grouped: Dict[str, List[Task]] = defaultdict(list)
        for task in tasks:
            project_name = (
                projects.get(task.project_id).name
                if task.project_id and task.project_id in projects
                else task.project_name
            )
            grouped[project_name].append(task)
        for project, bucket in grouped.items():
            grouped[project] = self._sort_tasks(bucket)
        return grouped

    def build_task_payloads(self) -> List[Dict[str, Any]]:
        tasks = self._task_repo.list_active_tasks()
        logs_map = self._build_logs_map()
        payloads: List[Dict[str, Any]] = []
        for task in self._sort_tasks(tasks):
            payloads.append(
                {
                    "id": task.id,
                    "name": task.name,
                    "priority": task.priority,
                    "status": task.status,
                    "due_date": task.due_date,
                    "project_id": task.project_id,
                    "project": task.project_name,
                    "content": task.content,
                    "subtasks": task.subtask_names,
                    "url": task.page_url,
                    "logs": logs_map.get(task.id, []),
                }
            )
        return payloads

    def _escape(self, text: str) -> str:
        if not text:
            return ""
        result = text
        # for ch in MD_SPECIAL:
        #     result = result.replace(ch, f"\\{ch}")
        return result
