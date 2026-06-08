"""Exception hierarchy for Universal Agents."""


class AgentError(Exception):
    """Base exception for all agent errors."""


class BrowserError(AgentError):
    """Error during browser automation."""


class NavigationError(BrowserError):
    """Failed to navigate to target URL."""


class ElementNotFoundError(BrowserError):
    """Could not locate a required DOM element."""


class ResponseTimeoutError(BrowserError):
    """Response did not stabilize within the timeout."""


class AuthenticationError(BrowserError):
    """Browser session not authenticated (login required)."""


class CloudflareChallengeError(BrowserError):
    """Blocked by Cloudflare challenge page."""


class APIError(AgentError):
    """Error during HTTP API call."""


class RateLimitError(APIError):
    """API rate limit exceeded (HTTP 429)."""


class CLIError(AgentError):
    """Error during CLI subprocess execution."""
