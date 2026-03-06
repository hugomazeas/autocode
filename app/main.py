import asyncio
import json
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from . import db
from .jobs.queue import JobQueue
from .jobs.worker import worker_loop, cancel_job, run_followup

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="AutoCode Agent")
queue = JobQueue()

INDEX_PATH = "app/static/index.html"


@app.on_event("startup")
async def startup():
    config.validate()
    db.init_db()
    asyncio.create_task(worker_loop(queue))


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class RepoCreate(BaseModel):
    url: str
    default_branch: Optional[str] = None


class JobCreate(BaseModel):
    repo_id: int
    ticket: str
    base_branch: Optional[str] = None


class JobFollowup(BaseModel):
    prompt: str


class JobResponse(BaseModel):
    job_id: str


# ---------------------------------------------------------------------------
# SPA index
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(INDEX_PATH)


# ---------------------------------------------------------------------------
# Repos API
# ---------------------------------------------------------------------------

@app.post("/api/repos")
async def create_repo(body: RepoCreate):
    repo = db.add_repo(url=body.url, default_branch=body.default_branch or "main")
    return repo


@app.get("/api/repos")
async def list_repos():
    return db.list_repos()


@app.delete("/api/repos/{repo_id}")
async def delete_repo(repo_id: int):
    db.delete_repo(repo_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Jobs API
# ---------------------------------------------------------------------------

@app.post("/api/jobs", response_model=JobResponse)
async def create_job(body: JobCreate):
    repo = db.get_repo(body.repo_id)
    if not repo:
        raise HTTPException(404, "Repo not found")

    base_branch = body.base_branch or repo.get("default_branch") or "main"

    # Create persistent record in DB
    db_job = db.create_job(
        repo_id=body.repo_id,
        ticket=body.ticket,
        base_branch=base_branch,
    )
    job_id = db_job["id"]

    # Create in-memory job in the queue for event tracking / execution
    queue.create(
        job_id=job_id,
        ticket=body.ticket,
        repo_url=repo["url"],
        base_branch=base_branch,
    )

    return JobResponse(job_id=job_id)


@app.get("/api/jobs")
async def list_jobs(repo_id: Optional[int] = Query(None)):
    return db.list_jobs(repo_id=repo_id)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    # In-memory queue has live events
    mem_job = queue.get(job_id)
    events = mem_job.events if mem_job else []

    # DB has authoritative metadata (with repo_url joined)
    db_job = db.get_job_with_repo(job_id)
    if not db_job and not mem_job:
        raise HTTPException(404, "Job not found")

    if db_job:
        return {
            **db_job,
            "events": events,
        }

    # Fallback: only in-memory data available
    return {
        "job_id": mem_job.job_id,
        "status": mem_job.status,
        "repo_url": mem_job.repo_url,
        "pr_url": mem_job.pr_url,
        "error": mem_job.error,
        "events": events,
    }


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job_endpoint(job_id: str):
    await cancel_job(job_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/followup")
async def followup_job(job_id: str, body: JobFollowup):
    # Need the in-memory job for event tracking
    mem_job = queue.get(job_id)
    if not mem_job:
        # Job existed in DB but not in memory (e.g. after restart) — recreate it
        db_job = db.get_job_with_repo(job_id)
        if not db_job:
            raise HTTPException(404, "Job not found")
        if db_job["status"] not in ("done", "failed", "cancelled"):
            raise HTTPException(409, "Job is still running")
        mem_job = queue.create(
            job_id=job_id,
            ticket=db_job["ticket"],
            repo_url=db_job["repo_url"],
            base_branch=db_job["base_branch"],
        )
        # Don't let it enter the worker_loop queue — remove from the async queue
        try:
            queue._queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    else:
        if mem_job.status not in ("done", "failed", "cancelled"):
            raise HTTPException(409, "Job is still running")

    await run_followup(mem_job, body.prompt)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    async def generator():
        seen = 0
        while True:
            job = queue.get(job_id)
            if not job:
                yield f'data: {json.dumps({"type": "error", "content": "job not found"})}\n\n'
                break

            for event in job.events[seen:]:
                yield f"data: {json.dumps(event)}\n\n"
            seen = len(job.events)

            # Send status updates so the frontend can track phase changes
            yield f"data: {json.dumps({'type': 'status', 'status': job.status})}\n\n"

            if job.status in ("done", "failed", "cancelled"):
                yield f'data: {json.dumps({"type": "done", "status": job.status, "pr_url": job.pr_url or ""})}\n\n'
                break

            await asyncio.sleep(0.3)

    return StreamingResponse(generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Static files (must be mounted AFTER API routes)
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ---------------------------------------------------------------------------
# SPA catch-all (must be last)
# ---------------------------------------------------------------------------

@app.get("/{full_path:path}")
async def spa_catch_all(full_path: str):
    return FileResponse(INDEX_PATH)
