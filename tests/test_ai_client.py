import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.ai_client import AIClient
from src.config import Settings


@pytest.mark.asyncio
async def test_ai_client_returns_model_answer(monkeypatch):
    settings = Settings(
        bot_token="test-token",
        api_key="sk-test",
        api_keys=("sk-test",),
        base_url="https://api.mapleai.de/v1",
        model_name="gpt-4o",
    )
    client = AIClient(settings)

    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))]
    )
    mock_create = AsyncMock(return_value=fake_response)
    monkeypatch.setattr(
        client._client.chat.completions, "create", mock_create
    )

    result = await client.generate_reply(
        [{"role": "user", "content": "ping"}], temperature=0.1, max_tokens=32
    )

    assert result == "answer"
    mock_create.assert_awaited_once()
    called_kwargs = mock_create.call_args.kwargs
    assert called_kwargs["model"] == settings.model_name
    assert called_kwargs["temperature"] == 0.1
    assert called_kwargs["max_completion_tokens"] == 32


class DummyTooManyError(Exception):
    def __init__(self, status_code):
        super().__init__("Too Many Requests")
        self.status_code = status_code


@pytest.mark.asyncio
async def test_ai_client_rotates_keys_on_rate_limit(monkeypatch):
    settings = Settings(
        bot_token="test-token",
        api_key="sk-a",
        api_keys=("sk-a", "sk-b"),
        base_url="https://api.mapleai.de/v1",
        model_name="gpt-4o",
    )

    created_clients = []

    def fake_build_client(self, api_key: str):
        create_mock = AsyncMock()
        if api_key == "sk-a":
            create_mock.side_effect = DummyTooManyError(429)
        else:
            create_mock.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="rotated"))]
            )
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )
        created_clients.append((api_key, create_mock))
        return client

    monkeypatch.setattr(AIClient, "_build_client", fake_build_client, raising=False)
    client = AIClient(settings)

    result = await client.generate_reply([{"role": "user", "content": "hi"}])

    assert result == "rotated"
    assert any(api == "sk-b" for api, _ in created_clients)


@pytest.mark.asyncio
async def test_ai_client_streaming(monkeypatch):
    settings = Settings(
        bot_token="test-token",
        api_key="sk-test",
        api_keys=("sk-test",),
        base_url="https://api.mapleai.de/v1",
        model_name="gpt-4o",
    )
    client = AIClient(settings)

    async def fake_stream():
        chunks = [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=" "))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="World"))]),
        ]
        for chunk in chunks:
            yield chunk

    async def create_mock(*args, **kwargs):
        return fake_stream()

    mock_create = AsyncMock(side_effect=create_mock)
    monkeypatch.setattr(
        client._client.chat.completions, "create", mock_create
    )

    chunks = []
    async for chunk in client.generate_reply_stream(
        [{"role": "user", "content": "hi"}]
    ):
        chunks.append(chunk)

    assert chunks == ["Hello", " ", "World"]
    mock_create.assert_awaited_once()
    called_kwargs = mock_create.call_args.kwargs
    assert called_kwargs["stream"] is True

