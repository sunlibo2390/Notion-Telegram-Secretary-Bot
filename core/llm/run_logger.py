from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class AgentRunLogger:
    def __init__(self, root_dir: Path):
        self._root = root_dir
        self._root.mkdir(parents=True, exist_ok=True)

    def log(self, chat_id: int, payload: Dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chat_id": chat_id,
            **payload,
        }
        path = self._root / f"{chat_id}.jsonl"
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
