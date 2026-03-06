from ..providers.base import AIProvider
from .prompts import CODER_PROMPT

CODER_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


async def run_coder(
    provider: AIProvider,
    ticket: str,
    plan: str,
    repo_path: str,
    max_turns: int,
    on_event,
):
    """Run the coder pass. Implements the plan."""
    prompt = CODER_PROMPT.format(ticket=ticket, plan=plan)

    async for event in provider.run(
        prompt=prompt,
        repo_path=repo_path,
        tools=CODER_TOOLS,
        max_turns=max_turns,
    ):
        await on_event(event)
