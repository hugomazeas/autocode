from abc import ABC, abstractmethod
from typing import AsyncIterator


class AIProvider(ABC):
    @abstractmethod
    async def run(
        self,
        prompt: str,
        repo_path: str,
        tools: list[str],
        max_turns: int,
    ) -> AsyncIterator[dict]:
        """Yields parsed stream-json events."""
        pass
