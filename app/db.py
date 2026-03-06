"""SQLite-based persistence layer for the AutoCode agent app."""

import os
import secrets
import sqlite3
import time

DB_PATH = "/app/data/autocode.db"


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


def init_db() -> None:
    """Create tables if they do not exist."""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS repos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                url             TEXT UNIQUE NOT NULL,
                name            TEXT NOT NULL,
                default_branch  TEXT NOT NULL DEFAULT 'main',
                created_at      REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id              TEXT PRIMARY KEY,
                repo_id         INTEGER NOT NULL REFERENCES repos(id),
                ticket          TEXT NOT NULL,
                base_branch     TEXT NOT NULL DEFAULT 'main',
                status          TEXT NOT NULL DEFAULT 'queued',
                pr_url          TEXT,
                error           TEXT,
                total_cost      REAL NOT NULL DEFAULT 0,
                created_at      REAL NOT NULL,
                updated_at      REAL NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _extract_name(url: str) -> str:
    """Extract a short 'org/repo' display name from a repo URL."""
    cleaned = url.rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    parts = cleaned.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1]


def add_repo(url: str, default_branch: str = "main") -> dict:
    """Insert a repo and return it as a dict. If URL already exists, return the existing one."""
    conn = _connect()
    try:
        cursor = conn.execute("SELECT * FROM repos WHERE url = ?", (url,))
        existing = cursor.fetchone()
        if existing is not None:
            # Update default_branch if a different one was provided
            if default_branch != existing["default_branch"]:
                conn.execute(
                    "UPDATE repos SET default_branch = ? WHERE id = ?",
                    (default_branch, existing["id"]),
                )
                conn.commit()
                return dict(conn.execute("SELECT * FROM repos WHERE id = ?", (existing["id"],)).fetchone())
            return dict(existing)

        name = _extract_name(url)
        now = time.time()
        cursor = conn.execute(
            "INSERT INTO repos (url, name, default_branch, created_at) VALUES (?, ?, ?, ?)",
            (url, name, default_branch, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM repos WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_repos() -> list[dict]:
    """Return all repos ordered by name."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM repos ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_repo(repo_id: int) -> dict | None:
    """Return a single repo by id, or None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM repos WHERE id = ?", (repo_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_repo(repo_id: int, **kwargs) -> None:
    """Update fields on a repo."""
    if not kwargs:
        return
    set_clause = ", ".join(f"{key} = ?" for key in kwargs)
    values = list(kwargs.values())
    values.append(repo_id)
    conn = _connect()
    try:
        conn.execute(f"UPDATE repos SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def delete_repo(repo_id: int) -> None:
    """Delete a repo and its jobs."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM jobs WHERE repo_id = ?", (repo_id,))
        conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
        conn.commit()
    finally:
        conn.close()


def create_job(repo_id: int, ticket: str, base_branch: str) -> dict:
    """Create a job with a random 8-char hex id and return it as a dict."""
    conn = _connect()
    try:
        job_id = secrets.token_hex(4)
        now = time.time()
        conn.execute(
            "INSERT INTO jobs (id, repo_id, ticket, base_branch, status, total_cost,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', 0, ?, ?)",
            (job_id, repo_id, ticket, base_branch, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_job(job_id: str) -> dict | None:
    """Return a single job by id, or None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_jobs(repo_id: int | None = None) -> list[dict]:
    """List jobs with repo name, optionally filtered by repo, ordered by created_at DESC."""
    conn = _connect()
    try:
        base = (
            "SELECT jobs.*, repos.name AS repo_name, repos.url AS repo_url "
            "FROM jobs JOIN repos ON jobs.repo_id = repos.id"
        )
        if repo_id is not None:
            rows = conn.execute(
                f"{base} WHERE jobs.repo_id = ? ORDER BY jobs.created_at DESC",
                (repo_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"{base} ORDER BY jobs.created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_job(job_id: str, **kwargs) -> None:
    """Update any fields on a job. Automatically sets updated_at."""
    if not kwargs:
        return
    kwargs["updated_at"] = time.time()
    set_clause = ", ".join(f"{key} = ?" for key in kwargs)
    values = list(kwargs.values())
    values.append(job_id)
    conn = _connect()
    try:
        conn.execute(
            f"UPDATE jobs SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
    finally:
        conn.close()


def get_job_with_repo(job_id: str) -> dict | None:
    """Return a job dict with an extra 'repo_url' field joined from repos."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT jobs.*, repos.url AS repo_url "
            "FROM jobs JOIN repos ON jobs.repo_id = repos.id "
            "WHERE jobs.id = ?",
            (job_id,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()
