"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agent import AgentRunner, run_baseline
from .llm import MockProvider, OpenAICompatibleProvider
from .retriever import Retriever, load_articles
from .schema import RunResult
from .trace import render_trace, write_trace_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lawagent",
        description="劳动法条检索与引用核验 Agent（技术演示，不构成法律意见）。",
    )
    parser.add_argument("question", nargs="?", help="要检索的法律问题或条文查询")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--agent", action="store_true", help="多步检索 + 引用核验（默认）")
    mode.add_argument("--baseline", action="store_true", help="单次检索 baseline")
    parser.add_argument(
        "--provider",
        choices=["mock", "openai"],
        default="mock",
        help="LLM provider；默认 mock，可离线复现",
    )
    parser.add_argument("--model", help="OpenAI-compatible 模型名")
    parser.add_argument("--base-url", help="OpenAI-compatible base URL")
    parser.add_argument(
        "--data",
        default="data/articles.jsonl",
        help="法条 JSONL 路径（默认 data/articles.jsonl）",
    )
    parser.add_argument("--top-k", type=int, default=5, help="baseline 返回条数")
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出完整 JSON")
    parser.add_argument("--trace-out", help="将轨迹写入 JSONL 文件")
    parser.add_argument("--show-trace", action="store_true", help="在文本输出末尾显示轨迹")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.question or not args.question.strip():
        parser.error("必须提供 question，例如：lawagent --agent \"经济补偿按什么标准计算？\"")

    try:
        articles = load_articles(args.data)
    except (FileNotFoundError, ValueError) as exc:
        print(f"数据加载失败：{exc}", file=sys.stderr)
        return 2

    if not articles:
        print(
            "数据文件为空：请先按 data/SOURCES.md 的规则录入并核验法条。"
            "测试可使用 tests/fixtures/articles.jsonl。",
            file=sys.stderr,
        )
        return 2

    retriever = Retriever(articles)
    if args.baseline:
        result = run_baseline(args.question.strip(), retriever, top_k=args.top_k)
    else:
        if args.provider == "mock":
            provider = MockProvider()
        else:
            try:
                provider = OpenAICompatibleProvider(
                    model=args.model,
                    base_url=args.base_url,
                )
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        runner = AgentRunner(retriever, provider)
        result = runner.run(args.question.strip())

    if args.trace_out:
        write_trace_jsonl(result.trace, args.trace_out)

    if args.as_json:
        print(result.model_dump_json(indent=2))
    else:
        print(render_result(result))
        if args.show_trace:
            print("\n【轨迹】")
            print(render_trace(result.trace))

    return 0


def render_result(result: RunResult) -> str:
    mode_label = "Agent" if result.mode == "agent" else "Baseline"
    if result.mode == "baseline":
        status_label = (
            "单次检索结果"
            if result.answer.status == "ok"
            else "单次检索无结果"
        )
    else:
        status_label = {
            "ok": "通过核验",
            "degraded": "降级输出",
            "no_evidence": "无可核验依据",
        }.get(result.answer.status, result.answer.status)

    lines = [
        f"【模式】{mode_label}",
        f"【状态】{status_label}",
        f"【步数】{result.steps}  工具调用：{result.tool_calls}",
        "",
        "【结论】",
        result.answer.summary,
        "",
        "【引用】",
    ]
    if not result.answer.citations:
        lines.append("（无）")
    else:
        for index, citation in enumerate(result.answer.citations, start=1):
            lines.append(f"{index}. 《{citation.law}》第{citation.article_no}条")
            lines.append(f"   “{citation.quote}”")
            if citation.source_url:
                lines.append(f"   来源：{citation.source_url}")

    lines.extend(["", "【缺失事实】"])
    if result.answer.missing_facts:
        lines.extend(f"- {item}" for item in result.answer.missing_facts)
    else:
        lines.append("（无）")

    lines.extend(["", "【免责声明】", result.answer.disclaimer])
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())