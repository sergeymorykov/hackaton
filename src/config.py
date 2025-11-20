from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import os
import re

from dotenv import load_dotenv


ENV_PATHS = (Path(".env"), Path(".env.local"))

MAX_MARKDOWN_MESSAGE = 3800
CHUNK_BODY_LIMIT = 3400
MAX_MESSAGE_LENGTH = 4000
MIN_CODE_CHUNK_SIZE = 500

UPDATE_INTERVAL = 0.5

EXA_SEARCH_TIMEOUT = 10.0
EXA_MAX_RESULTS = 5
EXA_MAX_TEXT_LENGTH = 500


def load_env() -> None:
    for candidate in ENV_PATHS:
        if candidate.exists():
            load_dotenv(dotenv_path=candidate)
            break
    else:
        load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    api_key: str
    base_url: str
    model_name: str
    api_keys: Tuple[str, ...] = ()
    dialogue_db_path: Optional[str] = None
    temperature: float = 0.6
    max_completion_tokens: int = 1024

    @classmethod
    def from_env(cls) -> "Settings":
        load_env()
        bot_token = os.getenv("BOT_TOKEN")
        raw_keys = os.getenv("API_KEYS", "")
        api_keys: list[str] = []
        if raw_keys:
            for chunk in re.split(r"[,\n;]", raw_keys):
                trimmed = chunk.strip()
                if trimmed and trimmed not in api_keys:
                    api_keys.append(trimmed)

        api_key = os.getenv("API_KEY")
        if not api_key and api_keys:
            api_key = api_keys[0]
        base_url = os.getenv("BASE_URL", "https://api.mapleai.de/v1")
        model = os.getenv("MODEL_NAME", "gpt-4o")
        dialogue_db_path = os.getenv("DIALOGUE_DB_PATH", "data/dialogue.db")
        if not bot_token:
            raise RuntimeError("BOT_TOKEN is not set")
        if not api_key:
            raise RuntimeError("API_KEY is not set")
        if not api_keys:
            api_keys = [api_key]
        return cls(
            bot_token=bot_token,
            api_key=api_key,
            api_keys=tuple(api_keys),
            base_url=base_url,
            model_name=model,
            dialogue_db_path=dialogue_db_path,
        )

