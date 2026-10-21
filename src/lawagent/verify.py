"""Citation existence and contiguous-quote verification."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from .retriever import Retriever
from .schema import Article, Citation

_ELLIPSIS_RE = re.compile(r"(?:…+|\.{3,}|。{3,})")
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")


def canonical_text(text: str) -> str:
    """Normalize only presentation noise; never paraphrase legal text."""

    value = unicodedata.normalize("NFKC", text)
    value = _ZERO_WIDTH_RE.sub("", value)
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", "", value)


def contains_ellipsis(text: str) -> bool:
    return bool(_ELLIPSIS_RE.search(text))


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    reason: str | None = None
    hint: str | None = None
    article: Article | None = None
    citation: Citation | None = None


class CitationVerifier:
    """The single source of truth for whether a citation may be shown."""

    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    def verify(
        self,
        citation: Citation,
        *,
        allowed_article_ids: Iterable[str] | None = None,
    ) -> VerificationResult:
        article = self.retriever.get_article(citation.law, citation.article_no)
        if article is None:
            return VerificationResult(
                ok=False,
                reason="article_not_found",
                hint="数据集中没有找到该法条，请先用检索或获取原文工具确认。",
            )

        if allowed_article_ids is not None and article.article_id not in set(allowed_article_ids):
            return VerificationResult(
                ok=False,
                reason="not_from_this_run",
                hint="引用必须来自本轮工具结果；请先检索或获取该条文原文。",
                article=article,
            )

        quote = citation.quote.strip()
        if not quote:
            return VerificationResult(
                ok=False,
                reason="empty_quote",
                hint="引用文本不能为空。",
                article=article,
            )
        if contains_ellipsis(quote):
            return VerificationResult(
                ok=False,
                reason="quote_contains_ellipsis",
                hint="引用必须是原文的连续片段，不能使用省略号或截断标记。",
                article=article,
            )
        if canonical_text(quote) not in canonical_text(article.text):
            return VerificationResult(
                ok=False,
                reason="quote_not_found",
                hint="引用不是原文的连续片段；请从工具返回的 text 中复制完整连续文本。",
                article=article,
            )

        canonical_citation = Citation(
            law=article.law,
            article_no=article.article_no,
            quote=quote,
            source_url=article.source_url,
            article_id=article.article_id,
        )
        return VerificationResult(
            ok=True,
            article=article,
            citation=canonical_citation,
        )

    def verify_all(
        self,
        citations: Iterable[Citation],
        *,
        allowed_article_ids: Iterable[str] | None = None,
    ) -> tuple[list[Citation], list[VerificationResult]]:
        verified: list[Citation] = []
        failures: list[VerificationResult] = []
        for citation in citations:
            result = self.verify(citation, allowed_article_ids=allowed_article_ids)
            if result.ok and result.citation is not None:
                verified.append(result.citation)
            else:
                failures.append(result)
        return verified, failures
