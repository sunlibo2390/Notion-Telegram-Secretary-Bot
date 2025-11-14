import json
from pathlib import Path

from apps.telegram_bot.history.history_store import HistoryStore


def _make_update(chat_id=1, message_id=11, text="hi", update_id=100):
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "date": 1700000000,
            "chat": {"id": chat_id},
            "text": text,
        },
    }


def test_append_and_read_history(tmp_path: Path):
    store = HistoryStore(root_dir=tmp_path)
    update = _make_update()
    store.append_user(update)
    history = store.get_history(1)
    assert len(history) == 1
    assert history[0].text == "hi"
    assert store.last_update_id() == 100


def test_deduplication(tmp_path: Path):
    store = HistoryStore(root_dir=tmp_path)
    update = _make_update()
    store.append_user(update)
    store.append_user(update)
    history = store.get_history(1)
    assert len(history) == 1


def test_append_bot_message(tmp_path: Path):
    store = HistoryStore(root_dir=tmp_path)
    store.append_bot(
        {
            "message_id": 22,
            "date": 1700000100,
            "chat": {"id": 1},
            "text": "pong",
        }
    )
    history = store.get_history(1)
    assert history[-1].direction == "bot"
    assert history[-1].text == "pong"
