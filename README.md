# hackaton
Тестовое задание на хакатон «Королева Кода»

Возможности
- Команды `/start`, `/help`, `/about`, `/reset` + inline-кнопки.
- Поддержка контекста диалога с усечением истории.
- Фильтрация стоп-слов и базовое логирование.
- Обработка ошибок AI/API, отображение статуса.

Быстрый старт
```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m src.bot
```

Переменные окружения
- `BOT_TOKEN` — токен BotFather.
- `ZENMUX_API_KEY` — основной ключ.
- `ZENMUX_BASE_URL` — `https://api.mapleai.de/v1`.
- `MODEL_NAME` — `gpt-4o`.
- `DIALOGUE_DB_PATH` — путь к SQLite для контекста (по умолчанию `data/dialogue.db`).

Тесты
```bash
python -m pytest
```

