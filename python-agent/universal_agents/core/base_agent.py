"""Abstract base class for all chat agents."""

from abc import ABC, abstractmethod
from uuid import uuid4

from .config import BaseConfig
from .history import ConversationHistory
from .types import AgentStats, ConversationTurn, Message


class BaseChatAgent(ABC):
    """Abstract base class all chat agents must implement."""

    def __init__(self, config: BaseConfig):
        self.config = config
        self.history = ConversationHistory(max_turns=config.max_history_turns)
        self.session_id: str = str(uuid4())

    @abstractmethod
    async def chat(self, message: str, **kwargs) -> str:
        """Send a message and return the assistant's response."""
        ...

    def get_history(self) -> list[Message]:
        return self.history.messages

    def get_turns(self) -> list[ConversationTurn]:
        return self.history.turns

    def clear_history(self) -> None:
        self.history.clear()

    def get_stats(self) -> AgentStats:
        successful = sum(1 for t in self.history.turns if t.success)
        failed = sum(1 for t in self.history.turns if not t.success)
        total_time = sum(t.processing_time_ms for t in self.history.turns)
        return AgentStats(
            session_id=self.session_id,
            provider=self.config.provider_name,
            total_turns=self.history.turn_count,
            successful_turns=successful,
            failed_turns=failed,
            total_processing_time_ms=total_time,
        )

    async def close(self) -> None:
        """Release resources. Override in subclasses."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()
