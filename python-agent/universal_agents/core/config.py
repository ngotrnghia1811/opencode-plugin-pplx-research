"""Configuration dataclasses for all agent types."""

from dataclasses import dataclass, field, fields, asdict
import os
from typing import Any


@dataclass
class BaseConfig:
    """Base configuration shared by all agents."""

    provider_name: str = ""
    max_history_turns: int = 50
    max_retries: int = 3
    retry_delay: float = 2.0
    timeout: int = 180

    def to_dict(self) -> dict[str, Any]:
        """Serialize config to a plain dict (suitable for JSON)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseConfig":
        """Create a config instance from a dict, ignoring unknown keys."""
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class BrowserConfig(BaseConfig):
    """Configuration for browser-automated agents."""

    base_url: str = ""
    headless: bool = True
    storage_state: str = ""  # Path to Playwright storage state JSON
    viewport_width: int = 1920
    viewport_height: int = 1080
    response_check_interval: float = 2.0
    required_stable_checks: int = 3
    page_load_timeout: int = 30


@dataclass
class APIConfig(BaseConfig):
    """Configuration for HTTP API agents."""

    api_key: str = field(default="", repr=False)
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stream: bool = False
    system_prompt: str = "You are a helpful AI assistant."


@dataclass
class CLIConfig(BaseConfig):
    """Configuration for CLI subprocess agents."""

    command: str = ""
    working_dir: str = ""
