from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProjectOut(ProjectIn):
    id: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ChatIn(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=200)


class ChatOut(ChatIn):
    id: str
    project_id: str
    created_at: datetime
    model_config = {"from_attributes": True}


class MessageIn(BaseModel):
    role: Literal["user", "assistant", "system"] = "user"
    content: str = Field(min_length=1, max_length=20_000)


class MessageOut(MessageIn):
    id: str
    chat_id: str
    created_at: datetime
    model_config = {"from_attributes": True}


class DatasetOut(BaseModel):
    id: str
    project_id: str
    filename: str
    row_count: int
    columns: list[str]
    profile: dict[str, Any]
    sheets: list[dict[str, Any]] = []
    created_at: datetime


class ChartRequest(BaseModel):
    chart_type: Literal["bar", "line", "scatter", "pie"]
    x: str
    y: str | None = None
    aggregation: Literal["count", "sum", "mean", "min", "max"] = "count"
    limit: int = Field(default=25, ge=1, le=100)


class AnalysisIn(BaseModel):
    dataset_id: str
    prompt: str = Field(min_length=1, max_length=10_000)
    chart: ChartRequest | None = None


class AnalysisOut(BaseModel):
    id: str
    project_id: str
    dataset_id: str
    prompt: str
    result: dict[str, Any]
    chart_spec: dict[str, Any] | None
    status: str
    created_at: datetime


class ChatAnalysisIn(BaseModel):
    dataset_id: str
    prompt: str = Field(min_length=1, max_length=10_000)
