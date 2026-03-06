import asyncio
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Job:
    job_id: str
    ticket: str
    repo_url: str
    base_branch: str
    status: str = "queued"  # queued | planning | coding | committing | done | failed
    events: list = field(default_factory=list)
    pr_url: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobQueue:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    def create(self, ticket: str, repo_url: str, base_branch: str, job_id: str | None = None) -> Job:
        if job_id is None:
            job_id = uuid.uuid4().hex[:8]
        job = Job(job_id=job_id, ticket=ticket, repo_url=repo_url, base_branch=base_branch)
        self._jobs[job_id] = job
        self._queue.put_nowait(job_id)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def dequeue(self) -> Job:
        job_id = await self._queue.get()
        return self._jobs[job_id]
