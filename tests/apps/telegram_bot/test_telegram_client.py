from unittest.mock import Mock

from apps.telegram_bot.clients.telegram_client import TelegramBotClient
from apps.telegram_bot.history.history_store import HistoryStore


class DummyStore(HistoryStore):
    def __init__(self):
        pass

    def append_bot(self, message):
        self.last_message = message


def test_send_message_persists_to_history(monkeypatch, tmp_path):
    history = DummyStore()

    session = Mock()
    session.post.return_value.json.return_value = {
        "ok": True,
        "result": {
            "message_id": 3,
            "date": 1700000000,
            "chat": {"id": 1},
            "text": "hello",
        },
    }
    session.post.return_value.raise_for_status.return_value = None

    client = TelegramBotClient(
        token="TEST",
        history_store=history,
        base_url="https://example.com/botTEST",
        session=session,
    )
    client.send_message(chat_id=1, text="hi")
    assert history.last_message["text"] == "hello"
    session.post.assert_called_once()


def test_get_updates(monkeypatch):
    history = DummyStore()
    session = Mock()
    session.get.return_value.json.return_value = {
        "ok": True,
        "result": [{"update_id": 1, "message": {"message_id": 2}}],
    }
    session.get.return_value.raise_for_status.return_value = None
    client = TelegramBotClient(
        token="TEST",
        history_store=history,
        base_url="https://example.com/botTEST",
        session=session,
    )
    updates = client.get_updates(offset=1, timeout=1)
    assert updates[0]["update_id"] == 1
    session.get.assert_called_once()
