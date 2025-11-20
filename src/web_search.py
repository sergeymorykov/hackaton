from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from .config import EXA_MAX_RESULTS, EXA_MAX_TEXT_LENGTH, EXA_SEARCH_TIMEOUT

if TYPE_CHECKING:
    pass


def needs_web_search(text: str) -> bool:
    text_lower = text.lower()
    search_keywords = [
        "погода",
        "погод",
        "температура",
        "новости",
        "новость",
        "курс",
        "курс валют",
        "цена",
        "стоимость",
        "сколько стоит",
        "что происходит",
        "последние",
        "сегодня",
        "сейчас",
        "актуальн",
        "актуальная",
        "тренд",
        "события",
        "событие",
        "календарь",
        "дата",
        "число",
        "какое число",
        "какая дата",
        "какой день",
        "какое сегодня число",
        "какая сегодня дата",
        "какой сегодня день",
        "год",
        "какой год",
        "какой сейчас год",
        "месяц",
        "какой месяц",
        "день недели",
        "какой день недели",
        "время",
        "который час",
        "сколько времени",
        "поищи в интернете",
        "поиск в интернете",
        "найди в интернете",
        "поискать в интернете",
        "поиск",
        "найди",
        "найти",
        "поищи",
        "в интернете",
        "в сети",
        "в гугле",
        "в яндексе",
    ]
    return any(keyword in text_lower for keyword in search_keywords)


async def search_web(query: str) -> str | None:
    try:
        exa_api_key = os.getenv("EXA_API_KEY")
        if not exa_api_key:
            logger.debug("EXA_API_KEY не установлен")
            return None

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": exa_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "num_results": EXA_MAX_RESULTS,
                    "contents": {
                        "text": {"max_characters": EXA_MAX_TEXT_LENGTH},
                    },
                },
                timeout=EXA_SEARCH_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if results:
                search_context = ""
                for idx, item in enumerate(results[:EXA_MAX_RESULTS], 1):
                    title = item.get("title", "")
                    url = item.get("url", "")
                    text_content = (
                        item.get("text", "")[:EXA_MAX_TEXT_LENGTH]
                        if item.get("text")
                        else ""
                    )
                    search_context += f"{idx}. {title}\nURL: {url}\n{text_content}\n\n"
                return search_context.strip()
    except httpx.HTTPError as exc:
        logger.debug("Ошибка HTTP при поиске через Exa: %s", exc)
    except Exception as exc:
        logger.debug("Ошибка поиска через Exa: %s", exc)
    return None


def build_search_query(text: str) -> str:
    text_lower = text.lower()
    if any(word in text_lower for word in ["число", "дата", "день", "год", "месяц", "календарь"]):
        if "сегодня" in text_lower or "сейчас" in text_lower:
            return f"какое сегодня число дата {datetime.now().strftime('%Y-%m-%d')}"
        return f"актуальная информация {text}"
    return text

