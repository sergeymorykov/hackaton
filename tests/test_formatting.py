from src.formatters import format_message, split_formatted_text


def test_format_message_wraps_html_without_backticks():
    raw = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
</head>
<body>
    <h1>Привет</h1>
</body>
</html>
"""

    formatted = format_message(raw)

    assert formatted.startswith("```html")
    assert formatted.rstrip().endswith("```")
    assert "<!DOCTYPE html>" in formatted


def test_format_message_plain_text_not_wrapped():
    raw = "Это обычное сообщение без кода и спецсимволов"
    formatted = format_message(raw)

    assert "```" not in formatted


def test_format_message_keeps_existing_code_block():
    raw = "```python\nprint('ok')\n```"
    formatted = format_message(raw)

    assert formatted.count("```python") == 1
    assert "print('ok')" in formatted


def test_split_long_code_block_preserves_fences():
    long_html = "```html\n" + "\n".join(f"<div id='{i}'></div>" for i in range(200)) + "\n```"
    parts = split_formatted_text(long_html, limit=300)
    assert len(parts) > 1
    assert parts[0].startswith("```html")
    assert parts[0].rstrip().endswith("```")
    assert parts[-1].rstrip().endswith("```")
    total = "".join(part.replace("```html\n", "").replace("```", "") for part in parts)
    assert "<div id='0'></div>" in total

