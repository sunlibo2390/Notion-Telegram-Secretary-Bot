from __future__ import annotations
import re
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from apps.telegram_bot.history.history_store import HistoryStore
from .wecom_client import WeComWebhookClient

logger = logging.getLogger(__name__)


class TelegramAPIError(RuntimeError):
    pass


@dataclass
class TelegramBotClient:
    token: str
    history_store: HistoryStore
    base_url: str | None = None
    request_timeout: int = 30
    session: Optional[requests.Session] = None
    wecom_client: Optional[WeComWebhookClient] = None

    def __post_init__(self):
        self.base_url = self.base_url or f"https://api.telegram.org/bot{self.token}"
        self.session = self.session or requests.Session()

    # def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
    #     response.raise_for_status()
    #     payload = response.json()
    #     if not payload.get("ok", True):
    #         raise TelegramAPIError(payload.get("description", "Unknown error"))
    #     return payload
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        try:
            response.raise_for_status()
        except requests.HTTPError:
            # 打印原始响应内容，里面有 Telegram 给的详细错误
            try:
                data = response.json()
            except ValueError:
                data = response.text

            raise RuntimeError(f"Telegram API error {response.status_code}: {data}")

        # 正常情况
        try:
            return response.json()
        except ValueError:
            return response.text


    def get_updates(self, offset: int | None = None, timeout: int = 25):
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        response = self.session.get(
            f"{self.base_url}/getUpdates",
            params=params,
            timeout=self.request_timeout,
        )
        payload = self._handle_response(response)
        return payload.get("result", [])

    def send_message(self, chat_id: int, text: str, parse_mode: str | None = "Markdown", **kwargs):
        print("Sending message:", [text])
        data = {"chat_id": chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        data.update(kwargs)
        response = self.session.post(
            f"{self.base_url}/sendMessage",
            data=data,
            timeout=self.request_timeout,
        )
        payload = self._handle_response(response)
        message = payload["result"]
        self.history_store.append_bot(message)
        if self.wecom_client:
            self._mirror_to_wecom(text)
        return message

    def _mirror_to_wecom(self, text: str) -> None:
        try:
            self.wecom_client.send_text(text)
        except Exception as error:  # pragma: no cover - best effort logging
            logger.warning("Mirror message to WeCom failed: %s", error)

    # def escape_markdown_v2(self, text: str) -> str:
    #     """
    #     Escape all special characters for Telegram MarkdownV2.
    #     """
    #     special_chars = r'_*[]()~`>#+-=|{}!'
        
    #     escaped = ""
    #     for ch in text:
    #         if ch in special_chars:
    #             escaped += f"\{ch}"
    #         else:
    #             escaped += ch
    #     return escaped

    # def escape_markdown_v2(self, text: str) -> str:
    #     # 必须转义的 MarkdownV2 字符
    #     escape_chars = r'[_*\[\]()~`>#+\-=|{}.!]'
    #     return re.sub(escape_chars, lambda m: '\\' + m.group(0), text)
