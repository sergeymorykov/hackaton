from src.state import ContextStore
from src.storage import DialogueStorage


def test_context_store_loads_from_storage(tmp_path):
    storage = DialogueStorage(tmp_path / "dialogues.db")
    store = ContextStore(max_messages=3, storage=storage)
    store.append(1, "user", "a")
    store.append(1, "assistant", "b")

    store = ContextStore(max_messages=3, storage=storage)
    state = store.get(1)
    assert [msg["content"] for msg in state.export()] == ["a", "b"]

    store.append(1, "user", "c")
    store.append(1, "assistant", "d")
    state = store.get(1)
    assert len(state.export()) == 3

