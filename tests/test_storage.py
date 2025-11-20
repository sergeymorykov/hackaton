from pathlib import Path

from src.storage import DialogueStorage


def test_dialogue_storage_persists_history(tmp_path):
    db_path = tmp_path / "dialogues.db"
    storage = DialogueStorage(db_path)

    storage.append(123, "user", "hello")
    storage.append(123, "assistant", "hi")

    history = storage.load_history(123, limit=5)
    assert history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]

    storage.replace_history(123, [{"role": "user", "content": "new"}])
    history = storage.load_history(123, limit=5)
    assert history == [{"role": "user", "content": "new"}]

    storage.reset_user(123)
    assert storage.load_history(123, limit=5) == []

