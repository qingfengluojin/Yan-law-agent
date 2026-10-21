from __future__ import annotations

import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from lawagent.agent import AgentConfig, AgentRunner
from lawagent.llm import MockProvider
from lawagent.retriever import Retriever
from lawagent.schema import AgentDecision, Citation, ToolObservation, TraceEvent

FIXTURE = Path(__file__).parent / "fixtures/articles.jsonl"


class AlwaysSearchProvider:
    name = "always-search"

    def __init__(self, queries: list[str]):
        self.queries = queries
        self.calls = 0

    def next_action(
        self,
        question: str,
        trace: Sequence[TraceEvent],
        observations: Sequence[ToolObservation],
        tool_schemas: list[dict[str, Any]],
    ) -> AgentDecision:
        query = self.queries[min(self.calls, len(self.queries) - 1)]
        self.calls += 1
        return AgentDecision(
            decision_summary="继续检索",
            tool="search_statutes",
            args={"query": query},
        )


class UnsupportedCitationProvider:
    name = "unsupported-citation"

    def __init__(self) -> None:
        self.calls = 0

    def next_action(
        self,
        question: str,
        trace: Sequence[TraceEvent],
        observations: Sequence[ToolObservation],
        tool_schemas: list[dict[str, Any]],
    ) -> AgentDecision:
        self.calls += 1
        if self.calls == 1:
            return AgentDecision(
                decision_summary="只获取第2条",
                tool="get_article",
                args={"law": "测试劳动法", "article_no": "2"},
            )
        return AgentDecision(
            decision_summary="引用本轮未获取的第1条",
            is_final=True,
            answer_summary="这是一个不应被接受的结论。",
            citations=[
                Citation(
                    law="测试劳动法",
                    article_no="1",
                    quote="用人单位应当依法为劳动者缴纳社会保险费。",
                )
            ],
        )


class FailingProvider:
    name = "failing"

    def next_action(self, question, trace, observations, tool_schemas):
        raise RuntimeError("provider unavailable")


class UnsupportedSummaryProvider:
    name = "unsupported-summary"

    def __init__(self, article):
        self.article = article
        self.calls = 0

    def next_action(self, question, trace, observations, tool_schemas):
        self.calls += 1
        if self.calls == 1:
            return AgentDecision(
                decision_summary="获取原文",
                tool="get_article",
                args={"law": self.article.law, "article_no": self.article.article_no},
            )
        return AgentDecision(
            decision_summary="生成结论",
            is_final=True,
            answer_summary="UNSUPPORTED CONCLUSION: pay 1,000,000 CNY.",
            citations=[
                Citation(
                    law=self.article.law,
                    article_no=self.article.article_no,
                    quote=self.article.text,
                )
            ],
        )


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retriever = Retriever.from_jsonl(FIXTURE)

    def test_mock_provider_completes_three_tool_flow(self) -> None:
        runner = AgentRunner(self.retriever, MockProvider())
        result = runner.run("测试劳动法第2条是什么？")
        self.assertEqual(result.answer.status, "ok")
        self.assertEqual(result.tool_calls, 3)
        self.assertTrue(result.answer.citations)
        self.assertEqual(result.answer.citations[0].article_no, "2")
        self.assertIn("经济补偿", result.answer.citations[0].quote)

    def test_citation_not_seen_this_run_is_rejected(self) -> None:
        runner = AgentRunner(self.retriever, UnsupportedCitationProvider())
        result = runner.run("测试引用守卫")
        self.assertEqual(result.answer.status, "no_evidence")
        self.assertEqual(result.answer.citations, [])
        self.assertTrue(any(event.reason == "no_verified_citation" for event in result.trace))

    def test_budget_exhaustion_degrades_safely(self) -> None:
        provider = AlwaysSearchProvider(["经济补偿 1", "经济补偿 2", "经济补偿 3"])
        runner = AgentRunner(
            self.retriever,
            provider,
            config=AgentConfig(max_tool_calls=2, max_steps=5),
        )
        result = runner.run("经济补偿")
        self.assertEqual(result.answer.status, "degraded")
        self.assertTrue(any(event.reason == "budget_exhausted" for event in result.trace))

    def test_duplicate_calls_are_rejected(self) -> None:
        provider = AlwaysSearchProvider(["经济补偿"])
        runner = AgentRunner(self.retriever, provider, config=AgentConfig(max_steps=5))
        result = runner.run("经济补偿")
        self.assertTrue(any(event.reason == "duplicate_call" for event in result.trace))
        self.assertEqual(result.answer.status, "degraded")

    def test_two_failed_searches_terminate_without_progress(self) -> None:
        provider = AlwaysSearchProvider(["zzzzzz", "qqqqqq"])
        runner = AgentRunner(self.retriever, provider, config=AgentConfig(max_steps=5))
        result = runner.run("不存在的问题")
        self.assertEqual(result.answer.status, "no_evidence")
        self.assertTrue(any(event.reason == "no_progress" for event in result.trace))

    def test_extractive_mode_does_not_pass_through_unsupported_summary(self) -> None:
        provider = UnsupportedSummaryProvider(self.retriever.articles[0])
        result = AgentRunner(self.retriever, provider).run("测试结论接地")
        self.assertEqual(result.answer.status, "ok")
        self.assertEqual(result.answer.answer_mode, "extractive")
        self.assertNotIn("UNSUPPORTED CONCLUSION", result.answer.summary)
        self.assertIn("UNSUPPORTED CONCLUSION", result.model_summary)
        self.assertFalse(result.answer.review_required)

    def test_advisory_mode_marks_model_summary_for_review(self) -> None:
        provider = UnsupportedSummaryProvider(self.retriever.articles[0])
        runner = AgentRunner(
            self.retriever,
            provider,
            config=AgentConfig(answer_mode="advisory"),
        )
        result = runner.run("测试结论接地")
        self.assertEqual(result.answer.status, "ok")
        self.assertEqual(result.answer.answer_mode, "advisory")
        self.assertIn("UNSUPPORTED CONCLUSION", result.answer.summary)
        self.assertTrue(result.answer.review_required)

    def test_provider_error_terminates_safely(self) -> None:
        result = AgentRunner(self.retriever, FailingProvider()).run("测试 provider 错误")
        self.assertEqual(result.answer.status, "no_evidence")
        self.assertIn("provider_error", {event.reason for event in result.trace})

    def test_max_steps_terminates(self) -> None:
        provider = AlwaysSearchProvider(["经济补偿"])
        runner = AgentRunner(
            self.retriever,
            provider,
            config=AgentConfig(max_steps=1, max_tool_calls=4),
        )
        result = runner.run("经济补偿")
        self.assertEqual(result.answer.status, "degraded")
        self.assertTrue(any(event.reason == "max_steps" for event in result.trace))


if __name__ == "__main__":
    unittest.main()
