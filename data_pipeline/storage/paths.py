from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", _PROJECT_ROOT / "databases")).resolve()
RAW_JSON_DIR = DATA_DIR / "raw_json"
PROCESSED_DIR = DATA_DIR / "json"
TELEGRAM_HISTORY_DIR = DATA_DIR / "telegram_history"

for directory in (RAW_JSON_DIR, PROCESSED_DIR, TELEGRAM_HISTORY_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def raw_json_path(name: str, suffix: str = ".json") -> Path:
    filename = f"{name}{suffix}" if not name.endswith(suffix) else name
    return RAW_JSON_DIR / filename


def processed_json_path(name: str, suffix: str = ".json") -> Path:
    filename = f"{name}{suffix}" if not name.endswith(suffix) else name
    return PROCESSED_DIR / filename


def history_path(chat_id: Optional[int] = None) -> Path:
    if chat_id is None:
        return TELEGRAM_HISTORY_DIR
    return TELEGRAM_HISTORY_DIR / f"{chat_id}.jsonl"


def metadata_path() -> Path:
    return TELEGRAM_HISTORY_DIR / "metadata.json"
