"""Provider selector registry — CSS selectors per provider's web UI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSelectors:
    """CSS/XPath selectors for interacting with a provider's web UI."""

    # Ordered by priority — first match wins
    input: list[str]
    submit: list[str]
    response: list[str]
    loading: list[str] = ()  # type: ignore[assignment]
    new_chat: list[str] = ()  # type: ignore[assignment]

    def __post_init__(self):
        # Convert tuples from defaults to lists
        if isinstance(self.loading, tuple):
            object.__setattr__(self, "loading", list(self.loading))
        if isinstance(self.new_chat, tuple):
            object.__setattr__(self, "new_chat", list(self.new_chat))
