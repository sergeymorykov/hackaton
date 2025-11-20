from __future__ import annotations

import logging
from typing import AsyncIterator, List, Sequence

from openai import AsyncOpenAI, BadRequestError, RateLimitError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .config import Settings


CHAT_ROLES = {"user", "assistant", "system"}
logger = logging.getLogger(__name__)


class AIClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        keys = list(settings.api_keys or (settings.api_key,))
        self._api_keys: List[str] = keys or [settings.api_key]
        self._current_key_idx = 0
        self._client = self._build_client(self._api_keys[self._current_key_idx])

    def _build_client(self, api_key: str) -> AsyncOpenAI:
        return AsyncOpenAI(
            base_url=self._settings.base_url,
            api_key=api_key,
        )

    def _rotate_key(self) -> bool:
        if len(self._api_keys) <= 1:
            return False
        self._current_key_idx = (self._current_key_idx + 1) % len(self._api_keys)
        new_key = self._api_keys[self._current_key_idx]
        self._client = self._build_client(new_key)
        logger.warning(
            "Переключаюсь на следующий API ключ (index=%s)", self._current_key_idx
        )
        return True

    @staticmethod
    def _should_rotate_key(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        message = str(getattr(exc, "message", "")) or str(exc)
        if isinstance(exc, RateLimitError):
            return True
        if isinstance(exc, BadRequestError) and status in (400, 429):
            return "too many" in message.lower()
        if status in (400, 429):
            return "too many" in message.lower() or status == 429
        return False

    def _normalize_messages(self, messages: Sequence[dict]) -> List[dict]:
        normalized: List[dict] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role not in CHAT_ROLES:
                raise ValueError(f"Unsupported role: {role}")

            if isinstance(content, list):
                normalized.append({"role": role, "content": content})
            elif isinstance(content, dict) and "type" in content:
                normalized.append({"role": role, "content": [content]})
            else:
                normalized.append({"role": role, "content": str(content)})
        return normalized

    async def generate_reply(
        self,
        messages: Sequence[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload = self._normalize_messages(messages)
        temperature = temperature or self._settings.temperature
        max_tokens = max_tokens or self._settings.max_completion_tokens

        initial_key_idx = self._current_key_idx
        keys_rotated = 0

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_random_exponential(min=1, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                try:
                    completion = await self._client.chat.completions.create(
                        model=self._settings.model_name,
                        messages=payload,
                        temperature=temperature,
                        max_completion_tokens=max_tokens,
                    )
                    message = completion.choices[0].message
                    return message.content or ""
                except Exception as exc:
                    if self._should_rotate_key(exc):
                        logger.debug(
                            "Ошибка rate limit. Текущий ключ: %s, переключений: %s/%s, начальный: %s",
                            self._current_key_idx,
                            keys_rotated,
                            len(self._api_keys),
                            initial_key_idx,
                        )
                        if keys_rotated < len(self._api_keys):
                            if self._rotate_key():
                                keys_rotated += 1
                                logger.info("Ключ переключён после ошибки: %s", exc)
                                if self._current_key_idx == initial_key_idx and keys_rotated > 0:
                                    logger.warning(
                                        "Прошёл полный круг по всем ключам (%s), но ошибка сохраняется",
                                        len(self._api_keys),
                                    )
                                    keys_rotated = len(self._api_keys)
                        else:
                            logger.warning(
                                "Все ключи перебраны (%s), но ошибка сохраняется: %s",
                                len(self._api_keys),
                                exc,
                            )
                    raise
        return ""

    async def generate_reply_stream(
        self,
        messages: Sequence[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        payload = self._normalize_messages(messages)
        temperature = temperature or self._settings.temperature
        max_tokens = max_tokens or self._settings.max_completion_tokens

        initial_key_idx = self._current_key_idx
        keys_rotated = 0

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_random_exponential(min=1, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                try:
                    stream = await self._client.chat.completions.create(
                        model=self._settings.model_name,
                        messages=payload,
                        temperature=temperature,
                        max_completion_tokens=max_tokens,
                        stream=True,
                    )
                    async for chunk in stream:
                        if chunk.choices and len(chunk.choices) > 0:
                            delta = chunk.choices[0].delta
                            if delta and hasattr(delta, 'content') and delta.content:
                                content = delta.content
                                if content:
                                    yield content
                    return
                except Exception as exc:
                    if self._should_rotate_key(exc):
                        logger.debug(
                            "Ошибка rate limit. Текущий ключ: %s, переключений: %s/%s, начальный: %s",
                            self._current_key_idx,
                            keys_rotated,
                            len(self._api_keys),
                            initial_key_idx,
                        )
                        if keys_rotated < len(self._api_keys):
                            if self._rotate_key():
                                keys_rotated += 1
                                logger.info("Ключ переключён после ошибки: %s", exc)
                                if self._current_key_idx == initial_key_idx and keys_rotated > 0:
                                    logger.warning(
                                        "Прошёл полный круг по всем ключам (%s), но ошибка сохраняется",
                                        len(self._api_keys),
                                    )
                                    keys_rotated = len(self._api_keys)
                        else:
                            logger.warning(
                                "Все ключи перебраны (%s), но ошибка сохраняется: %s",
                                len(self._api_keys),
                                exc,
                            )
                    raise

