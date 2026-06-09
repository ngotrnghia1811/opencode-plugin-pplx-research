"""Perplexity-specific configuration."""

import os
from dataclasses import dataclass, field

from ...core.config import BrowserConfig


@dataclass
class PerplexityConfig(BrowserConfig):
    """Configuration for Perplexity browser agents."""

    provider_name: str = "perplexity"
    base_url: str = "https://www.perplexity.ai"
    storage_state: str = field(
        default_factory=lambda: os.getenv("PPLX_STORAGE_STATE", "")
    )
    extract_citations: bool = True


@dataclass
class PerplexityResearchConfig(PerplexityConfig):
    """Configuration for the Perplexity deep research agent.

    research_mode:
        "deep"     — always attempt Deep Research mode, raise if unavailable
        "standard" — use normal Perplexity search (no Deep Research toggle)
        "auto"     — try Deep Research first, fall back to standard search
    """

    research_mode: str = "auto"
    output_dir: str = "reports/"
    max_research_wait: int = 300  # seconds (Deep Research can take 3-5 min)
    download_full_artifacts: bool = True  # Download .zip with all documents vs clipboard-only
