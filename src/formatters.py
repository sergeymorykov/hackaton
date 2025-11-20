from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from .config import MIN_CODE_CHUNK_SIZE

CODE_BLOCK_RE = re.compile(r"```(\w+)?\s*(.*?)```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`]+)`")

CODE_LANGUAGE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("html", re.compile(r"<!DOCTYPE html|<html\b|<body\b|</\w+>", re.IGNORECASE)),
    ("css", re.compile(r"\b[a-zA-Z0-9_\-\.#]+\s*\{[^}]+\}", re.MULTILINE)),
    (
        "javascript",
        re.compile(
            r"\b(function|const|let|var)\s+\w+\s*(?:=|\()" r"|\bconsole\.|document\.|=>",
            re.IGNORECASE,
        ),
    ),
    ("python", re.compile(r"\b(def|class)\s+\w+\s*\(|\bimport\s+\w+", re.IGNORECASE)),
    ("json", re.compile(r"^\s*\{[\s\S]*?:[\s\S]*?\}\s*$", re.MULTILINE)),
    ("bash", re.compile(r"^#!/bin/(?:bash|sh)|^\s*(?:cd|ls|mkdir|rm|echo)\b", re.MULTILINE)),
]


def detect_code_language(text: str) -> tuple[bool, str | None]:
    cleaned = text.strip()
    if len(cleaned) < 20:
        return False, None

    for language, pattern in CODE_LANGUAGE_PATTERNS:
        if pattern.search(cleaned):
            return True, language

    lines = [line for line in cleaned.splitlines() if line.strip()]
    if len(lines) < 3:
        return False, None

    code_like_lines = sum(
        1
        for line in lines
        if re.search(r"[<>{};=]|^\s*(?:if|for|while|class|def|return)\b", line)
    )
    if code_like_lines >= max(3, int(len(lines) * 0.5)):
        return True, None

    return False, None


def escape_markdown_v2(text: str) -> str:
    specials = r"_*[]()~`>#+-=|{}.!\\"
    return re.sub(rf"([{re.escape(specials)}])", r"\\\1", text)


def remove_markdown_stars(text: str) -> str:
    code_blocks: list[str] = []
    code_block_pattern = re.compile(r"```[\s\S]*?```")

    def replace_code_block(match: re.Match) -> str:
        code_blocks.append(match.group(0))
        return f"__PLACEHOLDER_CODE_{len(code_blocks) - 1}_UNIQUE__"

    text_no_code = code_block_pattern.sub(replace_code_block, text)

    text_no_code = re.sub(r"\*\*([^*]+)\*\*", r"\1", text_no_code)
    text_no_code = re.sub(r"\*([^*]+)\*", r"\1", text_no_code)
    text_no_code = re.sub(r"__([^_]+)__", r"\1", text_no_code)
    text_no_code = re.sub(r"_([^_]+)_", r"\1", text_no_code)

    for idx, code_block in enumerate(code_blocks):
        text_no_code = text_no_code.replace(f"__PLACEHOLDER_CODE_{idx}_UNIQUE__", code_block)

    return text_no_code


def format_message(text: str) -> str:
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(
        r"^\s*(HTML|JavaScript|CSS|Код|Markup|Java|JS|Пример):\s*$",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    detection_candidate = text.strip()

    placeholders: list[tuple[str, str]] = []

    def add_placeholder(content: str) -> str:
        token = f"__MD_SNIPPET_{len(placeholders)}__"
        placeholders.append((token, content))
        return token

    def block_replacer(match: re.Match) -> str:
        language = (match.group(1) or "").strip()
        code = match.group(2).strip("\n")
        if not code or code.strip() == "":
            return match.group(0)
        lang_prefix = f"{language}\n" if language else "\n"
        snippet = f"```{lang_prefix}{code}\n```"
        return add_placeholder(snippet)

    text_no_blocks = CODE_BLOCK_RE.sub(block_replacer, text)

    text_no_blocks = re.sub(r"__PLACEHOLDER_CODE_\d+_UNIQUE__", "", text_no_blocks)
    text_no_blocks = re.sub(r"_PLACEHOLDER[^_]*_", "", text_no_blocks)

    def inline_replacer(match: re.Match) -> str:
        content = match.group(1)
        if not content:
            return match.group(0)
        snippet = f"`{content}`"
        return add_placeholder(snippet)

    text_no_code = INLINE_CODE_RE.sub(inline_replacer, text_no_blocks)

    escaped_text = escape_markdown_v2(text_no_code)

    for token, snippet in placeholders:
        escaped_token = escape_markdown_v2(token)
        escaped_text = escaped_text.replace(escaped_token, snippet)

    if not placeholders:
        looks_like_code, language_hint = detect_code_language(detection_candidate)
        if looks_like_code:
            code_body = detection_candidate.strip("\n")
            if language_hint:
                return f"```{language_hint}\n{code_body}\n```"
            return f"```\n{code_body}\n```"

    return escaped_text


def format_html_fallback(text: str) -> str:
    clean = re.sub(r"```(\w+)?", "", text)
    clean = clean.replace("```", "")
    clean = re.sub(r"`", "", clean)
    return html.escape(clean).replace("\n", "<br/>")


def split_plain_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + limit)
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline + 1
        parts.append(text[start:end])
        start = end
    return [part.strip("\n") for part in parts if part.strip("\n")]


def split_formatted_text(text: str, limit: int) -> list[str]:
    text = text.strip("\n")
    if len(text) <= limit:
        return [text]

    if text.startswith("```"):
        newline_idx = text.find("\n")
        if newline_idx != -1:
            header = text[: newline_idx + 1]
            body = text[newline_idx + 1 :]
            if body.endswith("\n```"):
                body = body[:-4]
            elif body.endswith("```"):
                body = body[:-3]

            chunk_size = max(MIN_CODE_CHUNK_SIZE, limit - len(header) - 4)
            body_parts = split_plain_text(body, chunk_size)
            return [f"{header}{part.strip()}\n```" for part in body_parts]

    return split_plain_text(text, limit)

