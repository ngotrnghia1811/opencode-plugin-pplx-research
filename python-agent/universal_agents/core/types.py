"""Shared data types for all agents."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Message:
    """A single message in a conversation."""

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationTurn:
    """A complete user→assistant exchange."""

    turn_number: int
    user_message: Message
    assistant_message: Message
    thinking: Optional[str] = None
    processing_time_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    raw_api_responses: list[dict[str, Any]] = field(default_factory=list)
    thinking_source: Optional[str] = None


@dataclass
class TurnResult:
    """Testbed-compatible result for a single turn."""

    turn_number: int
    success: bool
    response: str
    thinking: Optional[str] = None
    thinking_source: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: float = 0.0
    validation: dict[str, Any] = field(default_factory=dict)
    raw_api_responses: list[dict[str, Any]] = field(default_factory=list)
    user_message: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_number": self.turn_number,
            "success": self.success,
            "response": self.response,
            "thinking": self.thinking,
            "thinking_source": self.thinking_source,
            "error": self.error,
            "processing_time_ms": self.processing_time_ms,
            "validation": self.validation,
            "raw_api_responses": self.raw_api_responses,
            "user_message": self.user_message,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentStats:
    """Runtime statistics for an agent session."""

    session_id: str
    provider: str
    total_turns: int = 0
    successful_turns: int = 0
    failed_turns: int = 0
    total_processing_time_ms: float = 0.0

    @property
    def avg_processing_time_ms(self) -> float:
        if self.total_turns == 0:
            return 0.0
        return self.total_processing_time_ms / self.total_turns

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "total_turns": self.total_turns,
            "successful_turns": self.successful_turns,
            "failed_turns": self.failed_turns,
            "total_processing_time_ms": self.total_processing_time_ms,
            "avg_processing_time_ms": self.avg_processing_time_ms,
        }
