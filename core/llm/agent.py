from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from core.llm.context_builder import AgentContextBuilder
from core.llm.openai_client import ChatResponse, OpenAIChatClient
from core.llm.run_logger import AgentRunLogger
from core.llm.tools import AgentTool
from core.services import LogbookService, StatusGuard, TaskSummaryService

logger = logging.getLogger(__name__)


class LLMAgent:
    def __init__(
        self,
        context_builder: AgentContextBuilder,
        task_service: TaskSummaryService,
        logbook_service: LogbookService,
        status_guard: StatusGuard,
        tools: List[AgentTool],
        llm_client: OpenAIChatClient | None = None,
        temperature: float = 0.3,
        run_logger: AgentRunLogger | None = None,
    ):
        self._context_builder = context_builder
        self._task_service = task_service
        self._logbook_service = logbook_service
        self._status_guard = status_guard
        self._tools = {tool.name: tool for tool in tools}
        self._llm_client = llm_client
        self._temperature = temperature
        self._logger = run_logger

    def handle(self, chat_id: int, user_text: str) -> List[str]:
        log_payload: Dict[str, Any] = {"user_text": user_text}
        stages: List[Dict[str, Any]] = []
        logger.info("收到用户(%s)输入：%s", chat_id, user_text)
        if self._llm_client:
            try:
                logger.info("使用 LLM 处理用户(%s)输入", chat_id)
                responses, meta, stages = self._handle_with_llm(chat_id, user_text)
            except Exception as exc:  # pragma: no cover - network errors
                logger.warning("LLM 调用失败，回退到规则逻辑: %s", exc)
                responses, meta, stages = self._fallback(
                    user_text, reason="llm_error", error=str(exc)
                )
        else:
            responses, meta, stages = self._fallback(
                user_text, reason="llm_disabled"
            )
        if self._logger:
            log_payload.update(meta)
            log_payload["responses"] = responses
            log_payload["stages"] = stages
            self._logger.log(chat_id, log_payload)
        logger.info(
            "用户(%s)处理完成，模式=%s，阶段=%s，回复=%s",
            chat_id,
            meta.get("mode"),
            [stage.get("stage") for stage in stages],
            responses,
        )
        return responses

    def _handle_with_llm(
        self, chat_id: int, user_text: str
    ) -> (List[str], Dict[str, Any], List[Dict[str, Any]]):
        messages = self._context_builder.build_messages(chat_id, user_text)
        tools_schema = [tool.to_openai_schema() for tool in self._tools.values()]
        logger.info("向 LLM 发送请求，消息数=%d，工具数=%d", len(messages), len(tools_schema))
        response = self._llm_client.chat(
            messages=messages, tools=tools_schema, temperature=self._temperature
        )
        meta: Dict[str, Any] = {
            "mode": "llm",
            "initial_tool_calls": [call.name for call in response.tool_calls],
            "usage_initial": response.usage,
        }
        stages: List[Dict[str, Any]] = [
            {
                "stage": "llm_initial",
                "reply": response.content,
                "tool_calls": [call.name for call in response.tool_calls],
                "usage": response.usage,
            }
        ]
        messages.append(_assistant_or_tool_message(response))
        if response.tool_calls:
            logger.info(
                "LLM 请求调用工具：%s，开始执行",
                [call.name for call in response.tool_calls],
            )
            observations, tool_results = self._execute_tool_calls(
                response.tool_calls, chat_id
            )
            meta["tool_results"] = tool_results
            for obs in observations:
                messages.append(obs)
            stages.append(
                {
                    "stage": "tool_execution",
                    "results": tool_results,
                }
            )
            logger.info(
                "LLM 请求工具：%s，执行结果：%s",
                [call.name for call in response.tool_calls],
                tool_results,
            )
            logger.info("工具执行完成，回传 observation 后再次请求 LLM")

            final = self._llm_client.chat(
                messages=messages, tools=tools_schema, temperature=self._temperature
            )
            meta["usage_final"] = final.usage
            stages.append(
                {
                    "stage": "llm_final",
                    "reply": final.content,
                    "usage": final.usage,
                }
            )
            return [final.content or "（LLM 未返回内容）"], meta, stages
        return [response.content or "（LLM 未返回内容）"], meta, stages

    def _execute_tool_calls(self, tool_calls, chat_id: int):
        observations = []
        results = []
        for idx, call in enumerate(tool_calls):
            tool = self._tools.get(call.name)
            call_id = call.call_id or f"call-{idx}"
            if not tool:
                observations.append(
                    {
                        "role": "tool",
                        "name": call.name,
                        "tool_call_id": call_id,
                        "content": f"未知工具 {call.name}",
                    },
                )
                results.append({"name": call.name, "status": "missing"})
                continue
            try:
                result = tool.execute(call.arguments, chat_id)
                content = _safe_json_dump(result)
                observations.append(
                    {
                        "role": "tool",
                        "name": call.name,
                        "tool_call_id": call_id,
                        "content": content,
                    }
                )
                results.append({"name": call.name, "status": "ok"})
            except Exception as exc:
                observations.append(
                    {
                        "role": "tool",
                        "name": call.name,
                        "tool_call_id": call_id,
                        "content": _safe_json_dump({"error": str(exc)}),
                    },
                )
                results.append(
                    {"name": call.name, "status": "error", "error": str(exc)}
                )
        return observations, results

    def _fallback(
        self, text: str, reason: str, error: str | None = None
    ) -> (List[str], Dict[str, Any], List[Dict[str, Any]]):
        logger.info("进入 fallback 模式，原因=%s，错误=%s", reason, error)
        lowered = text.lower()
        if lowered.startswith("/tasks") or lowered.startswith("/today"):
            response = self._task_service.build_today_summary()
            meta = {"mode": "fallback", "reason": reason, "error": error}
            return (
                [response],
                meta,
                [{"stage": "fallback", "reply": response}],
            )
        if lowered.startswith("/focus"):
            interventions = self._status_guard.evaluate()
            if not interventions:
                return (
                    [_escape_md("暂无异常，继续推进。", wrap=True)],
                    {"mode": "fallback", "reason": reason, "error": error},
                    [
                        {
                            "stage": "fallback",
                            "reply": "暂无异常，继续推进。",
                        }
                    ],
                )
            items = "\n".join(
                f"- {_escape_md(i.message)}" for i in interventions
            )
            return (
                [items],
                {"mode": "fallback", "reason": reason, "error": error},
                [
                    {
                        "stage": "fallback",
                        "reply": ";".join(i.message for i in interventions),
                    }
                ],
            )
        if lowered.startswith("#log"):
            result = self._logbook_service.record_log(text)
            return (
                [_escape_md(result.message, wrap=True)],
                {"mode": "fallback", "reason": reason, "error": error},
                [{"stage": "fallback", "reply": result.message}],
            )
        return (
            [
                _escape_md(
                    "记录已收到。当前为 fallback 模式，请使用 /tasks、/focus 或 #log。", wrap=True
                )
            ],
            {"mode": "fallback", "reason": reason, "error": error},
            [
                {
                    "stage": "fallback",
                    "reply": (
                        "记录已收到。Fallback 模式"
                    ),
                }
            ],
        )


def _assistant_or_tool_message(response: ChatResponse) -> Dict:
    if response.tool_calls:
        tool_entries = []
        for idx, call in enumerate(response.tool_calls):
            call_id = call.call_id or f"call-{idx}"
            call.call_id = call_id
            tool_entries.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
            )
        return {
            "role": "assistant",
            "content": response.content or "",
            "tool_calls": tool_entries,
        }
    return {"role": "assistant", "content": response.content or ""}


def _escape_md(text: str, wrap: bool = False) -> str:
    special_chars = ["\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
    result = text
    # for ch in special_chars:
    #     result = result.replace(ch, f"\\{ch}")
    # if wrap:
    #     return f"_{result}_"
    return result


def _safe_json_dump(value: Any) -> str:
    def _convert(obj: Any):
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, list):
            return [_convert(item) for item in obj]
        if isinstance(obj, dict):
            return {key: _convert(val) for key, val in obj.items()}
        return obj

    try:
        return json.dumps(_convert(value), ensure_ascii=False)
    except Exception:
        return json.dumps({"repr": repr(value)}, ensure_ascii=False)
