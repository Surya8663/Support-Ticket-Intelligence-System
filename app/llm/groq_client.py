from __future__ import annotations

import logging
import time

from groq import Groq

from app.config import Settings

logger = logging.getLogger(__name__)


class GroqNotConfiguredError(RuntimeError):
    """Raised when GROQ_API_KEY is missing."""


class GroqRequestError(RuntimeError):
    """Raised after retries are exhausted."""


class GroqClient:
    """Thin Groq wrapper: JSON mode, timeouts, and bounded retries."""

    def __init__(self, settings: Settings):
        if not settings.groq_api_key:
            raise GroqNotConfiguredError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add a free Groq key."
            )
        self.model = settings.groq_model
        self.max_retries = settings.groq_max_retries
        self._client = Groq(
            api_key=settings.groq_api_key,
            timeout=settings.groq_timeout_seconds,
        )

    def complete_json(self, system: str, user: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                content = response.choices[0].message.content or ""
                usage = getattr(response, "usage", None)
                logger.info(
                    "Groq call model=%s tokens=%s",
                    self.model,
                    getattr(usage, "total_tokens", None),
                )
                return content
            except GroqNotConfiguredError:
                raise
            except Exception as exc:  # noqa: BLE001 — normalize all provider failures
                last_error = exc
                logger.warning("Groq attempt %s failed: %s", attempt + 1, exc)
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
        raise GroqRequestError(f"Groq request failed after retries: {last_error}") from last_error
