from __future__ import annotations

import re
from typing import Iterable


STOP_WORDS = {
    "дурак",
    "идиот",
    "черт",
    "тупой",
    "тварь",
    "придурок",
    "псих",
    "урод",
    "хрен",
    "чмо",
    "лох",
}


def contains_stop_words(text: str, stop_words: Iterable[str] | None = None) -> bool:
    words = stop_words or STOP_WORDS
    lowered = text.lower()
    return any(word in lowered for word in words)


def contains_url(text: str) -> bool:
    return bool(re.search(r"https?://", text))

