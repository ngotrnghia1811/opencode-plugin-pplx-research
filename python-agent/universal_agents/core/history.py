"""Conversation history manager with max-turn truncation."""

from typing import Any, Optional

from .types import Message, ConversationTurn


class ConversationHistory:
    """Manages conversation messages and turns with a sliding window."""

    def __init__(self, max_turns: int = 50):
        self.max_turns = max_turns
        self._messages: list[Message] = []
        self._turns: list[ConversationTurn] = []
        self._total_turns: int = 0

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    @property
    def turns(self) -> list[ConversationTurn]:
        return list(self._turns)

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    def add_turn(
        self,
        user_message: Message,
        assistant_message: Message,
        thinking: str | None = None,
        processing_time_ms: float = 0.0,
        success: bool = True,
        error: str | None = None,
        raw_api_responses: Optional[list[dict[str, Any]]] = None,
        thinking_source: Optional[str] = None,
    ) -> ConversationTurn:
        """Record a complete user→assistant exchange."""
        self._total_turns += 1
        turn = ConversationTurn(
            turn_number=self._total_turns,
            user_message=user_message,
            assistant_message=assistant_message,
            thinking=thinking,
            processing_time_ms=processing_time_ms,
            success=success,
            error=error,
            raw_api_responses=raw_api_responses or [],
            thinking_source=thinking_source,
        )

        self._messages.append(user_message)
        self._messages.append(assistant_message)
        self._turns.append(turn)

        # Truncate oldest turns if over limit
        if len(self._turns) > self.max_turns:
            removed = self._turns.pop(0)
            # Remove the corresponding messages
            if removed.user_message in self._messages:
                self._messages.remove(removed.user_message)
            if removed.assistant_message in self._messages:
                self._messages.remove(removed.assistant_message)

        return turn

    def clear(self) -> None:
        """Clear all history."""
        self._messages.clear()
        self._turns.clear()

    def get_messages_for_context(self) -> list[dict[str, str]]:
        """Return messages formatted for API context (role + content dicts)."""
        return [{"role": m.role, "content": m.content} for m in self._messages]
