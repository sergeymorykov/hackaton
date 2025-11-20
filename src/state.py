from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

from .storage import DialogueStorage


Message = dict


@dataclass
class DialogueState:
    user_id: int
    max_messages: int = 12
    history: Deque[Message] = field(default_factory=deque)

    def append(self, role: str, content: str | list | dict) -> None:
        self.history.append({"role": role, "content": content})
        while len(self.history) > self.max_messages:
            self.history.popleft()

    def reset(self) -> None:
        self.history.clear()

    def export(self) -> List[Message]:
        return list(self.history)


class ContextStore:
    def __init__(self, max_messages: int = 12, storage: Optional[DialogueStorage] = None):
        self._store: Dict[int, DialogueState] = {}
        self._max_messages = max_messages
        self._storage = storage

    def get(self, user_id: int) -> DialogueState:
        if user_id not in self._store:
            state = DialogueState(user_id=user_id, max_messages=self._max_messages)
            if self._storage:
                history = self._storage.load_history(user_id, self._max_messages)
                for entry in history[-self._max_messages :]:
                    state.history.append(entry)
            self._store[user_id] = state
        return self._store[user_id]

    def append(self, user_id: int, role: str, content: str | list | dict) -> None:
        state = self.get(user_id)
        state.append(role, content)
        if self._storage:
            self._storage.replace_history(user_id, state.export())

    def reset(self, user_id: int) -> None:
        if user_id in self._store:
            self._store[user_id].reset()
        if self._storage:
            self._storage.reset_user(user_id)

