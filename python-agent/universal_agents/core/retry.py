"""Retry decorator with exponential backoff."""

import asyncio
import functools
import logging
from typing import Type

from .exceptions import AgentError

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    base_delay: float = 2.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[Type[BaseException], ...] = (AgentError,),
):
    """Retry an async function with exponential backoff.

    Usage:
        @retry(max_attempts=3, base_delay=1.0)
        async def flaky_operation():
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        break
                    delay = base_delay * (backoff_factor ** (attempt - 1))
                    logger.warning(
                        "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                        attempt,
                        max_attempts,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator
