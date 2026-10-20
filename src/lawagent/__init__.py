"""Law-agent: bounded legal-article retrieval with citation verification."""

from .agent import AgentConfig, AgentRunner, run_baseline
from .retriever import Retriever, load_articles
from .schema import DISCLAIMER, Article, Citation, FinalAnswer, RunResult
from .verify import CitationVerifier

__version__ = "0.1.0"

__all__ = [
    "AgentConfig",
    "AgentRunner",
    "Article",
    "Citation",
    "CitationVerifier",
    "DISCLAIMER",
    "FinalAnswer",
    "Retriever",
    "RunResult",
    "load_articles",
    "run_baseline",
]