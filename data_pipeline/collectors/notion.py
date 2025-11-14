from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List

import requests

from data_pipeline.storage import paths

logger = logging.getLogger(__name__)


@dataclass
class NotionCollectorConfig:
    api_key: str
    database_ids: Dict[str, str]
    data_dir: Path
    duration_threshold_minutes: int = 30
    sync_interval_seconds: int = 1800
    force_update: bool = False


@dataclass
class NotionCollector:
    config: NotionCollectorConfig
    processors: Iterable[Callable[[], None]] = field(default_factory=list)
    update_marker_filename: str = "last_updated.txt"

    def _update_marker_path(self) -> Path:
        return self.config.data_dir / self.update_marker_filename

    def _read_last_updated(self) -> datetime | None:
        marker = self._update_marker_path()
        if not marker.exists():
            return None
        value = marker.read_text(encoding="utf-8").strip()
        if not value:
            return None
        return datetime.fromisoformat(value)

    def _write_last_updated(self) -> None:
        self._update_marker_path().write_text(
            datetime.now().isoformat(), encoding="utf-8"
        )

    def update_needed(self) -> bool:
        if self.config.force_update:
            return True
        last_updated = self._read_last_updated()
        if not last_updated:
            return True
        delta = datetime.now() - last_updated
        return delta >= timedelta(minutes=self.config.duration_threshold_minutes)

    def _request_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def fetch_database(self, database_id: str) -> Dict:
        url = f"https://api.notion.com/v1/databases/{database_id}/query"
        headers = self._request_headers()
        for _ in range(5):
            logger.info("请求 Notion 数据库：%s", database_id)
            response = requests.post(url, headers=headers, timeout=30)
            if response.status_code == 200:
                logger.info("Notion 数据库 %s 请求成功", database_id)
                return response.json()
            time.sleep(10)
        logger.error("多次重试仍无法获取 Notion 数据库：%s", database_id)
        raise RuntimeError(f"Failed to fetch database {database_id}")

    def _persist_raw_payload(self, key: str, data: Dict) -> None:
        raw_path = paths.raw_json_path(key)
        with raw_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

    def collect_once(self) -> None:
        if not self.update_needed():
            return
        for key, database_id in self.config.database_ids.items():
            payload = self.fetch_database(database_id)
            self._persist_raw_payload(key, payload)
        for processor in self.processors:
            processor()
        self._write_last_updated()

    def run_forever(self) -> None:
        interval = self.config.sync_interval_seconds
        while True:
            try:
                self.collect_once()
            except Exception as error:
                print(f"[collector] error: {error}")
            time.sleep(interval)
