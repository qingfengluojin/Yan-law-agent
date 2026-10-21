"""Small-corpus BM25 retrieval with legal-term expansion and article routing."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

from .schema import Article

_CJK_SEQ_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[a-zA-Z]+|\d+(?:\.\d+)?")
_ARTICLE_NO_RE = re.compile(r"第\s*(\d+)\s*条")
_BARE_ARTICLE_NO_RE = re.compile(r"(?<!第)(\d+)\s*条")
_CN_ARTICLE_NO_RE = re.compile(r"第\s*([零一二两三四五六七八九十百千]+)\s*条")

_CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

_CN_UNITS = {
    "十": 10,
    "百": 100,
    "千": 1000,
}

_STOPWORDS = {
    "的",
    "了",
    "吗",
    "呢",
    "是",
    "在",
    "和",
    "与",
    "或",
    "及",
    "对",
    "为",
    "有",
    "无",
    "可",
    "能",
    "会",
    "要",
    "请",
    "我",
    "你",
    "他",
    "她",
    "它",
    "这",
    "那",
    "哪",
    "什么",
    "怎么",
    "如何",
    "哪些",
}

# Query-side synonym expansion only. Do not rewrite statutory text in the corpus.
_LEGAL_SYNONYMS = {
    "社保": "社会保险",
    "未缴": "未依法缴纳",
    "不交": "未依法缴纳",
    "补偿": "经济补偿",
    "加班": "延长工作时间",
    "辞退": "解除劳动合同",
    "开除": "解除劳动合同",
    "试用": "试用期",
    "工伤": "工伤保险",
    "公司": "用人单位",
    "单位": "用人单位",
    "工资": "劳动报酬",
}

# Canonical names used by the official corpus, mapped from common short names.
_LAW_ALIASES = {
    "劳动合同法": "中华人民共和国劳动合同法",
    "劳动法": "中华人民共和国劳动法",
    "社会保险法": "中华人民共和国社会保险法",
    "劳动争议调解仲裁法": "中华人民共和国劳动争议调解仲裁法",
    "工伤保险条例": "工伤保险条例",
}


def normalize_law_name(name: str) -> str:
    """Normalize a law name for matching while preserving its legal core."""

    value = unicodedata.normalize("NFKC", name).strip()
    value = value.strip("《》").replace(" ", "").replace("\u3000", "")
    if value.startswith("中华人民共和国"):
        value = value[len("中华人民共和国") :]
    return value


def extract_article_no(query: str) -> str | None:
    match = _ARTICLE_NO_RE.search(query)
    if match:
        return match.group(1)

    match = _CN_ARTICLE_NO_RE.search(query)
    if match:
        value = chinese_number_to_int(match.group(1))
        return str(value) if value is not None else None

    match = _BARE_ARTICLE_NO_RE.search(query)
    return match.group(1) if match else None


def resolve_law_name(name_or_query: str, known_laws: Iterable[str]) -> str | None:
    """Resolve a full/short law name, or find a law name inside a natural query."""

    known = list(known_laws)
    normalized_known = {normalize_law_name(law): law for law in known}
    text = unicodedata.normalize("NFKC", name_or_query).strip()
    direct = normalize_law_name(text)
    if direct in normalized_known:
        return normalized_known[direct]

    for alias, canonical in _LAW_ALIASES.items():
        if alias in text:
            target = normalize_law_name(canonical)
            if target in normalized_known:
                return normalized_known[target]

    # Longest match first so "劳动合同法" is not swallowed by "劳动法".
    for law in sorted(known, key=lambda item: len(normalize_law_name(item)), reverse=True):
        if normalize_law_name(law) in normalize_law_name(text):
            return law
    return None


def expand_legal_terms(text: str) -> str:
    additions = [
        canonical
        for alias, canonical in _LEGAL_SYNONYMS.items()
        if alias in text and canonical not in text
    ]
    return text if not additions else f"{text} {' '.join(additions)}"


def tokenize(text: str, *, expand: bool = False) -> list[str]:
    """Character unigram + bigram tokenizer for Chinese, plus ASCII words."""

    value = unicodedata.normalize("NFKC", text).lower()
    if expand:
        value = expand_legal_terms(value)

    tokens: list[str] = []
    for sequence in _CJK_SEQ_RE.findall(value):
        if len(sequence) == 1:
            if sequence not in _STOPWORDS:
                tokens.append(sequence)
            continue
        tokens.extend(char for char in sequence if char not in _STOPWORDS)
        tokens.extend(sequence[i : i + 2] for i in range(len(sequence) - 1))
    tokens.extend(_WORD_RE.findall(value))
    return tokens


def chinese_number_to_int(text: str) -> int | None:
    if not text:
        return None

    section = 0
    number = 0

    for char in text:
        if char in _CN_DIGITS:
            number = _CN_DIGITS[char]
        elif char in _CN_UNITS:
            unit = _CN_UNITS[char]
            if number == 0:
                number = 1
            section += number * unit
            number = 0
        else:
            return None

    return section + number


class BM25Index:
    """A compact BM25 implementation; no compiled dependency is required."""

    def __init__(self, documents: Sequence[Sequence[str]], *, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.term_freqs = [Counter(doc) for doc in documents]
        self.doc_lengths = [len(doc) for doc in documents]
        self.avgdl = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        document_frequency: Counter[str] = Counter()
        for freqs in self.term_freqs:
            document_frequency.update(freqs.keys())
        count = len(documents)
        self.idf = {
            term: math.log(1 + (count - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }

    def scores(self, query_tokens: Sequence[str]) -> list[float]:
        result = [0.0] * len(self.term_freqs)
        if not self.term_freqs or self.avgdl == 0:
            return result
        for term in set(query_tokens):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for index, freqs in enumerate(self.term_freqs):
                freq = freqs.get(term, 0)
                if not freq:
                    continue
                denominator = freq + self.k1 * (
                    1 - self.b + self.b * self.doc_lengths[index] / self.avgdl
                )
                result[index] += idf * freq * (self.k1 + 1) / denominator
        return result


class Retriever:
    """In-memory retriever for the deliberately small verified corpus."""

    def __init__(self, articles: Sequence[Article]):
        self.articles = list(articles)
        self.by_id = {article.article_id: article for article in self.articles}
        self.by_article_no: dict[str, list[Article]] = defaultdict(list)
        for article in self.articles:
            self.by_article_no[article.article_no].append(article)
        self.known_laws = sorted({article.law for article in self.articles})
        self.index = BM25Index([tokenize(article.text) for article in self.articles])

    @classmethod
    def from_jsonl(cls, path: str | Path) -> Retriever:
        return cls(load_articles(path))

    def resolve_law_name(self, name_or_query: str) -> str | None:
        return resolve_law_name(name_or_query, self.known_laws)

    def get_article(self, law: str, article_no: str) -> Article | None:
        article_no = _normalize_article_no(article_no)
        resolved_law = self.resolve_law_name(law)
        if resolved_law is not None:
            article = self.by_id.get(f"{resolved_law}#{article_no}")
            if article is not None:
                return article

        # If the law name is abbreviated beyond recognition, allow a unique
        # article-number match. Ambiguous matches are intentionally rejected.
        candidates = self.by_article_no.get(article_no, [])
        if len(candidates) == 1:
            return candidates[0]
        return None

    def search(self, query: str, top_k: int = 8) -> list[Article]:
        if not self.articles or top_k <= 0:
            return []

        query_text = unicodedata.normalize("NFKC", query).strip()
        article_no = extract_article_no(query_text)
        law_name = self.resolve_law_name(query_text)

        routed: list[Article] = []
        if article_no is not None:
            routed = [
                article
                for article in self.by_article_no.get(article_no, [])
                if law_name is None or article.law == law_name
            ]

        query_tokens = tokenize(query_text, expand=True)
        scores = self.index.scores(query_tokens)

        ordered: list[Article] = []
        seen: set[str] = set()
        for article in routed:
            if article.article_id not in seen:
                ordered.append(article)
                seen.add(article.article_id)

        ranked_indices = sorted(range(len(self.articles)), key=lambda i: scores[i], reverse=True)
        for index in ranked_indices:
            article = self.articles[index]
            if article.article_id in seen:
                continue
            if scores[index] <= 0:
                continue
            ordered.append(article)
            seen.add(article.article_id)
            if len(ordered) >= top_k:
                break

        return ordered[:top_k]


def _normalize_article_no(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip()

    match = _ARTICLE_NO_RE.search(text)
    if match:
        return match.group(1)

    match = _CN_ARTICLE_NO_RE.search(text)
    if match:
        number = chinese_number_to_int(match.group(1))
        if number is not None:
            return str(number)

    match = _BARE_ARTICLE_NO_RE.search(text)
    if match:
        return match.group(1)

    digits = re.search(r"(\d+)", text)
    return digits.group(1) if digits else text


def load_articles(path: str | Path) -> list[Article]:
    """Load and validate a JSONL corpus. Blank lines are ignored."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"articles file not found: {source}")

    articles: list[Article] = []
    seen: set[str] = set()
    with source.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip().lstrip("\ufeff")
            if not line:
                continue
            try:
                article = Article.model_validate_json(line)
            except Exception as exc:  # pydantic errors are re-raised with context
                raise ValueError(f"invalid article at {source}:{line_number}: {exc}") from exc
            if article.article_id in seen:
                raise ValueError(
                    f"duplicate article id at {source}:{line_number}: {article.article_id}"
                )
            seen.add(article.article_id)
            articles.append(article)
    return articles
