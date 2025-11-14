from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from core.domain import Project
from data_pipeline.storage import paths


class ProjectRepository:
    def __init__(self, processed_path: Path | None = None):
        self._processed_path = processed_path or paths.processed_json_path(
            "processed_projects"
        )
        self._cache: Dict[str, Project] = {}
        self._loaded = False

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Dict]:
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _load(self) -> None:
        if self._loaded:
            return
        if not self._processed_path.exists():
            self._cache = {}
            self._loaded = True
            return
        raw = self._read_json(self._processed_path)
        for project_id, payload in raw.items():
            self._cache[project_id] = Project(id=project_id, **payload)
        self._loaded = True

    def refresh(self) -> None:
        self._loaded = False
        self._cache.clear()
        self._load()

    def list_active_projects(self) -> List[Project]:
        self._load()
        return list(self._cache.values())
