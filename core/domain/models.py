from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass(slots=True)
class Project:
    id: str
    name: str
    status: str


@dataclass(slots=True)
class Task:
    id: str
    name: str
    priority: str
    status: str
    content: str
    project_id: Optional[str]
    project_name: str
    due_date: Optional[str]
    subtask_names: List[str] = field(default_factory=list)
    page_url: Optional[str] = None


@dataclass(slots=True)
class LogEntry:
    id: str
    name: str
    status: str
    content: str
    task_id: Optional[str]
    task_name: str


@dataclass(slots=True)
class Intervention:
    level: str
    message: str
    reason: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class UserProfile:
    name: str
    tone: str
    working_hours: List[str]
