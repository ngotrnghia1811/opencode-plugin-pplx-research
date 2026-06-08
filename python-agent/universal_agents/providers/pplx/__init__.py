"""Perplexity provider."""

from .chat import Citation  # dataclass — no playwright dependency
# PerplexityChatAgent imported lazily — depends on playwright, unused by research agent
from .config import PerplexityConfig, PerplexityResearchConfig
from .research import PerplexityResearchAgent, ResearchReport

__all__ = [
    "Citation",
    "PerplexityConfig",
    "PerplexityResearchConfig",
    "PerplexityResearchAgent",
    "ResearchReport",
]
