from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from lawagent.agent import AgentRunner, run_baseline
from lawagent.llm import MockProvider, OpenAICompatibleProvider
from lawagent.retriever import Retriever, load_articles
from lawagent.schema import RunResult
from lawagent.verify import CitationVerifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["agent", "baseline", "both"],
        default="both",
    )
    parser.add_argument(
        "--provider",
        choices=["mock", "openai"],
        default="mock",
    )
    parser.add_argument("--data", default="data/articles.jsonl")
    parser.add_argument("--cases", default="cases/cases.jsonl")
    parser.add_argument("--out", default="reports/report.md")
    parser.add_argument("--top-k", type=int, default=8)
    return parser.parse_args()


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def trace_ids(result: RunResult) -> set[str]:
    ids: set[str] = set()
    for event in result.trace:
        ids.update(event.top_ids)
    return ids


def failure_then_success(result: RunResult) -> bool:
    failed = False
    for event in result.trace:
        if event.ok is False:
            failed = True
        elif failed and event.ok is True:
            return True
    return False


def citation_metrics(
    result: RunResult,
    verifier: CitationVerifier,
    seen_ids: set[str],
) -> tuple[int, int, int, int]:
    total = len(result.answer.citations)
    existence = 0
    verbatim = 0
    unsupported = 0

    for citation in result.answer.citations:
        article = verifier.retriever.get_article(
            citation.law,
            citation.article_no,
        )
        if article is None:
            continue

        existence += 1
        if article.article_id not in seen_ids:
            unsupported += 1

        if verifier.verify(citation).ok:
            verbatim += 1

    return total, existence, verbatim, unsupported


def no_answer_is_safe(result: RunResult) -> bool:
    if result.answer.status in {"no_evidence", "degraded"}:
        return True

    if result.answer.status == "ok" and result.answer.missing_facts:
        cautious_markers = (
            "无法",
            "不能直接",
            "取决于",
            "需补充",
            "建议补充",
            "难以",
            "可能",
            "需要核实",
            "需核实",
        )
        return any(marker in result.answer.summary for marker in cautious_markers)

    return False


def evaluate_mode(
    mode: str,
    cases: list[dict[str, Any]],
    retriever: Retriever,
    provider,
    top_k: int,
) -> list[dict[str, Any]]:
    verifier = CitationVerifier(retriever)
    runner = AgentRunner(retriever, provider) if mode == "agent" else None
    rows: list[dict[str, Any]] = []

    for case in cases:
        if mode == "agent":
            result = runner.run(case["question"])
        else:
            result = run_baseline(case["question"], retriever, top_k=top_k)

        seen_ids = trace_ids(result)
        expected = set(case["gold_article_ids"])
        matched = len(expected & seen_ids)

        gold_case_hit = expected <= seen_ids if expected else None
        no_answer_safe = no_answer_is_safe(result) if case["type"] == "no_answer" else None
        recovery_case_hit = expected <= seen_ids if case["type"] == "recovery" else None

        total, existence, verbatim, unsupported = citation_metrics(
            result,
            verifier,
            seen_ids,
        )

        citation_ids: list[str] = []
        for citation in result.answer.citations:
            article = verifier.retriever.get_article(
                citation.law,
                citation.article_no,
            )
            citation_ids.append(
                article.article_id
                if article is not None
                else f"{citation.law}#{citation.article_no}"
            )

        rows.append(
            {
                "id": case["id"],
                "type": case["type"],
                "question": case["question"],
                "notes": case.get("notes", ""),
                "status": result.answer.status,
                "tool_calls": result.tool_calls,
                "gold_ids": sorted(expected),
                "gold_matched": matched,
                "gold_total": len(expected),
                "gold_case_hit": gold_case_hit,
                "citation_count": total,
                "citation_ids": citation_ids,
                "citation_existence": existence,
                "citation_verbatim": verbatim,
                "unsupported_citations": unsupported,
                "no_answer_safe": no_answer_safe,
                "recovery_case_hit": recovery_case_hit,
                "failure_then_success": failure_then_success(result),
            }
        )

    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    gold_rows = [row for row in rows if row["gold_total"] > 0]
    no_answer_rows = [row for row in rows if row["type"] == "no_answer"]
    recovery_rows = [row for row in rows if row["type"] == "recovery"]

    return {
        "cases": len(rows),
        "gold_cases": len(gold_rows),
        "gold_case_hit": sum(bool(row["gold_case_hit"]) for row in gold_rows),
        "gold_matched": sum(row["gold_matched"] for row in gold_rows),
        "gold_total": sum(row["gold_total"] for row in gold_rows),
        "citation_count": sum(row["citation_count"] for row in rows),
        "citation_existence": sum(row["citation_existence"] for row in rows),
        "citation_verbatim": sum(row["citation_verbatim"] for row in rows),
        "unsupported": sum(row["unsupported_citations"] for row in rows),
        "no_answer_total": len(no_answer_rows),
        "no_answer_safe": sum(bool(row["no_answer_safe"]) for row in no_answer_rows),
        "recovery_total": len(recovery_rows),
        "recovery_hit": sum(bool(row["recovery_case_hit"]) for row in recovery_rows),
        "failure_then_success": sum(row["failure_then_success"] for row in recovery_rows),
    }


def ratio(num: int, den: int) -> str:
    return f"{num}/{den}" if den else "N/A"


def render_report(
    agent_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    meta: dict[str, str],
) -> str:
    agent = summarize(agent_rows)
    baseline = summarize(baseline_rows) if baseline_rows else None

    def baseline_ratio(key: str, den_key: str) -> str:
        return ratio(baseline[key], baseline[den_key]) if baseline else "N/A"

    gold_case_hit_agent = ratio(agent["gold_case_hit"], agent["gold_cases"])
    gold_case_hit_baseline = baseline_ratio("gold_case_hit", "gold_cases")

    gold_recall_agent = ratio(agent["gold_matched"], agent["gold_total"])
    gold_recall_baseline = baseline_ratio("gold_matched", "gold_total")

    citation_existence_agent = ratio(agent["citation_existence"], agent["citation_count"])
    citation_existence_baseline = baseline_ratio("citation_existence", "citation_count")

    citation_verbatim_agent = ratio(agent["citation_verbatim"], agent["citation_count"])
    citation_verbatim_baseline = baseline_ratio("citation_verbatim", "citation_count")

    unsupported_agent = str(agent["unsupported"])
    unsupported_baseline = str(baseline["unsupported"]) if baseline else "N/A"

    no_answer_agent = ratio(agent["no_answer_safe"], agent["no_answer_total"])
    no_answer_baseline = baseline_ratio("no_answer_safe", "no_answer_total")

    recovery_agent = ratio(agent["recovery_hit"], agent["recovery_total"])
    recovery_baseline = baseline_ratio("recovery_hit", "recovery_total")

    failure_agent = ratio(agent["failure_then_success"], agent["recovery_total"])
    failure_baseline = baseline_ratio("failure_then_success", "recovery_total")

    lines = [
        "# 劳动法 Agent 评测报告",
        "",
        f"- 运行时间：{meta['timestamp']}",
        f"- 数据文件：`{meta['data']}`",
        f"- 案例文件：`{meta['cases']}`",
        f"- 数据快照：{meta['snapshot']}",
        f"- provider：`{meta['provider']}`",
        f"- 模型：`{meta['model']}`",
        f"- baseline top_k：{meta['top_k']}",
        "",
        "> Gold hit 以工具 observations 的 `top_ids` 为准，衡量检索覆盖，不等同于最终答案完整性。",
        "",
        "## 总览",
        "",
        "| 指标 | Agent | Baseline |",
        "|---|---:|---:|",
        f"| Gold case hit | {gold_case_hit_agent} | {gold_case_hit_baseline} |",
        f"| Gold article recall | {gold_recall_agent} | {gold_recall_baseline} |",
        f"| Citation existence | {citation_existence_agent} | {citation_existence_baseline} |",
        f"| Verbatim match | {citation_verbatim_agent} | {citation_verbatim_baseline} |",
        f"| Unsupported citations | {unsupported_agent} | {unsupported_baseline} |",
        f"| No-answer safe | {no_answer_agent} | {no_answer_baseline} |",
        f"| Recovery case hit | {recovery_agent} | {recovery_baseline} |",
        f"| Failure then success | {failure_agent} | {failure_baseline} |",
        "",
        "## Agent 分类结果",
        "",
        "| 类型 | 数量 | 命中 |",
        "|---|---:|---:|",
    ]

    for case_type in ("single_hop", "multi_hop", "no_answer", "recovery"):
        type_rows = [row for row in agent_rows if row["type"] == case_type]
        if not type_rows:
            continue
        if case_type == "no_answer":
            hit = sum(bool(row["no_answer_safe"]) for row in type_rows)
        else:
            hit = sum(bool(row["gold_case_hit"]) for row in type_rows)
        lines.append(f"| {case_type} | {len(type_rows)} | {hit}/{len(type_rows)} |")

    lines.extend(
        [
            "",
            "## Agent 逐案结果",
            "",
            "| ID | 类型 | 状态 | 工具调用 | Gold | 最终引用 | 无效引用 | 备注 |",
            "|---|---|---|---:|---:|---|---:|---|",
        ]
    )

    for row in agent_rows:
        gold = f"{row['gold_matched']}/{row['gold_total']}" if row["gold_total"] else "-"
        citations = ", ".join(row["citation_ids"]) or "-"
        if row["type"] == "no_answer":
            note = f"safe={row['no_answer_safe']}"
        elif row["type"] == "recovery":
            note = (
                f"recovery={row['recovery_case_hit']}; "
                f"failed_then_success={row['failure_then_success']}"
            )
        else:
            note = row["notes"]
        lines.append(
            f"| {row['id']} | {row['type']} | {row['status']} | "
            f"{row['tool_calls']} | {gold} | {citations} | "
            f"{row['unsupported_citations']} | {note} |"
        )

    if baseline_rows:
        lines.extend(
            [
                "",
                "## Baseline 逐案结果",
                "",
                "| ID | 状态 | Gold | 最终引用 | 无效引用 |",
                "|---|---|---:|---|---:|",
            ]
        )
        for row in baseline_rows:
            gold = f"{row['gold_matched']}/{row['gold_total']}" if row["gold_total"] else "-"
            citations = ", ".join(row["citation_ids"]) or "-"
            lines.append(
                f"| {row['id']} | {row['status']} | {gold} | "
                f"{citations} | {row['unsupported_citations']} |"
            )

    lines.extend(
        [
            "",
            "## 评测局限",
            "",
            "- 本报告仅覆盖 20 条人工案例，不能外推总体准确率。",
            "- Gold hit 是工具检索覆盖指标，不是最终答案完整性指标。",
            "- MockProvider 是确定性流程测试，不代表真实模型能力。",
            "- baseline 是 retrieval-only，不是端到端 LLM baseline。",
            "- 引用指标是 Output Guard 之后的结果，不能单独证明模型没有生成过错误引用。",
            "- 无答案安全率和失败恢复率必须结合真实 LLM 轨迹解释。",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    articles = load_articles(args.data)
    retriever = Retriever(articles)
    cases = load_cases(args.cases)

    provider = None
    if args.mode in {"agent", "both"}:
        provider = MockProvider() if args.provider == "mock" else OpenAICompatibleProvider()

    model_name = getattr(provider, "model", "mock") if provider else "N/A"

    agent_rows = (
        evaluate_mode("agent", cases, retriever, provider, args.top_k)
        if args.mode in {"agent", "both"}
        else []
    )
    baseline_rows = (
        evaluate_mode("baseline", cases, retriever, provider, args.top_k)
        if args.mode in {"baseline", "both"}
        else []
    )

    meta = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": args.data,
        "model": model_name,
        "cases": args.cases,
        "snapshot": ", ".join(sorted({article.verified_at.isoformat() for article in articles})),
        "provider": args.provider,
        "top_k": str(args.top_k),
    }

    report = render_report(agent_rows, baseline_rows, meta)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    print(f"wrote {out}")
    if agent_rows:
        summary = summarize(agent_rows)
        print(f"agent gold_case_hit: {summary['gold_case_hit']}/{summary['gold_cases']}")
        print(f"agent gold_article_recall: {summary['gold_matched']}/{summary['gold_total']}")
        print(f"agent unsupported_citations: {summary['unsupported']}")


if __name__ == "__main__":
    main()
