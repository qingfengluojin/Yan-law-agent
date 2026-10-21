"""Bounded ReAct loop, output guard, and retrieval-only baseline."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .llm import LLMProvider
from .retriever import Retriever
from .schema import (
    TOOL_NAMES,
    Article,
    Citation,
    FinalAnswer,
    RunResult,
    ToolObservation,
    TraceEvent,
)
from .tools import ToolRegistry
from .verify import CitationVerifier


@dataclass(frozen=True)
class AgentConfig:
    max_steps: int = 5
    # Four calls are required for one recovery path:
    # failed search -> rewritten search -> get_article -> verify_citation.
    max_tool_calls: int = 4
    no_progress_window: int = 2
    answer_mode: Literal["extractive", "advisory"] = "extractive"


class AgentRunner:
    """A deliberately small, auditable agent loop."""

    def __init__(
        self,
        retriever: Retriever,
        provider: LLMProvider,
        config: AgentConfig | None = None,
    ):
        self.retriever = retriever
        self.provider = provider
        self.config = config or AgentConfig()
        self.tools = ToolRegistry(retriever)
        self.verifier = CitationVerifier(retriever)

    def run(self, question: str) -> RunResult:
        trace: list[TraceEvent] = []
        observations: list[ToolObservation] = []
        seen_article_ids: set[str] = set()
        duplicate_calls: set[str] = set()
        tool_calls = 0
        consecutive_failures = 0
        step = 0

        for step in range(1, self.config.max_steps + 1):
            started = time.perf_counter()
            try:
                decision = self.provider.next_action(
                    question,
                    trace,
                    observations,
                    self.tools.schemas(),
                )
            except Exception as exc:
                trace.append(
                    TraceEvent(
                        step=step,
                        decision_summary="模型 provider 调用失败。",
                        ok=False,
                        reason="provider_error",
                        hint=f"{type(exc).__name__}: {exc}",
                    )
                )
                return self._terminate(
                    question,
                    trace,
                    observations,
                    step,
                    tool_calls,
                    reason="provider_error",
                )
            decision_latency_ms = (time.perf_counter() - started) * 1000

            if decision.is_final:
                raw_citations = list(decision.citations)
                model_summary = decision.answer_summary.strip()
                model_missing_facts = list(decision.missing_facts)
                answer = self._finalize(
                    decision,
                    seen_article_ids=seen_article_ids,
                    step=step,
                    trace=trace,
                    decision_latency_ms=decision_latency_ms,
                )
                return RunResult(
                    question=question,
                    mode="agent",
                    answer=answer,
                    trace=trace,
                    raw_citations=raw_citations,
                    model_summary=model_summary,
                    model_missing_facts=model_missing_facts,
                    steps=step,
                    tool_calls=tool_calls,
                )

            tool = decision.tool
            if tool not in TOOL_NAMES:
                consecutive_failures += 1
                trace.append(
                    TraceEvent(
                        step=step,
                        decision_summary=decision.decision_summary,
                        tool=tool,
                        args=decision.args,
                        ok=False,
                        reason="unknown_tool",
                        hint=f"可用工具：{', '.join(TOOL_NAMES)}。",
                        latency_ms=decision_latency_ms,
                    )
                )
                if consecutive_failures >= self.config.no_progress_window:
                    return self._terminate(
                        question,
                        trace,
                        observations,
                        step,
                        tool_calls,
                        reason="no_progress",
                    )
                continue

            call_key = _call_key(tool, decision.args)
            if call_key in duplicate_calls:
                consecutive_failures += 1
                trace.append(
                    TraceEvent(
                        step=step,
                        decision_summary=decision.decision_summary,
                        tool=tool,
                        args=decision.args,
                        ok=False,
                        reason="duplicate_call",
                        hint="该调用已经执行过，请改写查询或参数。",
                        latency_ms=decision_latency_ms,
                    )
                )
                if consecutive_failures >= self.config.no_progress_window:
                    return self._terminate(
                        question,
                        trace,
                        observations,
                        step,
                        tool_calls,
                        reason="no_progress",
                    )
                continue

            if consecutive_failures >= self.config.no_progress_window:
                return self._terminate(
                    question,
                    trace,
                    observations,
                    step,
                    tool_calls,
                    reason="no_progress",
                )

            if tool_calls >= self.config.max_tool_calls:
                return self._terminate(
                    question,
                    trace,
                    observations,
                    step,
                    tool_calls,
                    reason="budget_exhausted",
                )

            tool_started = time.perf_counter()
            result = self.tools.execute(tool, decision.args)
            tool_latency_ms = (time.perf_counter() - tool_started) * 1000

            duplicate_calls.add(call_key)
            tool_calls += 1
            observations.append(ToolObservation(tool=tool, args=decision.args, result=result))
            seen_article_ids.update(result.top_ids)
            trace.append(
                TraceEvent(
                    step=step,
                    decision_summary=decision.decision_summary,
                    tool=tool,
                    args=decision.args,
                    ok=result.ok,
                    reason=result.reason,
                    hint=result.hint,
                    top_ids=result.top_ids,
                    latency_ms=tool_latency_ms,
                )
            )

            if result.ok:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= self.config.no_progress_window:
                    return self._terminate(
                        question,
                        trace,
                        observations,
                        step,
                        tool_calls,
                        reason="no_progress",
                    )

        return self._terminate(
            question,
            trace,
            observations,
            step or self.config.max_steps,
            tool_calls,
            reason="max_steps",
        )

    def _finalize(
        self,
        decision,
        *,
        seen_article_ids: set[str],
        step: int,
        trace: list[TraceEvent],
        decision_latency_ms: float,
    ) -> FinalAnswer:
        verified, failures = self.verifier.verify_all(
            decision.citations,
            allowed_article_ids=seen_article_ids,
        )

        if not verified:
            hint = None
            if failures:
                hint = "; ".join(
                    f"{failure.reason or 'verification_failed'}: {failure.hint or ''}".strip()
                    for failure in failures[:3]
                )
            trace.append(
                TraceEvent(
                    step=step,
                    decision_summary=decision.decision_summary,
                    ok=False,
                    reason="no_verified_citation",
                    hint=hint or "本轮没有可核验引用。",
                    latency_ms=decision_latency_ms,
                )
            )
            return FinalAnswer(
                status="no_evidence",
                answer_mode=self.config.answer_mode,
                summary="无法给出可核验结论：本轮没有通过存在性与逐字核验的引用。",
                citations=[],
                missing_facts=decision.missing_facts,
            )

        status = "ok" if not failures else "degraded"
        if self.config.answer_mode == "extractive":
            summary = (
                f"已核验 {len(verified)} 条法条引用片段。"
                "本工具默认只展示引用片段，不输出法律适用结论。"
            )
            review_required = False
        else:
            model_summary = decision.answer_summary.strip()
            summary = (
                "以下为模型生成的辅助性说明，未经法律适用性核验；"
                "所附引用原文已通过存在性与逐字核验。"
            )
            if model_summary:
                summary += f"\n\n{model_summary}"
            review_required = True
        if failures:
            summary = "部分引用未通过核验，仅保留已核验部分。\n\n" + summary

        trace.append(
            TraceEvent(
                step=step,
                decision_summary=decision.decision_summary,
                ok=status == "ok",
                reason=None if status == "ok" else "partial_citation_failure",
                hint=None
                if status == "ok"
                else f"有 {len(failures)} 条引用未通过核验，已从最终输出中移除。",
                latency_ms=decision_latency_ms,
            )
        )
        return FinalAnswer(
            status=status,
            answer_mode=self.config.answer_mode,
            summary=summary,
            citations=verified,
            missing_facts=decision.missing_facts,
            review_required=review_required,
        )

    def _terminate(
        self,
        question: str,
        trace: list[TraceEvent],
        observations: Sequence[ToolObservation],
        step: int,
        tool_calls: int,
        *,
        reason: str,
    ) -> RunResult:
        articles = _unique_articles(observations)
        citations: list[Citation] = []
        for article in articles[:5]:
            citation = Citation(
                law=article.law,
                article_no=article.article_no,
                quote=article.text,
            )
            result = self.verifier.verify(citation)
            if result.ok and result.citation is not None:
                citations.append(result.citation)

        trace.append(
            TraceEvent(
                step=step,
                decision_summary="安全终止并降级输出。",
                ok=False,
                reason=reason,
                hint="只展示本轮已获取的条文原文，不输出法律结论。",
            )
        )

        if citations:
            answer = FinalAnswer(
                status="degraded",
                answer_mode="extractive",
                summary=(
                    f"检索未收敛（{reason}）。以下仅列出本轮已获取的条文原文，不构成法律结论。"
                ),
                citations=citations,
            )
        else:
            answer = FinalAnswer(
                status="no_evidence",
                answer_mode="extractive",
                summary=f"检索未收敛（{reason}），且没有取得可核验的条文原文。",
                citations=[],
            )

        return RunResult(
            question=question,
            mode="agent",
            answer=answer,
            trace=trace,
            steps=step,
            tool_calls=tool_calls,
        )


def run_baseline(question: str, retriever: Retriever, *, top_k: int = 5) -> RunResult:
    """Single retrieval, no multi-step completion and no model call."""

    started = time.perf_counter()
    articles = retriever.search(question, top_k=top_k)
    latency_ms = (time.perf_counter() - started) * 1000
    citations = [
        Citation(
            law=article.law,
            article_no=article.article_no,
            quote=article.text,
            source_url=article.source_url,
            article_id=article.article_id,
        )
        for article in articles
    ]
    trace = [
        TraceEvent(
            step=1,
            decision_summary="baseline：单次检索，不做多步补检索。",
            tool="search_statutes",
            args={"query": question, "top_k": top_k},
            ok=bool(articles),
            reason=None if articles else "no_results",
            hint=None if articles else "baseline 没有命中条文。",
            top_ids=[article.article_id for article in articles],
            latency_ms=latency_ms,
        )
    ]
    if not articles:
        answer = FinalAnswer(
            status="no_evidence",
            answer_mode="extractive",
            summary="baseline 单次检索没有命中条文。",
            citations=[],
        )
    else:
        answer = FinalAnswer(
            status="ok",
            answer_mode="extractive",
            summary=(
                f"baseline 单次检索返回 {len(articles)} 条候选条文。"
                "以下仅列出原文，未进行多步补检索。"
            ),
            citations=citations,
        )
    return RunResult(
        question=question,
        mode="baseline",
        answer=answer,
        trace=trace,
        raw_citations=citations,
        steps=1,
        tool_calls=1,
    )


def _call_key(tool: str, args: dict) -> str:
    return f"{tool}:{json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"


def _unique_articles(observations: Sequence[ToolObservation]) -> list[Article]:
    result: list[Article] = []
    seen: set[str] = set()
    for observation in observations:
        data = observation.result.data
        raw_articles = data.get("articles")
        if isinstance(raw_articles, list):
            for raw in raw_articles:
                _append_article(result, seen, raw)
        raw_article = data.get("article")
        if isinstance(raw_article, dict):
            _append_article(result, seen, raw_article)
    return result


def _append_article(result: list[Article], seen: set[str], raw) -> None:
    try:
        article = Article.model_validate(raw)
    except Exception:
        return
    if article.article_id not in seen:
        result.append(article)
        seen.add(article.article_id)
