from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    name: str
    arguments: str
    call_id: str | None = None


@dataclass
class ChatResponse:
    content: str | None
    tool_calls: List[ToolCall]
    usage: Dict[str, Any]


class OpenAIChatClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        provider: str = "openai",
    ):
        self._client = OpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model
        self._provider = provider

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
    ) -> ChatResponse:
        logger.info(
            "调用 OpenAI ChatCompletions，模型=%s，messages=%d，tools=%d",
            self._model,
            len(messages),
            len(tools or []),
        )
        for i, message in enumerate(messages):
            role = message.get("role", "unknown")
            content = message.get("content", "")
            if role != "tool":
                logger.debug("Message %d - Role: %s, Content: %s", i, role, content)
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                temperature=temperature,
            )
        except Exception as exc:
            logger.exception("LLM 调用失败: %s", exc)
            raise
        choice = response.choices[0].message
        logger.debug("LLM 输出 content=%s", choice.content)
        tool_calls = []
        for call in choice.tool_calls or []:
            tool_calls.append(
                ToolCall(
                    name=call.function.name,
                    arguments=call.function.arguments,
                    call_id=getattr(call, "id", None),
                )
            )
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
        return ChatResponse(
            content=choice.content,
            tool_calls=tool_calls,
            usage=usage,
        )
