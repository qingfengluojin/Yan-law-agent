"""The three tools exposed to the agent."""

from __future__ import annotations

from typing import Any

from .retriever import Retriever
from .schema import TOOL_NAMES, Citation, ToolResult
from .verify import CitationVerifier


def tool_schemas() -> list[dict[str, Any]]:
    """OpenAI-compatible function schemas for the three allowed tools."""

    return [
        {
            "type": "function",
            "function": {
                "name": "search_statutes",
                "description": (
                    "检索劳动法相关条文。输入自然语言问题或关键词，返回候选条文。"
                    "若没有结果，请改写查询词后重试，不要重复相同查询。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "自然语言问题或关键词"},
                        "top_k": {
                            "type": "integer",
                            "description": "返回条数，默认 8，范围 1-12",
                            "minimum": 1,
                            "maximum": 12,
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_article",
                "description": (
                    "根据法律名称和条号获取完整原文。适用于已经定位到具体条文、需要查看全文的场景。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "law": {
                            "type": "string",
                            "description": "法律名称，例如：中华人民共和国劳动合同法",
                        },
                        "article_no": {"type": "string", "description": "条号，例如：38"},
                    },
                    "required": ["law", "article_no"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "verify_citation",
                "description": "核验某条引用是否存在，并检查引用文本是否为原文的连续片段。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "law": {"type": "string"},
                        "article_no": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["law", "article_no", "quote"],
                    "additionalProperties": False,
                },
            },
        },
    ]


class ToolRegistry:
    """Validates arguments and executes one tool call."""

    def __init__(self, retriever: Retriever, verifier: CitationVerifier | None = None):
        self.retriever = retriever
        self.verifier = verifier or CitationVerifier(retriever)

    def schemas(self) -> list[dict[str, Any]]:
        return tool_schemas()

    def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        if name not in TOOL_NAMES:
            return _error(
                name,
                "unknown_tool",
                f"未知工具。可用工具：{', '.join(TOOL_NAMES)}。",
            )
        if not isinstance(args, dict):
            return _error(name, "invalid_args", "工具参数必须是 JSON 对象。")

        try:
            if name == "search_statutes":
                return self._search(args)
            if name == "get_article":
                return self._get_article(args)
            return self._verify_citation(args)
        except Exception as exc:  # defensive boundary: tools never crash the loop
            return _error(name, "tool_error", f"工具执行失败：{type(exc).__name__}: {exc}")

    def _search(self, args: dict[str, Any]) -> ToolResult:
        extra = set(args) - {"query", "top_k"}
        if extra:
            return _error("search_statutes", "invalid_args", f"不支持的参数：{sorted(extra)}。")
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            return _error("search_statutes", "invalid_args", "query 必须是非空字符串。")
        if len(query) > 500:
            return _error("search_statutes", "invalid_args", "query 过长，请控制在 500 字以内。")

        top_k = args.get("top_k", 8)
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 12:
            return _error("search_statutes", "invalid_args", "top_k 必须是 1-12 的整数。")

        articles = self.retriever.search(query.strip(), top_k=top_k)
        if not articles:
            return _error(
                "search_statutes",
                "no_results",
                "没有命中条文。请改用更短的法律术语，或换一个查询角度。不要重复相同查询。",
            )
        return ToolResult(
            ok=True,
            tool="search_statutes",
            data={"articles": [article.model_dump(mode="json") for article in articles]},
            top_ids=[article.article_id for article in articles],
        )

    def _get_article(self, args: dict[str, Any]) -> ToolResult:
        extra = set(args) - {"law", "article_no"}
        if extra:
            return _error("get_article", "invalid_args", f"不支持的参数：{sorted(extra)}。")
        law = args.get("law")
        article_no = args.get("article_no")
        if not isinstance(law, str) or not law.strip():
            return _error("get_article", "invalid_args", "law 必须是非空字符串。")
        if not isinstance(article_no, (str, int)) or not str(article_no).strip():
            return _error("get_article", "invalid_args", "article_no 必须是非空条号。")

        article = self.retriever.get_article(law.strip(), str(article_no).strip())
        if article is None:
            available = "、".join(self.retriever.known_laws) or "（数据集为空）"
            return _error(
                "get_article",
                "article_not_found",
                f"未找到该条文。当前数据集包含的法律：{available}。请核对法律名称和条号。",
            )
        return ToolResult(
            ok=True,
            tool="get_article",
            data={"article": article.model_dump(mode="json")},
            top_ids=[article.article_id],
        )

    def _verify_citation(self, args: dict[str, Any]) -> ToolResult:
        extra = set(args) - {"law", "article_no", "quote"}
        if extra:
            return _error("verify_citation", "invalid_args", f"不支持的参数：{sorted(extra)}。")
        law = args.get("law")
        article_no = args.get("article_no")
        quote = args.get("quote")
        if not isinstance(law, str) or not law.strip():
            return _error("verify_citation", "invalid_args", "law 必须是非空字符串。")
        if not isinstance(article_no, (str, int)) or not str(article_no).strip():
            return _error("verify_citation", "invalid_args", "article_no 必须是非空条号。")
        if not isinstance(quote, str) or not quote.strip():
            return _error("verify_citation", "invalid_args", "quote 必须是非空字符串。")

        citation = Citation(
            law=law.strip(),
            article_no=str(article_no).strip(),
            quote=quote,
        )
        result = self.verifier.verify(citation)
        if not result.ok or result.article is None:
            return _error(
                "verify_citation",
                result.reason or "verification_failed",
                result.hint or "引用核验失败。",
                top_ids=[result.article.article_id] if result.article else [],
            )
        return ToolResult(
            ok=True,
            tool="verify_citation",
            data={
                "verified": True,
                "article": result.article.model_dump(mode="json"),
            },
            top_ids=[result.article.article_id],
        )


def _error(
    tool: str,
    reason: str,
    hint: str,
    *,
    top_ids: list[str] | None = None,
) -> ToolResult:
    return ToolResult(
        ok=False,
        tool=tool,
        reason=reason,
        hint=hint,
        top_ids=top_ids or [],
    )
