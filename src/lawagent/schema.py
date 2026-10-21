"""Pydantic models used across the law-agent pipeline."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DISCLAIMER = (
    "本工具仅提供法条检索与引用核验，不构成法律意见。"
    "法条数据以官方来源为准，请在使用前核对最新版本。"
)

TOOL_NAMES = ("search_statutes", "get_article", "verify_citation")


class Article(BaseModel):
    """One verified statutory article from data/articles.jsonl."""

    model_config = ConfigDict(extra="forbid")

    law: str
    law_type: Literal["法律", "行政法规"] = "法律"
    article_no: str
    text: str
    topic: str
    source_url: str
    verified_at: date
    review_status: Literal["self_checked", "independently_verified"] = "self_checked"
    reviewer: str = ""
    status: Literal["current"] = "current"

    @field_validator("law", "article_no", "text", "topic", "source_url")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be blank")
        return value

    @field_validator("article_no", mode="before")
    @classmethod
    def _article_no_to_str(cls, value: Any) -> str:
        return str(value).strip()

    @property
    def article_id(self) -> str:
        return f"{self.law}#{self.article_no}"


class Citation(BaseModel):
    """A citation proposed by the model or produced by the output guard."""

    model_config = ConfigDict(extra="ignore")

    law: str
    article_no: str
    quote: str
    source_url: str = ""
    article_id: str = ""

    @field_validator("law", "article_no", "quote")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be blank")
        return value

    @field_validator("article_no", mode="before")
    @classmethod
    def _article_no_to_str(cls, value: Any) -> str:
        return str(value).strip()


class AgentDecision(BaseModel):
    """Normalized model decision for one ReAct step."""

    model_config = ConfigDict(extra="ignore")

    decision_summary: str = ""
    is_final: bool = False
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    answer_summary: str = ""
    citations: list[Citation] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    """Structured observation returned to the model."""

    model_config = ConfigDict(extra="ignore")

    ok: bool
    tool: str
    reason: str | None = None
    hint: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    top_ids: list[str] = Field(default_factory=list)


class ToolObservation(BaseModel):
    """A tool call plus its observation, shown to the LLM provider."""

    model_config = ConfigDict(extra="ignore")

    tool: str
    args: dict[str, Any]
    result: ToolResult


class TraceEvent(BaseModel):
    """Auditable trace entry. It intentionally excludes hidden chain-of-thought."""

    model_config = ConfigDict(extra="ignore")

    step: int
    decision_summary: str = ""
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool | None = None
    reason: str | None = None
    hint: str | None = None
    top_ids: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0


class RunMeta(BaseModel):
    """Reproducibility metadata attached to a CLI run."""

    model_config = ConfigDict(extra="ignore")

    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    data_path: str = ""
    data_sha256: str = ""
    git_commit: str = ""
    git_dirty: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FinalAnswer(BaseModel):
    """Final, code-guarded output."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["ok", "degraded", "no_evidence"] = "ok"
    answer_mode: Literal["extractive", "advisory"] = "extractive"
    summary: str
    citations: list[Citation] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    review_required: bool = False
    disclaimer: str = DISCLAIMER


class RunResult(BaseModel):
    """Everything needed to audit one CLI run."""

    model_config = ConfigDict(extra="ignore")

    question: str
    mode: Literal["agent", "baseline"]
    answer: FinalAnswer
    trace: list[TraceEvent] = Field(default_factory=list)
    raw_citations: list[Citation] = Field(default_factory=list)
    run_meta: RunMeta = Field(default_factory=RunMeta)
    steps: int = 0
    tool_calls: int = 0
