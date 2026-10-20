"""LLM providers: a deterministic mock and an OpenAI-compatible client."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol, Sequence

from .schema import AgentDecision, Article, Citation, ToolObservation, TraceEvent


class LLMProvider(Protocol):
    name: str

    def next_action(
        self,
        question: str,
        trace: Sequence[TraceEvent],
        observations: Sequence[ToolObservation],
        tool_schemas: list[dict[str, Any]],
    ) -> AgentDecision:
        ...


class MockProvider:
    """Deterministic provider for tests, offline demos, and CLI smoke runs.

    It follows the intended loop: search -> get_article -> verify_citation -> final.
    It is not a legal model and must not be presented as one.
    """

    name = "mock"

    def next_action(
        self,
        question: str,
        trace: Sequence[TraceEvent],
        observations: Sequence[ToolObservation],
        tool_schemas: list[dict[str, Any]],
    ) -> AgentDecision:
        if not observations:
            return AgentDecision(
                decision_summary="先检索与问题相关的法条。",
                tool="search_statutes",
                args={"query": question, "top_k": 8},
            )

        last = observations[-1]
        if last.tool == "search_statutes":
            if not last.result.ok:
                failed_searches = [
                    item
                    for item in observations
                    if item.tool == "search_statutes" and not item.result.ok
                ]
                if len(failed_searches) == 1:
                    return AgentDecision(
                        decision_summary="首次检索无结果，改用更短的关键词重试。",
                        tool="search_statutes",
                        args={"query": _rewrite_query(question), "top_k": 8},
                    )
                return _no_evidence("检索重试后仍无结果。")

            articles = _articles_from_result(last.result.data.get("articles"))
            if not articles:
                return _no_evidence("检索结果为空。")

            article = articles[0]
            requested_no = _extract_article_no(question)
            if requested_no is not None:
                article = next(
                    (item for item in articles if item.article_no == requested_no),
                    article,
                )
            return AgentDecision(
                decision_summary=f"检索已定位到第{article.article_no}条，获取完整原文。",
                tool="get_article",
                args={"law": article.law, "article_no": article.article_no},
            )

        if last.tool == "get_article":
            if not last.result.ok:
                return _no_evidence("没有取得可核验的条文原文。")
            article = _article_from_result(last.result.data.get("article"))
            if article is None:
                return _no_evidence("工具没有返回条文原文。")
            quote = article.text[:80]
            return AgentDecision(
                decision_summary=f"取得第{article.article_no}条原文，提交引用核验。",
                tool="verify_citation",
                args={
                    "law": article.law,
                    "article_no": article.article_no,
                    "quote": quote,
                },
            )

        if last.tool == "verify_citation":
            if not last.result.ok:
                return _no_evidence("引用核验失败。")
            article = _article_from_result(last.result.data.get("article"))
            if article is None:
                return _no_evidence("核验工具没有返回条文。")
            return AgentDecision(
                decision_summary="引用已通过核验，形成最终答复。",
                is_final=True,
                answer_summary=f"根据已核验的第{article.article_no}条原文形成答复。",
                citations=[
                    Citation(
                        law=article.law,
                        article_no=article.article_no,
                        quote=article.text[:80],
                    )
                ],
                missing_facts=[],
            )

        return _no_evidence("无法识别当前观察结果。")


class OpenAICompatibleProvider:
    """Thin wrapper around an OpenAI-compatible chat completions endpoint."""

    name = "openai"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "未安装 openai 依赖。请执行 `pip install -e .[llm]`，"
                "或使用 `--provider mock` 离线运行。"
            ) from exc

        import os

        self.model = model or os.getenv("LAWAGENT_MODEL", "gpt-4.1-mini")
        self.client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
        )

    def next_action(
        self,
        question: str,
        trace: Sequence[TraceEvent],
        observations: Sequence[ToolObservation],
        tool_schemas: list[dict[str, Any]],
    ) -> AgentDecision:
        system = (
            "你是劳动法条检索 Agent。你只能基于工具返回的原文工作。"
            "每轮只输出一个 JSON 对象：要么是工具调用，要么是最终答复。"
            "不得输出未出现在本轮工具结果中的法条。"
            "最终答复中的 citation.quote 必须是工具返回 text 的连续片段，"
            "不得使用省略号、概括或改写。"
            "如果证据不足，返回空 citations，并说明无法给出可核验结论。"
            "不要输出完整思维链，只给一句决策摘要。\n"
            f"可用工具：{json.dumps(tool_schemas, ensure_ascii=False)}"
        )
        user = json.dumps(
            {
                "question": question,
                "trace": [event.model_dump(mode="json") for event in trace],
                "observations": [
                    _compact_observation(observation) for observation in observations
                ],
                "response_format": {
                    "tool_call": {
                        "decision_summary": "一句决策摘要",
                        "tool": "search_statutes | get_article | verify_citation",
                        "args": {},
                    },
                    "final": {
                        "decision_summary": "一句决策摘要",
                        "is_final": True,
                        "answer": {
                            "summary": "仅基于已核验条文的简要结论",
                            "citations": [
                                {
                                    "law": "法律名称",
                                    "article_no": "条号",
                                    "quote": "原文连续片段",
                                }
                            ],
                            "missing_facts": [],
                        },
                    },
                },
            },
            ensure_ascii=False,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
        except Exception:
            # Some compatible servers do not implement response_format.
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=1200,
            )

        content = response.choices[0].message.content or "{}"
        payload = _load_json_object(content)
        return _parse_decision(payload)


def _extract_article_no(text: str) -> str | None:
    match = re.search(r"第\s*(\d+)\s*条", text)
    return match.group(1) if match else None


def _rewrite_query(question: str) -> str:
    compact = re.sub(r"[？?！!。，,；;：:\s]+", "", question)
    compact = compact.replace("怎么", "").replace("如何", "")
    rewritten = compact or "劳动法 条文"
    return f"{rewritten} 劳动法"


def _articles_from_result(value: Any) -> list[Article]:
    if not isinstance(value, list):
        return []
    articles: list[Article] = []
    for item in value:
        try:
            articles.append(Article.model_validate(item))
        except Exception:
            continue
    return articles


def _article_from_result(value: Any) -> Article | None:
    if not isinstance(value, dict):
        return None
    try:
        return Article.model_validate(value)
    except Exception:
        return None


def _no_evidence(reason: str) -> AgentDecision:
    return AgentDecision(
        decision_summary=reason,
        is_final=True,
        answer_summary="",
        citations=[],
        missing_facts=[],
    )


def _compact_observation(observation: ToolObservation) -> dict[str, Any]:
    data = observation.result.model_dump(mode="json")
    compact_data = dict(data.get("data") or {})

    if isinstance(compact_data.get("articles"), list):
        compact_data["articles"] = [
            _truncate_article(item) for item in compact_data["articles"]
        ]
    if isinstance(compact_data.get("article"), dict):
        compact_data["article"] = _truncate_article(compact_data["article"])

    data["data"] = compact_data
    return data


def _truncate_article(item: Any, limit: int = 1500) -> Any:
    if not isinstance(item, dict):
        return item
    result = dict(item)
    text = result.get("text")
    if isinstance(text, str) and len(text) > limit:
        result["text"] = text[:limit]
    return result


def _load_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
        else:
            return {}
    return value if isinstance(value, dict) else {}


def _parse_decision(payload: dict[str, Any]) -> AgentDecision:
    final_payload = payload.get("final")
    if not isinstance(final_payload, dict):
        final_payload = payload.get("answer") if isinstance(payload.get("answer"), dict) else None

    if final_payload is not None or payload.get("is_final"):
        source = final_payload or payload
        raw_citations = source.get("citations", [])
        citations: list[Citation] = []
        if isinstance(raw_citations, list):
            for item in raw_citations:
                try:
                    citations.append(Citation.model_validate(item))
                except Exception:
                    continue
        missing_facts = source.get("missing_facts", [])
        if not isinstance(missing_facts, list):
            missing_facts = []
        return AgentDecision(
            decision_summary=str(
                source.get("decision_summary") or payload.get("decision_summary") or ""
            ),
            is_final=True,
            answer_summary=str(source.get("summary") or source.get("answer_summary") or ""),
            citations=citations,
            missing_facts=[str(item) for item in missing_facts],
        )

    tool = payload.get("tool")
    args = payload.get("args", {})
    return AgentDecision(
        decision_summary=str(payload.get("decision_summary") or ""),
        is_final=False,
        tool=str(tool) if tool is not None else None,
        args=args if isinstance(args, dict) else {},
    )