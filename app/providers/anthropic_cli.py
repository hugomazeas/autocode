import asyncio
import json
from typing import AsyncIterator

from .base import AIProvider


class AnthropicCLIProvider(AIProvider):
    def __init__(self):
        self._process: asyncio.subprocess.Process | None = None

    async def kill(self):
        """Terminate the running subprocess, forcefully if necessary."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()

    async def run(
        self,
        prompt: str,
        repo_path: str,
        tools: list[str],
        max_turns: int,
    ) -> AsyncIterator[dict]:
        process = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            "--allowedTools", ",".join(tools),
            "--output-format", "stream-json",
            "--verbose",
            "--max-turns", str(max_turns),
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10 * 1024 * 1024,  # 10 MB line buffer for large stream-json events
        )
        self._process = process

        async for raw in process.stdout:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield {"type": "text", "content": line}

        await process.wait()
        if process.returncode != 0:
            err = await process.stderr.read()
            yield {"type": "error", "content": err.decode()}
