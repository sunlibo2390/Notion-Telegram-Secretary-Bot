import json
from importlib import reload
from pathlib import Path

from core.repositories import ProjectRepository, TaskRepository
from core.services import TaskSummaryService
from data_pipeline.storage import paths


class DummyLogRepo:
    def list_logs(self):
        return []


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_task_summary_orders_by_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reload(paths)
    tasks_path = paths.processed_json_path("processed_tasks")
    projects_path = paths.processed_json_path("processed_projects")
    _write_json(
        projects_path,
        {
            "proj1": {"name": "Main", "status": "Active"},
        },
    )
    _write_json(
        tasks_path,
        {
            "task1": {
                "name": "Low priority",
                "priority": "Low",
                "status": "Todo",
                "content": "",
                "project_id": "proj1",
                "project_name": "Main",
                "due_date": "2099-01-01",
                "subtask_names": [],
            },
            "task2": {
                "name": "Urgent task",
                "priority": "Urgent",
                "status": "Todo",
                "content": "",
                "project_id": "proj1",
                "project_name": "Main",
                "due_date": "2099-01-01",
                "subtask_names": [],
            },
        },
    )
    task_repo = TaskRepository()
    project_repo = ProjectRepository()
    service = TaskSummaryService(task_repo, project_repo, DummyLogRepo())
    summary = service.build_today_summary()
    assert summary.index("Urgent task") < summary.index("Low priority")
    monkeypatch.delenv("DATA_DIR", raising=False)
    reload(paths)
