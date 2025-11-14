from __future__ import annotations

import json
from pathlib import Path
from dataclasses import asdict
from typing import Dict, List, Optional

from core.domain import LogEntry
from data_pipeline.storage import paths


class LogRepository:
    def __init__(
        self,
        processed_path: Path | None = None,
        custom_path: Path | None = None,
    ):
        self._primary_path = processed_path or paths.processed_json_path(
            "processed_logs"
        )
        self._custom_path = custom_path or paths.processed_json_path(
            "agent_logs"
        )
        self._primary_cache: Dict[str, LogEntry] = {}
        self._custom_cache: Dict[str, LogEntry] = {}
        self._primary_loaded = False
        self._custom_loaded = False

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Dict]:
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _load_primary(self) -> None:
        if self._primary_loaded:
            return
        self._primary_cache = {}
        if self._primary_path.exists():
            raw = self._read_json(self._primary_path)
            for log_id, payload in raw.items():
                payload = dict(payload)
                payload.pop("id", None)
                self._primary_cache[log_id] = LogEntry(id=log_id, **payload)
        self._primary_loaded = True

    def _load_custom(self) -> None:
        if self._custom_loaded:
            return
        self._custom_cache = {}
        if self._custom_path.exists():
            raw = self._read_json(self._custom_path)
            for log_id, payload in raw.items():
                payload = dict(payload)
                payload.pop("id", None)
                self._custom_cache[log_id] = LogEntry(id=log_id, **payload)
        else:
            self._custom_path.parent.mkdir(parents=True, exist_ok=True)
            self._custom_path.write_text("{}", encoding="utf-8")
        self._custom_loaded = True

    def _write_primary(self) -> None:
        if not self._primary_loaded:
            return
        with open(self._primary_path, "w", encoding="utf-8") as file:
            json.dump(
                {log.id: asdict(log) for log in self._primary_cache.values()},
                file,
                ensure_ascii=False,
                indent=4,
            )

    def _write_custom(self) -> None:
        if not self._custom_loaded:
            return
        with open(self._custom_path, "w", encoding="utf-8") as file:
            json.dump(
                {log.id: asdict(log) for log in self._custom_cache.values()},
                file,
                ensure_ascii=False,
                indent=4,
            )

    def refresh(self) -> None:
        self._primary_loaded = False
        self._custom_loaded = False
        self._primary_cache.clear()
        self._custom_cache.clear()
        self._load_primary()
        self._load_custom()

    def list_logs(self) -> List[LogEntry]:
        self._load_primary()
        self._load_custom()
        return list(self._primary_cache.values()) + list(self._custom_cache.values())

    def delete_log(self, log_id: str) -> bool:
        self._load_custom()
        if log_id in self._custom_cache:
            self._custom_cache.pop(log_id, None)
            self._write_custom()
            return True
        self._load_primary()
        if log_id not in self._primary_cache:
            return False
        self._primary_cache.pop(log_id, None)
        self._write_primary()
        return True

    def update_log(
        self,
        log_id: str,
        content: Optional[str] = None,
        task_id: Optional[str] = None,
        task_name: Optional[str] = None,
    ) -> Optional[LogEntry]:
        self._load_custom()
        target_cache = None
        entry = self._custom_cache.get(log_id)
        if entry:
            target_cache = "custom"
        else:
            self._load_primary()
            entry = self._primary_cache.get(log_id)
            if entry:
                target_cache = "primary"
        if not entry:
            return None
        if content:
            entry.content = content
        if task_id is not None:
            entry.task_id = task_id
        if task_name is not None:
            entry.task_name = task_name
        if target_cache == "custom":
            self._custom_cache[log_id] = entry
            self._write_custom()
        else:
            self._primary_cache[log_id] = entry
            self._write_primary()
        return entry

    def add_local_log(self, entry: LogEntry) -> None:
        self._load_custom()
        self._custom_cache[entry.id] = entry
        self._write_custom()
