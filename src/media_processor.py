from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from telegram import Audio, PhotoSize, Voice


async def get_photo_base64(photo: list[PhotoSize] | None) -> str | None:
    if not photo:
        return None
    try:
        file = await photo[-1].get_file()
        photo_bytes = await file.download_as_bytearray()
        return base64.b64encode(photo_bytes).decode("utf-8")
    except Exception as exc:
        logger.warning("Не удалось получить фото: %s", exc)
        return None


async def get_audio_base64(audio: Audio | Voice | None) -> str | None:
    if not audio:
        return None
    try:
        file = await audio.get_file()
        audio_bytes = await file.download_as_bytearray()
        return base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as exc:
        logger.warning("Не удалось получить аудио: %s", exc)
        return None

