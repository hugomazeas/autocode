import os
import shutil
import tempfile
from pathlib import Path

from git import Repo

from .. import config


def _git_env() -> dict:
    """Build environment dict with SSH and HTTPS credential helper."""
    env = os.environ.copy()
    if config.SSH_KEY_PATH:
        env["GIT_SSH_COMMAND"] = f"ssh -i {config.SSH_KEY_PATH} -o StrictHostKeyChecking=no"
    if config.REPO_TOKEN:
        # Use a credential helper that returns the token for any HTTPS request
        env["GIT_ASKPASS"] = _ensure_askpass_script()
        env["GIT_TOKEN"] = config.REPO_TOKEN
    return env


_askpass_path: str | None = None


def _ensure_askpass_script() -> str:
    """Create a tiny script that echoes GIT_TOKEN for password prompts."""
    global _askpass_path
    if _askpass_path and os.path.exists(_askpass_path):
        return _askpass_path
    fd, path = tempfile.mkstemp(prefix="git-askpass-", suffix=".sh")
    with os.fdopen(fd, "w") as f:
        f.write('#!/bin/sh\nexec echo "$GIT_TOKEN"\n')
    os.chmod(path, 0o755)
    _askpass_path = path
    return path


def clone_repo(repo_url: str, dest: Path, branch: str | None = None) -> Repo:
    """Clone a repo into dest directory. If branch is None, uses remote default."""
    env = _git_env()
    kwargs = dict(env=env)
    if branch:
        kwargs["branch"] = branch
    repo = Repo.clone_from(repo_url, str(dest), **kwargs)
    return repo


def create_branch_and_commit(repo_path: Path, branch_name: str, message: str) -> str:
    """Create branch, stage all changes, commit, and push. Returns the branch name."""
    repo = Repo(str(repo_path))

    # Create and checkout branch
    repo.git.checkout("-b", branch_name)

    # Stage all changes
    repo.git.add("-A")

    if not repo.index.diff("HEAD"):
        return branch_name  # nothing to commit

    # Commit
    repo.index.commit(message)

    # Push
    env = _git_env()
    with repo.git.custom_environment(**env):
        repo.git.push("--set-upstream", "origin", branch_name)

    return branch_name


def commit_and_push(repo_path: Path, branch_name: str, message: str) -> bool:
    """Stage all changes, commit, and push on an existing branch. Returns True if anything was pushed."""
    repo = Repo(str(repo_path))

    # Make sure we're on the right branch
    if repo.active_branch.name != branch_name:
        repo.git.checkout(branch_name)

    repo.git.add("-A")

    if not repo.is_dirty(untracked_files=True):
        return False

    repo.index.commit(message)

    env = _git_env()
    with repo.git.custom_environment(**env):
        repo.git.push("origin", branch_name)

    return True


def cleanup(repo_path: Path):
    """Remove cloned repo directory."""
    if repo_path.exists():
        shutil.rmtree(repo_path)
