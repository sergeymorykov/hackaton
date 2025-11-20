from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .state import ContextStore

if TYPE_CHECKING:
    from .storage import DialogueStorage

SYSTEM_PROMPT = (
    "Ты отвечаешь в стиле «Лаконичный‑Практичный»: по делу, дружелюбно, без лишних украшательств. "
    "НЕ используй markdown форматирование (звёздочки, жирный текст и т.д.). "
    "Если нужно показать код, обязательно оборачивай его в тройные бэктики ```lang ... ``` с точным языком после первых бэктиков "
    "(например ```html, ```javascript). Внутри блоков кода ничего лишнего не добавляй. "
    "Обычные ответы делай короткими, списки оформляй маркерами -, избегай лишних эмодзи.\n\n"
    "ВАЖНО: Ты создан для конференции ТАТАР САН 2025. Когда пользователь спрашивает о твоём назначении, "
    "расскажи, что ты можешь рассказать подробности о конференции ТАТАР САН 2025 или ответить на любые вопросы."
)

CONFERENCE_INFO_PATH = Path(__file__).parent.parent / "Tatar_San_2025_Full_Info.md"

MENU_CALLBACKS = {
    "CMD_HELP": "help",
    "CMD_ABOUT": "about",
    "CMD_RESET": "reset",
}


def build_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("ℹ️ Помощь", callback_data="CMD_HELP"),
            ],
            [
                InlineKeyboardButton("🤖 О модели", callback_data="CMD_ABOUT"),
                InlineKeyboardButton("♻️ Сброс", callback_data="CMD_RESET"),
            ],
        ]
    )


def load_conference_info() -> str | None:
    try:
        if CONFERENCE_INFO_PATH.exists():
            return CONFERENCE_INFO_PATH.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Не удалось загрузить информацию о конференции: %s", exc)
    return None


def is_conference_question(text: str) -> bool:
    text_lower = text.lower()
    keywords = [
        "татар сан",
        "татарсан",
        "конференция",
        "футуршок",
        "хакатон",
        "королева кода",
        "спикер",
        "программа",
        "расписание",
        "казань",
        "22 ноября",
        "ит-парк",
    ]
    return any(keyword in text_lower for keyword in keywords)


def get_user_info(user) -> str:
    if not user:
        return ""

    info_parts = []
    if user.first_name:
        info_parts.append(f"Имя: {user.first_name}")
    if user.last_name:
        info_parts.append(f"Фамилия: {user.last_name}")
    if user.username:
        info_parts.append(f"Username: @{user.username}")
    if user.id:
        info_parts.append(f"ID: {user.id}")
    if user.language_code:
        info_parts.append(f"Язык: {user.language_code}")

    if info_parts:
        return "Информация о пользователе:\n" + "\n".join(info_parts)
    return ""


def get_bot_info_text(bot_info: dict | None) -> str:
    if not bot_info:
        return ""
    
    bot_info_text = "Информация о боте:\n"
    if bot_info.get("first_name"):
        bot_info_text += f"Имя бота: {bot_info['first_name']}\n"
    if bot_info.get("username"):
        bot_info_text += f"Username бота: @{bot_info['username']}\n"
    if bot_info.get("id"):
        bot_info_text += f"ID бота: {bot_info['id']}\n"
    bot_info_text += "\nИспользуй эту информацию для ответа на вопросы о боте."
    return bot_info_text


async def handle_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    context_store: ContextStore,
    bot_info: dict | None,
) -> None:
    user = update.effective_user
    text = (
        "Привет! Я AI-ассистент.\n\n"
        "Я создан для конференции ТАТАР САН 2025 и могу:\n"
        "• Рассказать о конференции «ФУТУРШОК» (22 ноября, Казань)\n"
        "• Ответить на вопросы о программе, спикерах, хакатоне\n"
        "• Помочь с любыми другими вопросами\n\n"
        "Задавай вопросы или используй кнопки ниже!"
    )
    await _reply(update, text, reply_markup=build_menu())
    if user:
        logger.info("User %s started bot", user.id)

        dialogue = context_store.get(user.id)
        if not dialogue.export():
            context_parts = []

            user_info = get_user_info(user)
            if user_info:
                context_parts.append(user_info)

            bot_info_text = get_bot_info_text(bot_info)
            if bot_info_text:
                context_parts.append(bot_info_text)

            if context_parts:
                full_context = (
                    "\n\n".join(context_parts)
                    + "\n\nИспользуй эту информацию для ответа на вопросы пользователя о себе или о боте (имя, username и т.д.)."
                )
                context_store.append(user.id, "system", full_context)


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "/start — приветствие и меню\n"
        "/help — эта справка\n"
        "/about — информация о модели\n"
        "/reset — очистка контекста\n\n"
        "Я могу рассказать о конференции ТАТАР САН 2025 или ответить на любые вопросы.\n"
        "Пиши обычные сообщения, я отвечу с учётом предыдущего контекста."
    )
    await _reply(update, text, reply_markup=build_menu())


async def handle_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "Модель: GPT 4o)"
    await _reply(update, text, reply_markup=build_menu())


async def handle_reset(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    context_store: ContextStore,
) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is not None:
        context_store.reset(user_id)
    await _reply(update, "Контекст очищен. Можем начать заново!", reply_markup=build_menu())


async def handle_menu_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    context_store: ContextStore,
    bot_info: dict | None,
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    action = MENU_CALLBACKS.get(query.data or "")
    if action == "help":
        await handle_help(update, context)
    elif action == "about":
        await handle_about(update, context)
    elif action == "reset":
        await handle_reset(update, context, context_store)


async def _reply(update: Update, text: str, **kwargs) -> None:
    from telegram.error import BadRequest

    if update.message:
        await update.message.reply_text(text, **kwargs)
    elif update.callback_query:
        current = update.callback_query.message
        if current and current.text == text:
            return
        try:
            await update.callback_query.edit_message_text(text, **kwargs)
        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
            raise

