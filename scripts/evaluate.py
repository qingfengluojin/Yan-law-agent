from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lawagent.agent import AgentRunner, run_baseline
from lawagent.llm import MockProvider, OpenAICompatibleProvider
from lawagent.retriever import Retriever, load_articles
from lawagent.schema import RunResult
from lawagent.trace import build_run_meta
from lawagent.verify import CitationVerifier, canonical_text


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
    with Path(path).open("r", encoding="utf-8-sig") as handle:
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


def _citation_metrics(
    citations,
    verifier: CitationVerifier,
    seen_ids: set[str],
) -> dict[str, int]:
    total = len(citations)
    existence = 0
    verbatim = 0
    unsupported = 0
    unique_keys: set[tuple[str, str, str]] = set()

    for citation in citations:
        article = verifier.retriever.get_article(
            citation.law,
            citation.article_no,
        )
        unique_key = (
            article.article_id if article is not None else citation.law,
            citation.article_no,
            canonical_text(citation.quote),
        )
        unique_keys.add(unique_key)
        if article is None:
            continue

        existence += 1
        if not verifier.verify(citation, allowed_article_ids=seen_ids).ok:
            unsupported += 1

        if verifier.verify(citation).ok:
            verbatim += 1

    return {
        "count": total,
        "unique": len(unique_keys),
        "existence": existence,
        "verbatim": verbatim,
        "unsupported": unsupported,
        "duplicates": total - len(unique_keys),
    }


def citation_metrics(
    result: RunResult,
    verifier: CitationVerifier,
    seen_ids: set[str],
) -> dict[str, dict[str, int]]:
    raw_citations = result.raw_citations or result.answer.citations
    return {
        "raw": _citation_metrics(raw_citations, verifier, seen_ids),
        "post_guard": _citation_metrics(result.answer.citations, verifier, seen_ids),
    }


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

        metrics = citation_metrics(result, verifier, seen_ids)

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
                "raw_citation_count": metrics["raw"]["count"],
                "raw_citation_unique": metrics["raw"]["unique"],
                "raw_citation_existence": metrics["raw"]["existence"],
                "raw_citation_verbatim": metrics["raw"]["verbatim"],
                "raw_unsupported_citations": metrics["raw"]["unsupported"],
                "post_guard_citation_count": metrics["post_guard"]["count"],
                "post_guard_citation_unique": metrics["post_guard"]["unique"],
                "post_guard_citation_existence": metrics["post_guard"]["existence"],
                "post_guard_citation_verbatim": metrics["post_guard"]["verbatim"],
                "post_guard_unsupported_citations": metrics["post_guard"]["unsupported"],
                "duplicate_final_citations": metrics["post_guard"]["duplicates"],
                "citation_ids": citation_ids,
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
        "raw_citation_count": sum(row["raw_citation_count"] for row in rows),
        "raw_citation_existence": sum(row["raw_citation_existence"] for row in rows),
        "raw_citation_verbatim": sum(row["raw_citation_verbatim"] for row in rows),
        "raw_unsupported": sum(row["raw_unsupported_citations"] for row in rows),
        "post_guard_citation_count": sum(row["post_guard_citation_count"] for row in rows),
        "post_guard_citation_unique": sum(row["post_guard_citation_unique"] for row in rows),
        "post_guard_citation_existence": sum(row["post_guard_citation_existence"] for row in rows),
        "post_guard_citation_verbatim": sum(row["post_guard_citation_verbatim"] for row in rows),
        "post_guard_unsupported": sum(row["post_guard_unsupported_citations"] for row in rows),
        "duplicate_final_citations": sum(row["duplicate_final_citations"] for row in rows),
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

    raw_existence_agent = ratio(agent["raw_citation_existence"], agent["raw_citation_count"])
    raw_existence_baseline = baseline_ratio("raw_citation_existence", "raw_citation_count")

    raw_verbatim_agent = ratio(agent["raw_citation_verbatim"], agent["raw_citation_count"])
    raw_verbatim_baseline = baseline_ratio("raw_citation_verbatim", "raw_citation_count")

    raw_unsupported_agent = str(agent["raw_unsupported"])
    raw_unsupported_baseline = str(baseline["raw_unsupported"]) if baseline else "N/A"

    post_existence_agent = ratio(
        agent["post_guard_citation_existence"], agent["post_guard_citation_count"]
    )
    post_existence_baseline = baseline_ratio(
        "post_guard_citation_existence", "post_guard_citation_count"
    )

    post_verbatim_agent = ratio(
        agent["post_guard_citation_verbatim"], agent["post_guard_citation_count"]
    )
    post_verbatim_baseline = baseline_ratio(
        "post_guard_citation_verbatim", "post_guard_citation_count"
    )

    post_unsupported_agent = str(agent["post_guard_unsupported"])
    post_unsupported_baseline = str(baseline["post_guard_unsupported"]) if baseline else "N/A"

    unique_agent = str(agent["post_guard_citation_unique"])
    unique_baseline = str(baseline["post_guard_citation_unique"]) if baseline else "N/A"

    duplicates_agent = str(agent["duplicate_final_citations"])
    duplicates_baseline = str(baseline["duplicate_final_citations"]) if baseline else "N/A"

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
        f"- 数据 SHA256：`{meta['data_sha256']}`",
        f"- Git commit：`{meta['git_commit']}`",
        f"- Git dirty：{meta['git_dirty']}",
        f"- provider：`{meta['provider']}`",
        f"- 模型：`{meta['model']}`",
        f"- Prompt version：`{meta['prompt_version']}`",
        f"- 输出模式：{meta.get('answer_mode', 'extractive')}",
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
        f"| Raw citation existence | {raw_existence_agent} | {raw_existence_baseline} |",
        f"| Raw verbatim match | {raw_verbatim_agent} | {raw_verbatim_baseline} |",
        f"| Raw unsupported citations | {raw_unsupported_agent} | {raw_unsupported_baseline} |",
        f"| Post-guard citation existence | {post_existence_agent} | {post_existence_baseline} |",
        f"| Post-guard verbatim match | {post_verbatim_agent} | {post_verbatim_baseline} |",
        "| Post-guard unsupported citations | "
        f"{post_unsupported_agent} | {post_unsupported_baseline} |",
        f"| Unique final citations | {unique_agent} | {unique_baseline} |",
        f"| Duplicate final citations | {duplicates_agent} | {duplicates_baseline} |",
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
            "| ID | 类型 | 状态 | 工具调用 | Gold | 原始无效 | 最终引用 | "
            "最终唯一数 | 最终无效 | 备注 |",
            "|---|---|---|---:|---:|---:|---|---:|---:|---|",
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
            f"{row['tool_calls']} | {gold} | {row['raw_unsupported_citations']} | "
            f"{citations} | {row['post_guard_citation_unique']} | "
            f"{row['post_guard_unsupported_citations']} | {note} |"
        )

    if baseline_rows:
        lines.extend(
            [
                "",
                "## Baseline 逐案结果",
                "",
                "| ID | 状态 | Gold | 最终引用 | 最终唯一数 | 最终无效 |",
                "|---|---|---:|---|---:|---:|",
            ]
        )
        for row in baseline_rows:
            gold = f"{row['gold_matched']}/{row['gold_total']}" if row["gold_total"] else "-"
            citations = ", ".join(row["citation_ids"]) or "-"
            lines.append(
                f"| {row['id']} | {row['status']} | {gold} | "
                f"{citations} | {row['post_guard_citation_unique']} | "
                f"{row['post_guard_unsupported_citations']} |"
            )

    lines.extend(
        [
            "",
            "## 评测局限",
            "",
            f"- 本报告仅覆盖 {agent['cases']} 条人工案例，不能外推总体准确率。",
            "- Gold hit 是工具检索覆盖指标，不是最终答案完整性指标。",
            "- MockProvider 是确定性流程测试，其无答案路由是固定演示规则，不代表真实模型能力。",
            "- baseline 是 retrieval-only，不是端到端 LLM baseline。",
            "- Raw 指标仍不覆盖在 JSON 解析阶段就被丢弃的非法 citation 结构。",
            "- 无答案安全率和失败恢复率必须结合真实 LLM 轨迹解释。",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    started_at = datetime.now(UTC)
    articles = load_articles(args.data)
    retriever = Retriever(articles)
    cases = load_cases(args.cases)

    provider = None
    if args.mode in {"agent", "both"}:
        provider = MockProvider() if args.provider == "mock" else OpenAICompatibleProvider()

    model_name = getattr(provider, "model", "mock") if provider else "N/A"
    run_meta = build_run_meta(
        provider=args.provider,
        model=model_name,
        prompt_version="evaluation-v1",
        data_path=args.data,
        started_at=started_at,
    )

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
        "prompt_version": run_meta.prompt_version,
        "cases": args.cases,
        "snapshot": ", ".join(sorted({article.verified_at.isoformat() for article in articles})),
        "provider": args.provider,
        "data_sha256": run_meta.data_sha256,
        "git_commit": run_meta.git_commit,
        "git_dirty": str(run_meta.git_dirty).lower(),
        "answer_mode": "extractive",
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
        print(f"agent raw_unsupported_citations: {summary['raw_unsupported']}")
        print(f"agent post_guard_unsupported_citations: {summary['post_guard_unsupported']}")


if __name__ == "__main__":
    main()
