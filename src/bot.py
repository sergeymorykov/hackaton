from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from loguru import logger
from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter, TimedOut
from telegram.ext import (
    AIORateLimiter,
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .ai_client import AIClient
from .config import (
    CHUNK_BODY_LIMIT,
    MAX_MESSAGE_LENGTH,
    MIN_CODE_CHUNK_SIZE,
    Settings,
    UPDATE_INTERVAL,
)
from .filters import contains_stop_words
from .formatters import (
    CODE_BLOCK_RE,
    format_message,
    remove_markdown_stars,
    split_formatted_text,
)
from .handlers import (
    build_menu,
    get_bot_info_text,
    handle_about,
    handle_help,
    handle_menu_button,
    handle_reset,
    handle_start,
    is_conference_question,
    load_conference_info,
    SYSTEM_PROMPT,
)
from .media_processor import get_audio_base64, get_photo_base64
from .state import ContextStore
from .storage import DialogueStorage
from .web_search import build_search_query, needs_web_search, search_web


class TelegramAIAgent:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ai_client = AIClient(settings)
        db_path = Path(settings.dialogue_db_path or "data/dialogue.db")
        self._storage = DialogueStorage(db_path)
        self._context_store = ContextStore(storage=self._storage)
        self._bot_info: dict | None = None

    async def build_application(self) -> Application:
        application = (
            Application.builder()
            .token(self._settings.bot_token)
            .rate_limiter(AIORateLimiter())
            .post_init(self._post_init)
            .build()
        )
        application.add_handler(CommandHandler("start", self.on_start))
        application.add_handler(CommandHandler("help", self.on_help))
        application.add_handler(CommandHandler("about", self.on_about))
        application.add_handler(CommandHandler("reset", self.on_reset))
        application.add_handler(CallbackQueryHandler(self.on_menu_button))
        application.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.AUDIO | filters.VOICE | filters.VIDEO_NOTE)
                & (~filters.COMMAND),
                self.on_message,
            )
        )

        commands = [
            BotCommand("start", "Запустить бота и показать меню"),
            BotCommand("help", "Показать справку"),
            BotCommand("about", "Информация о модели"),
            BotCommand("reset", "Очистить контекст диалога"),
        ]
        await application.bot.set_my_commands(commands)

        return application

    async def _post_init(self, application: Application) -> None:
        bot_me = await application.bot.get_me()
        self._bot_info = {
            "id": bot_me.id,
            "username": bot_me.username,
            "first_name": bot_me.first_name,
            "is_bot": bot_me.is_bot,
        }
        logger.info("Bot initialized as @{username}", username=bot_me.username)

    async def _ensure_bot_info(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._bot_info and context.bot:
            try:
                bot_me = await context.bot.get_me()
                self._bot_info = {
                    "id": bot_me.id,
                    "username": bot_me.username,
                    "first_name": bot_me.first_name,
                    "is_bot": bot_me.is_bot,
                }
            except (BadRequest, RetryAfter, TimedOut) as exc:
                logger.warning("Не удалось получить информацию о боте: %s", exc)

    async def on_menu_button(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await handle_menu_button(update, context, self._context_store, self._bot_info)

    async def on_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._ensure_bot_info(context)
        await handle_start(update, context, self._context_store, self._bot_info)

    async def on_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await handle_help(update, context)

    async def on_about(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await handle_about(update, context)

    async def on_reset(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await handle_reset(update, context, self._context_store)

    async def _process_media_content(self, message) -> list[dict]:
        content_parts = []
        text = message.text or message.caption or ""

        if text:
            content_parts.append({"type": "text", "text": text})

        if message.photo:
            photo_b64 = await get_photo_base64(message.photo)
            if photo_b64:
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{photo_b64}"},
                    }
                )

        if message.audio:
            audio_b64 = await get_audio_base64(message.audio)
            if audio_b64:
                mime_type = message.audio.mime_type or "audio/mpeg"
                content_parts.append(
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_b64, "format": mime_type},
                    }
                )

        if message.voice:
            audio_b64 = await get_audio_base64(message.voice)
            if audio_b64:
                content_parts.append(
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_b64, "format": "audio/ogg"},
                    }
                )

        return content_parts

    def _build_system_messages(self) -> list[dict]:
        system_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        bot_info_text = get_bot_info_text(self._bot_info)
        if bot_info_text:
            system_messages.append({"role": "system", "content": bot_info_text})

        return system_messages

    async def _add_conference_context(
        self, text: str, history: list[dict]
    ) -> None:
        if text and is_conference_question(text):
            conference_info = load_conference_info()
            if conference_info:
                history.append(
                    {
                        "role": "system",
                        "content": f"Полная информация о конференции ТАТАР САН 2025:\n\n{conference_info}",
                    }
                )
                logger.debug("Добавлена информация о конференции в контекст")

    async def _add_web_search_context(
        self, text: str, history: list[dict]
    ) -> None:
        if text and needs_web_search(text):
            logger.debug("Определена необходимость веб-поиска для текста: %s", text[:100])
            try:
                search_query = build_search_query(text)
                search_result = await search_web(search_query)
                if search_result:
                    history.append(
                        {
                            "role": "system",
                            "content": (
                                f"Результаты поиска в интернете:\n\n{search_result}\n\n"
                                "Используй эту информацию для ответа на вопрос пользователя. "
                                "Если в результатах поиска есть актуальная дата, число или год, "
                                "обязательно используй эту информацию."
                            ),
                        }
                    )
                    logger.info(
                        "Добавлены результаты поиска в контекст (длина: %d символов)",
                        len(search_result),
                    )
                else:
                    logger.warning(
                        "Поиск выполнен, но результат пустой для запроса: %s", text[:100]
                    )
            except Exception as exc:
                logger.warning("Не удалось выполнить поиск через Exa: %s", exc)

    async def _send_code_blocks(
        self, accumulated_text: str, message, sent_code_blocks: set
    ) -> None:
        for match in CODE_BLOCK_RE.finditer(accumulated_text):
            code_block_full = match.group(0)
            if code_block_full not in sent_code_blocks:
                sent_code_blocks.add(code_block_full)
                language = (match.group(1) or "").strip()
                code = match.group(2).strip("\n")
                if code:
                    lang_prefix = f"{language}\n" if language else ""
                    code_message = f"```{lang_prefix}{code}\n```"
                    try:
                        await message.reply_text(
                            code_message, parse_mode=ParseMode.MARKDOWN_V2
                        )
                    except BadRequest:
                        try:
                            await message.reply_text(code_message, parse_mode=None)
                        except (BadRequest, RetryAfter, TimedOut):
                            pass

    async def _update_status_message(
        self,
        status_message,
        accumulated_text: str,
        last_update_time: float,
        chunk_count: int,
    ) -> tuple[bool, float]:
        current_time = time.time()
        should_update = chunk_count == 1 or (
            current_time - last_update_time >= UPDATE_INTERVAL
            and accumulated_text.strip()
        )

        if should_update:
            text_without_code = accumulated_text
            for match in CODE_BLOCK_RE.finditer(accumulated_text):
                text_without_code = text_without_code.replace(match.group(0), "")

            safe_text = remove_markdown_stars(text_without_code)
            if safe_text.strip():
                formatted_text = format_message(safe_text)
                if not formatted_text.strip() or formatted_text.strip() == "-":
                    return False, last_update_time
                try:
                    await self._safe_edit(
                        status_message, formatted_text, parse_mode=ParseMode.MARKDOWN_V2
                    )
                    return False, current_time
                except RetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                    return True, current_time
                except TimedOut:
                    return True, current_time
                except BadRequest:
                    try:
                        await self._safe_edit(
                            status_message,
                            safe_text[:MAX_MESSAGE_LENGTH],
                            parse_mode=None,
                        )
                        return False, current_time
                    except (BadRequest, RetryAfter, TimedOut):
                        return True, current_time

        return False, last_update_time

    async def on_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.effective_message
        user = update.effective_user
        if not message or not user:
            return

        text = message.text or message.caption or ""
        if text and contains_stop_words(text):
            await message.reply_text("Пожалуйста, без нецензурных слов 🙏")
            return

        content_parts = await self._process_media_content(message)
        if not content_parts:
            return

        if len(content_parts) == 1 and content_parts[0].get("type") == "text":
            user_content = content_parts[0]["text"]
        elif len(content_parts) > 1:
            user_content = content_parts
        else:
            user_content = content_parts[0]

        self._context_store.append(user.id, "user", user_content)

        await self._ensure_bot_info(context)

        history = self._build_system_messages()

        await self._add_conference_context(text, history)
        await self._add_web_search_context(text, history)

        history.extend(self._context_store.get(user.id).export())

        status_message = await message.reply_text("🤖 Думаю над ответом...")

        try:
            accumulated_text = ""
            last_update_time = 0.0
            chunk_count = 0
            pending_update = False
            sent_code_blocks: set[str] = set()

            async for chunk in self._ai_client.generate_reply_stream(history):
                if not chunk:
                    continue

                accumulated_text += chunk
                chunk_count += 1

                await self._send_code_blocks(accumulated_text, message, sent_code_blocks)

                pending_update, last_update_time = await self._update_status_message(
                    status_message, accumulated_text, last_update_time, chunk_count
                )

            text_without_code = accumulated_text
            for match in CODE_BLOCK_RE.finditer(accumulated_text):
                text_without_code = text_without_code.replace(match.group(0), "")

            if pending_update and text_without_code.strip():
                safe_text = remove_markdown_stars(text_without_code)
                formatted_text = format_message(safe_text)
                try:
                    await self._safe_edit(
                        status_message, formatted_text, parse_mode=ParseMode.MARKDOWN_V2
                    )
                except (BadRequest, RetryAfter, TimedOut):
                    try:
                        await self._safe_edit(
                            status_message,
                            safe_text[:MAX_MESSAGE_LENGTH],
                            parse_mode=None,
                        )
                    except (BadRequest, RetryAfter, TimedOut):
                        pass

            if not accumulated_text:
                accumulated_text = "Готово!"

            safe_reply = remove_markdown_stars(accumulated_text)
            self._context_store.append(user.id, "assistant", safe_reply)

            formatted_text = format_message(safe_reply)
            chunks = split_formatted_text(formatted_text, CHUNK_BODY_LIMIT)

            if len(chunks) == 1:
                await self._safe_edit(
                    status_message, chunks[0], parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await self._safe_edit(
                    status_message,
                    f"Ответ длинный, частей: {len(chunks)}",
                    parse_mode=None,
                )
                for idx, chunk in enumerate(chunks, start=1):
                    await message.reply_text(f"Часть {idx}/{len(chunks)}")
                    await message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN_V2)

        except (BadRequest, RetryAfter, TimedOut) as exc:
            logger.exception("Telegram API error: %s", exc)
            await self._safe_edit(
                status_message,
                "Упс, произошла ошибка при отправке сообщения. Попробуй позже.",
            )
        except Exception as exc:
            logger.exception("AI error: %s", exc)
            await self._safe_edit(
                status_message,
                "Упс, сервис временно недоступен. Попробуй позже.",
            )

    async def _safe_edit(self, message, text: str, **kwargs) -> None:
        try:
            await message.edit_text(text, **kwargs)
        except BadRequest as exc:
            lowered = str(exc).lower()
            if "message is not modified" in lowered:
                return

            if kwargs.get("parse_mode") == ParseMode.MARKDOWN_V2:
                logger.warning("MarkdownV2 failed, trying plain text. Error: %s", exc)
                try:
                    await message.edit_text(
                        text, parse_mode=None, reply_markup=kwargs.get("reply_markup")
                    )
                except (RetryAfter, TimedOut) as e:
                    if isinstance(e, RetryAfter):
                        await asyncio.sleep(e.retry_after)
                    raise
                return
            raise
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            raise
        except TimedOut:
            raise


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        logs_dir / "bot.log",
        rotation="10 MB",
        retention="14 days",
        enqueue=True,
        encoding="utf-8",
    )
    settings = Settings.from_env()
    agent = TelegramAIAgent(settings)
    application = await agent.build_application()
    await application.initialize()
    await application.start()
    logger.info("Application started")
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.updater.start_polling()
    logger.info("Polling started")
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        logger.info("Shutdown signal received")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
