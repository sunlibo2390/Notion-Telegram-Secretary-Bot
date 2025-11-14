from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class WeComWebhookClient:
    def __init__(self, webhook_url: str, session: Optional[requests.Session] = None):
        self._webhook_url = webhook_url
        self._session = session or requests.Session()

    def send_text(self, text: str) -> None:
        payload = {
            "msgtype": "text",
            "text": {
                "content": text,
            },
        }
        try:
            response = self._session.post(
                self._webhook_url,
                json=payload,
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("errcode") != 0:
                logger.warning("WeCom webhook error: %s", data)
        except Exception as error:  # pragma: no cover - network failure best effort
            logger.warning("Failed to send WeCom webhook message: %s", error)
