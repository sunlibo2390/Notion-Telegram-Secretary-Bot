from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from data_pipeline.storage import paths


def _to_iso(timestamp: int | float | str | None) -> str:
    if timestamp is None:
        return datetime.utcnow().isoformat()
    if isinstance(timestamp, (int, float)):
        return datetime.utcfromtimestamp(timestamp).isoformat()
    return str(timestamp)


@dataclass
class HistoryEntry:
    chat_id: int
    message_id: int
    direction: str
    text: str
    timestamp: str
    reply_to: Optional[int]
    raw: Dict


class HistoryStore:
    def __init__(self, root_dir: Path | None = None):
        self._root = Path(root_dir) if root_dir else paths.history_path()
        self._root.mkdir(parents=True, exist_ok=True)
        self._archive_dir = self._root / "archive"
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_path = self._root / "metadata.json"
        if not self._metadata_path.exists():
            self._metadata_path.write_text(json.dumps({}, indent=2))
        self._cache: Dict[int, set[int]] = {}
        self._metadata = self._load_metadata()

    def _load_metadata(self) -> Dict[str, int]:
        with open(self._metadata_path, "r", encoding="utf-8") as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                return {}

    def _save_metadata(self) -> None:
        with open(self._metadata_path, "w", encoding="utf-8") as file:
            json.dump(self._metadata, file, ensure_ascii=False, indent=2)

    def last_update_id(self) -> Optional[int]:
        return self._metadata.get("last_update_id")

    def record_update_checkpoint(self, update_id: Optional[int]) -> None:
        if update_id is None:
            return
        self._metadata["last_update_id"] = update_id
        self._save_metadata()

    def _chat_path(self, chat_id: int) -> Path:
        return self._root / f"{chat_id}.jsonl"

    def _ensure_cache(self, chat_id: int) -> None:
        if chat_id in self._cache:
            return
        path = self._chat_path(chat_id)
        ids = set()
        if path.exists():
            with open(path, "r", encoding="utf-8") as file:
                for line in file:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ids.add(record.get("message_id"))
        self._cache[chat_id] = ids

    def _append_entry(self, entry: HistoryEntry) -> bool:
        self._ensure_cache(entry.chat_id)
        seen = self._cache[entry.chat_id]
        if entry.message_id in seen:
            return False
        seen.add(entry.message_id)
        path = self._chat_path(entry.chat_id)
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry.__dict__, ensure_ascii=False) + "\n")
        return True

    def append_user(self, update: Dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            self.record_update_checkpoint(update.get("update_id"))
            return
        entry = HistoryEntry(
            chat_id=message["chat"]["id"],
            message_id=message["message_id"],
            direction="user",
            text=message.get("text", ""),
            timestamp=_to_iso(message.get("date")),
            reply_to=(message.get("reply_to_message") or {}).get("message_id"),
            raw=message,
        )
        self._append_entry(entry)
        self.record_update_checkpoint(update.get("update_id"))

    def append_bot(self, message: Dict) -> None:
        entry = HistoryEntry(
            chat_id=message["chat"]["id"],
            message_id=message["message_id"],
            direction="bot",
            text=message.get("text", ""),
            timestamp=_to_iso(message.get("date")),
            reply_to=(message.get("reply_to_message") or {}).get("message_id"),
            raw=message,
        )
        self._append_entry(entry)

    def get_history(self, chat_id: int, limit: int = 50) -> List[HistoryEntry]:
        path = self._chat_path(chat_id)
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as file:
            entries = [
                HistoryEntry(**json.loads(line))
                for line in file
                if line.strip()
            ]
        if len(entries) <= limit:
            return entries
        return entries[0:1] + entries[-limit:]

    def clear_chat(self, chat_id: int) -> None:
        self._cache.pop(chat_id, None)
        path = self._chat_path(chat_id)
        if path.exists():
            # 北京时间
            timestamp = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y%m%d%H%M%S")
            archive_path = self._archive_dir / f"{chat_id}_{timestamp}.jsonl"
            path.rename(archive_path)
