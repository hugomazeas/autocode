import asyncio
import logging
import time
from pathlib import Path

from .. import config, db
from ..providers.anthropic_cli import AnthropicCLIProvider
from ..agent.planner import run_planner
from ..agent.coder import run_coder
from ..git.operations import clone_repo, create_branch_and_commit, commit_and_push, cleanup
from ..platforms.github import GitHubPlatform
from ..platforms.gitlab import GitLabPlatform
from ..platforms.bitbucket import BitbucketPlatform
from .queue import Job, JobQueue

log = logging.getLogger(__name__)

PLATFORMS = {
    "github": GitHubPlatform,
    "gitlab": GitLabPlatform,
    "bitbucket": BitbucketPlatform,
}

# Maps job_id -> running asyncio.Task so jobs can be cancelled externally.
_running_jobs: dict[str, asyncio.Task] = {}

FOLLOWUP_PROMPT = """You are a senior developer. The user has a follow-up request on this codebase.

Previous ticket context:
{ticket}

Follow-up request:
{followup}

Instructions:
- Address the follow-up request
- After each significant change, run the existing tests with Bash
- Fix any test failures before continuing
- Do not push or commit — just edit the files
- Stop when all tests pass or you have no more changes to make"""


def _get_platform():
    cls = PLATFORMS[config.REPO_PLATFORM]
    return cls(config.REPO_TOKEN)


def _update_status(job: Job, status: str, **extra_fields):
    """Update in-memory job object AND persist to database."""
    job.status = status
    job.updated_at = time.time()
    db.update_job(job.job_id, status=status, updated_at=job.updated_at, **extra_fields)


async def cancel_job(job_id: str) -> bool:
    task = _running_jobs.get(job_id)
    if task is None:
        return False

    task.cancel()

    provider = getattr(task, "_provider_ref", None)
    if provider is not None:
        await provider.kill()

    db.update_job(job_id, status="cancelled", updated_at=time.time())
    return True


def _setup_task(job: Job, provider: AnthropicCLIProvider):
    """Stash provider on job and current task for cancel support."""
    job._provider = provider  # type: ignore[attr-defined]
    current_task = asyncio.current_task()
    if current_task is not None:
        current_task._provider_ref = provider  # type: ignore[attr-defined]


async def _run_job(job: Job):
    provider = AnthropicCLIProvider()
    _setup_task(job, provider)

    repo_path = config.WORKSPACE_DIR / job.job_id

    async def on_event(event: dict):
        job.events.append(event)
        job.updated_at = time.time()

    try:
        # 1. Clone (only if workspace doesn't exist yet)
        if not repo_path.exists():
            await on_event({"type": "system", "content": f"Cloning {job.repo_url}..."})
            await asyncio.to_thread(clone_repo, job.repo_url, repo_path)
            await on_event({"type": "system", "content": "Clone complete."})

        # 2. Planner pass
        _update_status(job, "planning")
        await on_event({"type": "system", "content": "Starting planner pass..."})
        plan = await run_planner(provider, job.ticket, str(repo_path), on_event)
        await on_event({"type": "system", "content": "Plan complete."})

        # 3. Coder pass
        _update_status(job, "coding")
        await on_event({"type": "system", "content": "Starting coder pass..."})
        await run_coder(provider, job.ticket, plan, str(repo_path), config.MAX_TURNS, on_event)
        await on_event({"type": "system", "content": "Coding complete."})

        # 4. Git commit + push
        _update_status(job, "committing")
        branch_name = f"agent/{job.job_id}"
        commit_msg = f"agent: {job.ticket[:72]}"
        await asyncio.to_thread(
            create_branch_and_commit, repo_path, branch_name, commit_msg
        )
        await on_event({"type": "system", "content": f"Pushed branch {branch_name}."})

        # 5. Create PR
        platform = _get_platform()
        pr_url = await platform.create_pr(
            repo_url=job.repo_url,
            branch=branch_name,
            base_branch=job.base_branch,
            title=f"[Agent] {job.ticket[:60]}",
            body=f"## Ticket\n{job.ticket}\n\n## Plan\n{plan}",
        )
        job.pr_url = pr_url
        _update_status(job, "done", pr_url=pr_url)
        await on_event({"type": "system", "content": f"PR created: {pr_url}"})

    except asyncio.CancelledError:
        log.info("Job %s cancelled by user", job.job_id)
        _update_status(job, "cancelled")
        await on_event({"type": "system", "content": "Job cancelled by user."})

    except Exception as e:
        log.exception("Job %s failed", job.job_id)
        job.error = str(e)
        _update_status(job, "failed", error=str(e))
        await on_event({"type": "error", "content": str(e)})


async def _run_followup(job: Job, prompt: str):
    """Run a follow-up coder pass on an existing workspace."""
    provider = AnthropicCLIProvider()
    _setup_task(job, provider)

    repo_path = config.WORKSPACE_DIR / job.job_id

    async def on_event(event: dict):
        job.events.append(event)
        job.updated_at = time.time()

    try:
        await on_event({"type": "system", "content": f"Follow-up: {prompt[:200]}"})

        if not repo_path.exists():
            # Workspace was cleaned up — re-clone and checkout the agent branch
            await on_event({"type": "system", "content": f"Re-cloning {job.repo_url}..."})
            await asyncio.to_thread(clone_repo, job.repo_url, repo_path)
            # Try to checkout the existing agent branch
            from git import Repo as GitRepo
            try:
                repo = GitRepo(str(repo_path))
                repo.git.checkout(f"agent/{job.job_id}")
            except Exception:
                pass  # Branch may not exist yet, that's fine
            await on_event({"type": "system", "content": "Clone complete."})

        # Run coder pass with follow-up prompt
        _update_status(job, "coding")
        await on_event({"type": "system", "content": "Starting follow-up pass..."})

        full_prompt = FOLLOWUP_PROMPT.format(ticket=job.ticket, followup=prompt)
        coder_tools = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

        async for event in provider.run(
            prompt=full_prompt,
            repo_path=str(repo_path),
            tools=coder_tools,
            max_turns=config.MAX_TURNS,
        ):
            await on_event(event)

        await on_event({"type": "system", "content": "Follow-up complete."})

        # Commit and push
        _update_status(job, "committing")
        branch_name = f"agent/{job.job_id}"
        commit_msg = f"agent follow-up: {prompt[:60]}"
        pushed = await asyncio.to_thread(
            commit_and_push, repo_path, branch_name, commit_msg
        )
        if pushed:
            await on_event({"type": "system", "content": f"Pushed to {branch_name}."})
        else:
            await on_event({"type": "system", "content": "No changes to push."})

        _update_status(job, "done")
        await on_event({"type": "system", "content": "Done."})

    except asyncio.CancelledError:
        log.info("Job %s follow-up cancelled", job.job_id)
        _update_status(job, "cancelled")
        await on_event({"type": "system", "content": "Follow-up cancelled by user."})

    except Exception as e:
        log.exception("Job %s follow-up failed", job.job_id)
        job.error = str(e)
        _update_status(job, "failed", error=str(e))
        await on_event({"type": "error", "content": str(e)})


async def run_followup(job: Job, prompt: str):
    """Public entry point to run a follow-up on a job. Returns immediately."""
    _update_status(job, "running")

    task = asyncio.create_task(_run_followup(job, prompt))
    _running_jobs[job.job_id] = task

    async def _cleanup():
        try:
            await task
        finally:
            _running_jobs.pop(job.job_id, None)

    asyncio.create_task(_cleanup())


async def worker_loop(queue: JobQueue):
    """Continuously dequeue and process jobs."""
    while True:
        job = await queue.dequeue()
        _update_status(job, "running")

        task = asyncio.create_task(_run_job(job))
        _running_jobs[job.job_id] = task

        try:
            await task
        finally:
            _running_jobs.pop(job.job_id, None)
