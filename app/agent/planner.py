from ..providers.base import AIProvider
from .prompts import PLANNER_PROMPT

PLANNER_TOOLS = ["Read", "Glob", "Grep", "Bash"]


async def run_planner(
    provider: AIProvider,
    ticket: str,
    repo_path: str,
    on_event,
):
    """Run the planner pass. Returns the extracted plan text."""
    prompt = PLANNER_PROMPT.format(ticket=ticket)
    plan_text = ""

    async for event in provider.run(
        prompt=prompt,
        repo_path=repo_path,
        tools=PLANNER_TOOLS,
        max_turns=5,
    ):
        await on_event(event)
        # Capture the final assistant text as the plan
        if event.get("type") == "assistant" and "content" in event:
            for block in event["content"]:
                if isinstance(block, dict) and block.get("type") == "text":
                    plan_text = block["text"]
        # Also handle result type from stream-json
        if event.get("type") == "result":
            plan_text = event.get("result", plan_text)

    return plan_text
