# AutoCode

A self-hosted coding agent that takes a ticket description, clones your repo, plans and implements changes using Claude Code CLI, then opens a pull request — all from a single web UI.

![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/fastapi-latest-green)
![License](https://img.shields.io/badge/license-MIT-gray)

## How it works

1. **You register a repository** and describe a task (ticket)
2. **Planner pass** — Claude explores the codebase and outputs a structured implementation plan
3. **Coder pass** — Claude implements the plan, editing files and running tests
4. **Commit & PR** — changes are pushed to a new branch and a pull request is created automatically

The web UI streams every step in real time: tool calls, reasoning, context usage, cost, and duration.

## Prerequisites

- **Docker** and **Docker Compose**
- A **Claude Code** session (you must be logged in to Claude Code on the host machine — the container mounts your `~/.claude` config)
- A **GitHub / GitLab / Bitbucket personal access token** with repo + PR permissions
- **SSH keys** configured on the host if your repos use SSH URLs

## Quick start

### 1. Clone the repo

```bash
git clone https://github.com/hugomazeas/autocode.git
cd autocode
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
REPO_PLATFORM=github              # github | gitlab | bitbucket
REPO_TOKEN=ghp_your_token_here    # personal access token
MAX_TURNS=20                      # max agent iterations per job
```

### 3. Start the service

```bash
docker compose up --build
```

The app will be available at **http://localhost:8000**.

### 4. Use it

1. Open http://localhost:8000
2. Add a repository (paste the git clone URL, e.g. `https://github.com/org/repo.git`)
3. Select the repo, describe the task, and hit **Submit Job**
4. Watch the agent plan, code, and open a PR in real time

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `REPO_PLATFORM` | yes | `github` | `github`, `gitlab`, or `bitbucket` |
| `REPO_TOKEN` | yes | — | Personal access token with repo + PR scope |
| `SSH_KEY_PATH` | no | — | Path to SSH key inside the container |
| `SSH_PRIVATE_KEY` | no | — | Inline SSH private key (alternative to path) |
| `STAGING_URL` | no | — | If set, the agent validates changes against this URL |
| `MAX_TURNS` | no | `20` | Hard cap on agent iterations per job |

## Running without Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Make sure 'claude' CLI is installed and authenticated
npm install -g @anthropic-ai/claude-code

# Set environment variables (or use a .env file)
export REPO_PLATFORM=github
export REPO_TOKEN=ghp_your_token_here

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Architecture

```
app/
├── main.py              # FastAPI app, API routes, SSE streaming
├── config.py            # Environment config + validation
├── db.py                # SQLite persistence (repos, jobs)
├── agent/
│   ├── planner.py       # Planner pass — explores repo, outputs plan
│   ├── coder.py         # Coder pass — implements plan, runs tests
│   └── prompts.py       # System prompts for planner and coder
├── jobs/
│   ├── queue.py         # In-memory async job queue
│   └── worker.py        # Job worker loop, follow-ups, cancellation
├── git/
│   └── operations.py    # Clone, branch, commit, push via GitPython
├── platforms/
│   ├── github.py        # GitHub PR creation via API
│   ├── gitlab.py        # GitLab MR creation via API
│   └── bitbucket.py     # Bitbucket PR creation via API
├── providers/
│   └── anthropic_cli.py # Wraps Claude Code CLI (stream-json output)
└── static/
    └── index.html       # Single-page dashboard UI
```

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/repos` | Register a repository |
| `GET` | `/api/repos` | List all repositories |
| `DELETE` | `/api/repos/:id` | Remove a repository |
| `POST` | `/api/jobs` | Create a new coding job |
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/jobs/:id` | Get job details + events |
| `GET` | `/api/jobs/:id/stream` | SSE stream of live job events |
| `POST` | `/api/jobs/:id/cancel` | Cancel a running job |
| `POST` | `/api/jobs/:id/followup` | Send a follow-up prompt to a completed job |
