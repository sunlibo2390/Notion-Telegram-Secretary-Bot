from pathlib import Path

from apps.telegram_bot.history.history_store import HistoryStore
from core.llm.agent import LLMAgent
from core.llm.context_builder import AgentContextBuilder
from core.llm.tools import build_default_tools
from core.services.logbook_service import LogRecordResult


class DummyTaskService:
    def build_today_summary(self):
        return "今日任务：测试任务 A"

    def build_task_payloads(self):
        return [
            {
                "id": "task1",
                "name": "测试任务 A",
                "priority": "High",
                "status": "Todo",
                "due_date": "2099-01-01",
                "project": "Main",
                "content": "内容",
                "subtasks": [],
                "logs": [],
            }
        ]


class DummyStatusGuard:
    def evaluate(self):
        return []


class DummyLogbookService:
    def record_log(self, text: str) -> LogRecordResult:
        return LogRecordResult(message=f"日志已保存：{text}", task_name=None, stored=True)


def _build_agent(tmp_path: Path) -> LLMAgent:
    history = HistoryStore(root_dir=tmp_path / "history")
    profile = tmp_path / "profile.md"
    profile.write_text("测试用户，讨厌拖延。", encoding="utf-8")
    builder = AgentContextBuilder(history, profile)
    task_service = DummyTaskService()
    logbook_service = DummyLogbookService()
    status_guard = DummyStatusGuard()
    tools = build_default_tools(task_service, logbook_service, status_guard)
    return LLMAgent(
        context_builder=builder,
        task_service=task_service,
        logbook_service=logbook_service,
        status_guard=status_guard,
        tools=tools,
        llm_client=None,
    )


def test_llm_agent_fallback_tasks(tmp_path):
    agent = _build_agent(tmp_path)
    responses = agent.handle(chat_id=1, user_text="/tasks")
    assert any("今日任务" in resp for resp in responses)


def test_llm_agent_fallback_log(tmp_path):
    agent = _build_agent(tmp_path)
    responses = agent.handle(chat_id=1, user_text="#log 进度更新")
    assert "日志已保存" in responses[0]
